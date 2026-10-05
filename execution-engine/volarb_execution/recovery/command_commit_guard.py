"""[5,0,8,1,2] durable account-scoped Command Commit Guard."""

from __future__ import annotations

import asyncio
import inspect
import math
from copy import deepcopy
from enum import StrEnum
from typing import Any, Mapping

from ..contracts.provider_error import ProviderCommandOutcome, is_provider_error
from ..ports.runtime_ports import assert_admission_ledger_port, assert_broker_port, assert_clock_port
from .execution_action_envelope import CorrelationIdFactory, ExecutionAction, broker_request_for_execution_action, normalize_execution_action
from .execution_scope import ExecutionScope
from .sqlite_ledger import LedgerAdmissionError


class CommandCommitGuardErrorCode(StrEnum):
    STALE_INTENT = "COMMAND_COMMIT_GUARD.STALE_INTENT"
    INTERRUPT_CONFLICT = "COMMAND_COMMIT_GUARD.INTERRUPT_CONFLICT"
    INTEGRITY_DENIED = "COMMAND_COMMIT_GUARD.INTEGRITY_DENIED"
    DUPLICATE_ACTION = "COMMAND_COMMIT_GUARD.DUPLICATE_ACTION"
    CORRELATION_COLLISION = "COMMAND_COMMIT_GUARD.CORRELATION_COLLISION"
    SCOPE_BUSY = "COMMAND_COMMIT_GUARD.SCOPE_BUSY"
    SCOPE_UNRESOLVED = "COMMAND_COMMIT_GUARD.SCOPE_UNRESOLVED"
    WRITE_AHEAD_FAILED = "COMMAND_COMMIT_GUARD.WRITE_AHEAD_FAILED"
    POST_MUTATION_LEDGER_FAILED = "COMMAND_COMMIT_GUARD.POST_MUTATION_LEDGER_FAILED"


class CommandCommitGuardError(Exception):
    def __init__(self, code: CommandCommitGuardErrorCode, message: str,
                 details: Mapping[str, Any] | None = None, cause: BaseException | None = None) -> None:
        self.code = code
        self.details = deepcopy(dict(details or {}))
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause


def _require_method(value: Any, name: str, method: str) -> Any:
    if value is None or not callable(getattr(value, method, None)):
        raise TypeError(f"{name} must implement {method}()")
    return value


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _allowed(result: Any) -> bool:
    if isinstance(result, bool):
        return result
    if isinstance(result, Mapping) and isinstance(result.get("allowed"), bool):
        return result["allowed"]
    raise TypeError("authority result must be bool or {'allowed': bool}")


