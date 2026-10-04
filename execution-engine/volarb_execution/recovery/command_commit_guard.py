"""[5,0,8,1,2] production Command Commit Guard."""

from __future__ import annotations

import asyncio
import inspect
from copy import deepcopy
from enum import StrEnum
from typing import Any, Mapping

from ..contracts.provider_error import (
    ProviderCommandOutcome,
    ProviderError,
    is_provider_error,
)
from ..ports.runtime_ports import assert_broker_port, assert_clock_port, assert_ledger_port
from .execution_action_envelope import (
    CorrelationIdFactory,
    ExecutionAction,
    broker_request_for_execution_action,
    normalize_execution_action,
)


class CommandCommitGuardErrorCode(StrEnum):
    STALE_INTENT = "COMMAND_COMMIT_GUARD.STALE_INTENT"
    INTERRUPT_CONFLICT = "COMMAND_COMMIT_GUARD.INTERRUPT_CONFLICT"
    INTEGRITY_DENIED = "COMMAND_COMMIT_GUARD.INTEGRITY_DENIED"
    DUPLICATE_ACTION = "COMMAND_COMMIT_GUARD.DUPLICATE_ACTION"
    CORRELATION_COLLISION = "COMMAND_COMMIT_GUARD.CORRELATION_COLLISION"
    WRITE_AHEAD_FAILED = "COMMAND_COMMIT_GUARD.WRITE_AHEAD_FAILED"
    POST_MUTATION_LEDGER_FAILED = "COMMAND_COMMIT_GUARD.POST_MUTATION_LEDGER_FAILED"


class CommandCommitGuardError(Exception):
    def __init__(
        self,
        code: CommandCommitGuardErrorCode,
        message: str,
        details: Mapping[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
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
    if inspect.isawaitable(value):
        return await value
    return value


def _allowed(result: Any) -> bool:
    if isinstance(result, bool):
        return result
    if isinstance(result, Mapping) and isinstance(result.get("allowed"), bool):
        return bool(result["allowed"])
    raise TypeError("authority result must be bool or {'allowed': bool}")


def _authority_reason(result: Any) -> Any:
    return result.get("reason") if isinstance(result, Mapping) else None


def _ledger_identity(action: ExecutionAction) -> dict[str, Any]:
    return {
        "actionId": action.action_id,
        "actionClass": action.action_class,
        "originType": action.origin_type,
        "originId": action.origin_id,
        "intentId": action.intent_id,
        "intentVersion": action.intent_version,
        "sliceId": action.slice_id,
        "correlationId": action.correlation_id,
        "operation": action.operation.value,
    }


def _row_value(row: Mapping[str, Any], camel: str, snake: str) -> Any:
    return row.get(camel, row.get(snake))


class CommandCommitGuard:
    """Single admission point for every mutating broker command.

    The in-process lock prevents concurrent duplicate admission within one guard
    instance. A production durable ledger must additionally enforce unique
    action/correlation identities across processes.
    """

    def __init__(
        self,
        *,
        broker_port: Any,
        ledger: Any,
        clock: Any,
        intent_authority: Any,
        integrity_authority: Any,
        interrupt_authority: Any,
        correlation_id_factory: CorrelationIdFactory | None = None,
    ) -> None:
        self.broker_port = assert_broker_port(broker_port)
        self.ledger = assert_ledger_port(ledger)
        self.clock = assert_clock_port(clock)
        self.intent_authority = _require_method(intent_authority, "intent_authority", "is_current")
        self.integrity_authority = _require_method(integrity_authority, "integrity_authority", "allows")
        self.interrupt_authority = _require_method(interrupt_authority, "interrupt_authority", "allows")
        self.correlation_id_factory = correlation_id_factory
        self._commit_lock = asyncio.Lock()

    async def _ledger_entries(self) -> list[Mapping[str, Any]]:
        entries = await _maybe_await(self.ledger.entries())
        if not isinstance(entries, list):
            raise TypeError("ledger.entries() must return a list")
        return entries

    async def _assert_unique(self, action: ExecutionAction) -> None:
        rows = await self._ledger_entries()
        if any(_row_value(row, "actionId", "action_id") == action.action_id for row in rows):
            raise CommandCommitGuardError(
                CommandCommitGuardErrorCode.DUPLICATE_ACTION,
                f"action {action.action_id} already exists in the execution ledger",
                _ledger_identity(action),
            )
        collision = next(
            (
                row
                for row in rows
                if _row_value(row, "correlationId", "correlation_id") == action.correlation_id
                and _row_value(row, "actionId", "action_id") != action.action_id
            ),
            None,
        )
        if collision is not None:
            raise CommandCommitGuardError(
                CommandCommitGuardErrorCode.CORRELATION_COLLISION,
                f"correlation {action.correlation_id} is already bound to another action",
                {
                    **_ledger_identity(action),
                    "existingActionId": _row_value(collision, "actionId", "action_id"),
                },
            )

    async def _assert_authorities(self, action: ExecutionAction) -> None:
        if action.intent_id is not None:
            current = await _maybe_await(
                self.intent_authority.is_current(
                    intent_id=action.intent_id,
                    intent_version=action.intent_version,
                    action=action,
                )
            )
            if not _allowed(current):
                raise CommandCommitGuardError(
                    CommandCommitGuardErrorCode.STALE_INTENT,
                    f"intent {action.intent_id} version {action.intent_version} is not current",
                    {**_ledger_identity(action), "reason": _authority_reason(current)},
                )

        interrupt = await _maybe_await(self.interrupt_authority.allows(action))
        if not _allowed(interrupt):
            raise CommandCommitGuardError(
                CommandCommitGuardErrorCode.INTERRUPT_CONFLICT,
                f"action {action.action_id} conflicts with the active interrupt state",
                {**_ledger_identity(action), "reason": _authority_reason(interrupt)},
            )

        integrity = await _maybe_await(self.integrity_authority.allows(action))
        if not _allowed(integrity):
            raise CommandCommitGuardError(
                CommandCommitGuardErrorCode.INTEGRITY_DENIED,
                f"state integrity does not permit action {action.action_id}",
                {**_ledger_identity(action), "reason": _authority_reason(integrity)},
            )

    async def _append_before_mutation(self, action: ExecutionAction) -> Any:
        entry = {
            "eventType": "MUTATION_INTENDED",
            "status": "INTENDED",
            **_ledger_identity(action),
            "createdAt": action.created_at,
            "request": deepcopy(action.payload),
        }
        try:
            return await _maybe_await(self.ledger.append(entry))
        except Exception as error:
            raise CommandCommitGuardError(
                CommandCommitGuardErrorCode.WRITE_AHEAD_FAILED,
                f"write-ahead ledger append failed for action {action.action_id}",
                _ledger_identity(action),
                error,
            ) from error

    async def _append_after_mutation(self, action: ExecutionAction, entry: Mapping[str, Any]) -> Any:
        try:
            return await _maybe_await(self.ledger.append(dict(entry)))
        except Exception as error:
            raise CommandCommitGuardError(
                CommandCommitGuardErrorCode.POST_MUTATION_LEDGER_FAILED,
                (
                    f"post-mutation ledger append failed for action {action.action_id}; "
                    "broker truth must be reconciled before another mutation"
                ),
                _ledger_identity(action),
                error,
            ) from error

    async def commit(self, action_input: Mapping[str, Any]) -> dict[str, Any]:
        async with self._commit_lock:
            return await self._commit_once(action_input)

    async def _commit_once(self, action_input: Mapping[str, Any]) -> dict[str, Any]:
        action = normalize_execution_action(
            action_input,
            now_ms=float(self.clock.now()),
            correlation_id_factory=self.correlation_id_factory,
        )

        await self._assert_unique(action)
        await self._assert_authorities(action)
        intended = await self._append_before_mutation(action)
        request = broker_request_for_execution_action(action)

        try:
            broker_result = await _maybe_await(self.broker_port.call(request))
            acknowledged = await self._append_after_mutation(
                action,
                {
                    "eventType": "BROKER_RESULT",
                    "status": "ACKNOWLEDGED",
                    **_ledger_identity(action),
                    "brokerObservedAt": (
                        broker_result.get("observedAt") if isinstance(broker_result, Mapping) else None
                    ),
                    "brokerProvider": (
                        broker_result.get("provider") if isinstance(broker_result, Mapping) else None
                    ),
                    "brokerResult": deepcopy(broker_result),
                },
            )
            return {
                "action": action,
                "intended": intended,
                "acknowledged": acknowledged,
                "broker_result": broker_result,
            }
        except CommandCommitGuardError:
            raise
        except Exception as error:
            if is_provider_error(error):
                provider_outcome = ProviderCommandOutcome(getattr(error, "outcome"))
                if isinstance(error, ProviderError):
                    provider_error_payload: Mapping[str, Any] = error.to_dict()
                else:
                    provider_error_payload = {
                        "name": type(error).__name__,
                        "contractVersion": getattr(error, "contract_version", None),
                        "category": str(getattr(error, "category", "")),
                        "code": str(getattr(error, "code", "")),
                        "message": str(error),
                        "operation": getattr(error, "operation", None),
                        "kind": str(getattr(error, "kind", "")),
                        "outcome": provider_outcome.value,
                        "provider": deepcopy(getattr(error, "provider", {})),
                        "observedAt": getattr(error, "observed_at", None),
                    }
            else:
                provider_outcome = ProviderCommandOutcome.UNKNOWN
                provider_error_payload = {
                    "name": type(error).__name__,
                    "message": str(error),
                }

            status = (
                "KNOWN_NOT_APPLIED"
                if provider_outcome is ProviderCommandOutcome.KNOWN_NOT_APPLIED
                else "UNKNOWN"
            )
            await self._append_after_mutation(
                action,
                {
                    "eventType": "BROKER_RESULT",
                    "status": status,
                    **_ledger_identity(action),
                    "providerOutcome": provider_outcome.value,
                    "providerError": deepcopy(dict(provider_error_payload)),
                },
            )
            raise