class CommandCommitGuard:
    """One admitted command per account until authoritative resolution.

    The bound broker, all guards, reconciliation and authority writers must use
    the same ledger/account fence. Authority callbacks are read-only. Broker calls
    must be nonblocking/async and must not suppress task cancellation.
    """

    def __init__(self, *, broker_port: Any, ledger: Any, clock: Any,
                 intent_authority: Any, integrity_authority: Any, interrupt_authority: Any,
                 command_timeout_s: float, correlation_id_factory: CorrelationIdFactory | None = None) -> None:
        self.broker_port = assert_broker_port(broker_port)
        self.scope = getattr(broker_port, "scope", None)
        if not isinstance(self.scope, ExecutionScope):
            raise TypeError("broker_port must have a trusted ExecutionScope account binding")
        self.ledger = assert_admission_ledger_port(ledger)
        self.clock = assert_clock_port(clock)
        if isinstance(command_timeout_s, bool) or not math.isfinite(command_timeout_s) or command_timeout_s <= 0:
            raise ValueError("command_timeout_s must be positive and finite")
        self.command_timeout_s = command_timeout_s
        self.intent_authority = _require_method(intent_authority, "intent_authority", "is_current")
        self.integrity_authority = _require_method(integrity_authority, "integrity_authority", "allows")
        self.interrupt_authority = _require_method(interrupt_authority, "interrupt_authority", "allows")
        for authority in (self.intent_authority, self.integrity_authority, self.interrupt_authority):
            if getattr(authority, "scope", self.scope) != self.scope:
                raise ValueError("authority is bound to a different broker account")
        self.correlation_id_factory = correlation_id_factory
        self._commit_lock = asyncio.Lock()

    async def _assert_authorities(self, action: ExecutionAction) -> None:
        if action.intent_id is not None:
            result = await _maybe_await(self.intent_authority.is_current(
                intent_id=action.intent_id, intent_version=action.intent_version, action=action))
            if not _allowed(result):
                raise CommandCommitGuardError(CommandCommitGuardErrorCode.STALE_INTENT,
                                              "intent version is not current", {"actionId": action.action_id})
        for authority, code in ((self.interrupt_authority, CommandCommitGuardErrorCode.INTERRUPT_CONFLICT),
                                (self.integrity_authority, CommandCommitGuardErrorCode.INTEGRITY_DENIED)):
            result = await _maybe_await(authority.allows(action))
            if not _allowed(result):
                raise CommandCommitGuardError(code, "authority denies action", {
                    "actionId": action.action_id, "reason": result.get("reason") if isinstance(result, Mapping) else None})

    def _record_outcome(self, lease: Any, action: ExecutionAction, status: str, details: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return self.ledger.record_outcome(lease, action.action_id, status, details)
        except Exception as error:
            raise CommandCommitGuardError(CommandCommitGuardErrorCode.POST_MUTATION_LEDGER_FAILED,
                                          "broker outcome was not persisted; account remains unresolved",
                                          {"actionId": action.action_id}, error) from error

    def _known_not_applied(self, error: BaseException, action: ExecutionAction) -> bool:
        if not is_provider_error(error):
            return False
        provider = getattr(error, "provider", {})
        return (getattr(error, "outcome", None) == ProviderCommandOutcome.KNOWN_NOT_APPLIED
                and str(getattr(error, "kind", "")) == "COMMAND"
                and getattr(error, "operation", None) == action.operation.value
                and isinstance(provider, Mapping) and provider.get("key") == self.scope.provider)

    def _validate_ack(self, result: Any, action: ExecutionAction) -> None:
        if (not isinstance(result, Mapping) or result.get("contractVersion") != "1.0"
                or result.get("provider") != self.scope.provider or result.get("kind") != "COMMAND"
                or result.get("operation") != action.operation.value):
            raise ValueError("invalid broker acknowledgement envelope")
        data = result.get("data")
        if not isinstance(data, Mapping) or not isinstance(data.get("brokerOrderRef"), str) or not data["brokerOrderRef"].strip():
            raise ValueError("broker acknowledgement lacks order identity")
        if action.operation.value != "PLACE_ORDER" and data["brokerOrderRef"] != action.payload.get("orderId"):
            raise ValueError("broker acknowledgement references a different order")

    async def commit(self, action_input: Mapping[str, Any]) -> dict[str, Any]:
        async with self._commit_lock:
            action = normalize_execution_action(action_input, now_ms=float(self.clock.now()), correlation_id_factory=self.correlation_id_factory)
            try:
                with self.ledger.lock_scope(self.scope) as lease:
                    await self._assert_authorities(action)
                    request = broker_request_for_execution_action(action)
                    try:
                        intended = self.ledger.admit(lease, action)
                    except LedgerAdmissionError:
                        raise
                    except Exception as error:
                        raise CommandCommitGuardError(CommandCommitGuardErrorCode.WRITE_AHEAD_FAILED,
                                                      "durable admission failed", {"actionId": action.action_id}, error) from error
                    try:
                        await self._assert_authorities(action)
                        if broker_request_for_execution_action(action) != request:
                            raise ValueError("authority callback changed the admitted action")
                    except BaseException:
                        # Failed abort persistence leaves INTENDED, also provably unsent.
                        self.ledger.abort_before_dispatch(lease, action.action_id, "authority or preparation failed before dispatch")
                        raise
                    try:
                        self.ledger.mark_dispatch(lease, action.action_id, float(self.clock.now()))
                    except Exception as error:
                        raise CommandCommitGuardError(CommandCommitGuardErrorCode.WRITE_AHEAD_FAILED,
                                                      "dispatch marker was not durably confirmed; do not send",
                                                      {"actionId": action.action_id}, error) from error
                    try:
                        async with asyncio.timeout(self.command_timeout_s):
                            result = await _maybe_await(self.broker_port.call(request))
                        self._validate_ack(result, action)
                    except BaseException as error:
                        status = "KNOWN_NOT_APPLIED" if self._known_not_applied(error, action) else "UNKNOWN"
                        self._record_outcome(lease, action, status, {
                            "providerError": {"name": type(error).__name__, "message": str(error)}, "providerOutcome": status})
                        raise
                    acknowledged = self._record_outcome(lease, action, "ACKNOWLEDGED", {"brokerResult": deepcopy(result)})
                    return {"action": action, "intended": intended, "acknowledged": acknowledged,
                            "broker_result": result, "reconciliation_required": True}
            except LedgerAdmissionError as error:
                codes = {code.name: code for code in CommandCommitGuardErrorCode}
                raise CommandCommitGuardError(codes.get(error.code, CommandCommitGuardErrorCode.WRITE_AHEAD_FAILED),
                                              str(error), {"actionId": action.action_id}, error) from error
