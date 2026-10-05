"""Deterministic standalone tests for [5,0,8,1,2] Command Commit Guard."""

from __future__ import annotations

import asyncio
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from volarb_execution.contracts.provider_error import (  # noqa: E402
    ProviderCommandOutcome,
    ProviderError,
    ProviderErrorCategory,
    ProviderErrorCode,
    ProviderOperationKind,
)
from volarb_execution.recovery.command_commit_guard import (  # noqa: E402
    CommandCommitGuard,
    CommandCommitGuardError,
    CommandCommitGuardErrorCode,
)

from volarb_execution.recovery.execution_scope import ExecutionScope
from volarb_execution.recovery.sqlite_ledger import SQLiteExecutionLedger

SCOPE = ExecutionScope("simulated", "synthetic-account")


class FakeClock:
    def __init__(self, now_ms: int = 0) -> None:
        self._now_ms = now_ms

    def now(self) -> int:
        return self._now_ms

    def schedule(self, delay_ms: int, callback: Any) -> tuple[int, Any]:
        return delay_ms, callback


class RecordingLedger(SQLiteExecutionLedger):
    def __init__(self, trace, fail_append=False):
        self._directory = tempfile.TemporaryDirectory()
        self._trace, self._fail_append = trace, fail_append
        super().__init__(Path(self._directory.name) / "ledger.sqlite3")

    def admit(self, lease, action):
        if self._fail_append:
            raise OSError("disk unavailable")
        row = super().admit(lease, action)
        self._trace.append(("ledger.append", copy.deepcopy(row)))
        return row

    def mark_dispatch(self, lease, action_id, now_ms):
        row = super().mark_dispatch(lease, action_id, now_ms)
        self._trace.append(("ledger.append", copy.deepcopy(row)))
        return row

    def record_outcome(self, lease, action_id, status, details):
        row = super().record_outcome(lease, action_id, status, details)
        self._trace.append(("ledger.append", copy.deepcopy(row)))
        return row


class AllowIntent:
    async def is_current(self, **_: Any) -> bool:
        return True


class DenyIntent:
    async def is_current(self, **_: Any) -> dict[str, Any]:
        return {"allowed": False, "reason": "superseded by v2"}


class AllowAuthority:
    async def allows(self, _: Any) -> bool:
        return True


class DenyAuthority:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def allows(self, _: Any) -> dict[str, Any]:
        return {"allowed": False, "reason": self.reason}


class SimulatedBroker:
    def __init__(
        self,
        trace: list[tuple[str, dict[str, Any]]],
        *,
        outcome: ProviderCommandOutcome | None = None,
    ) -> None:
        self.trace = trace
        self.scope = SCOPE
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []
        self.applied = 0

    async def call(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(copy.deepcopy(request))
        payload = request["payload"]
        action_id = (
            payload.get("order", {}).get("actionId")
            if request["operation"] == "PLACE_ORDER"
            else payload.get("actionId")
        )
        correlation_id = (
            payload.get("order", {}).get("correlationId")
            if request["operation"] == "PLACE_ORDER"
            else payload.get("correlationId")
        )

        if self.outcome is ProviderCommandOutcome.KNOWN_NOT_APPLIED:
            raise ProviderError(
                category=ProviderErrorCategory.ORDER_REJECTED,
                code=ProviderErrorCode.ORDER_REJECTED,
                message="simulated rejection",
                operation=request["operation"],
                kind=ProviderOperationKind.COMMAND,
                outcome=ProviderCommandOutcome.KNOWN_NOT_APPLIED,
                provider={"key": "simulated"},
                observed_at="1970-01-01T00:00:00Z",
            )

        self.applied += 1
        self.trace.append(
            (
                "broker.command.applied",
                {
                    "operation": request["operation"],
                    "actionId": action_id,
                    "correlationId": correlation_id,
                },
            )
        )

        if self.outcome is ProviderCommandOutcome.UNKNOWN:
            self.trace.append(
                (
                    "broker.command.ambiguous",
                    {
                        "operation": request["operation"],
                        "actionId": action_id,
                        "correlationId": correlation_id,
                    },
                )
            )
            raise ProviderError(
                category=ProviderErrorCategory.NETWORK,
                code=ProviderErrorCode.NETWORK_FAILURE,
                message="simulated acknowledgement loss after apply",
                operation=request["operation"],
                kind=ProviderOperationKind.COMMAND,
                outcome=ProviderCommandOutcome.UNKNOWN,
                provider={"key": "simulated", "reason": "ACK_LOST_AFTER_APPLY"},
                observed_at="1970-01-01T00:00:00Z",
            )

        return {
            "contractVersion": "1.0",
            "provider": "simulated",
            "kind": request["kind"],
            "operation": request["operation"],
            "observedAt": "1970-01-01T00:00:00Z",
            "data": {"accepted": True, "brokerOrderRef": "synthetic-order-1"},
        }


def place_action(**overrides: Any) -> dict[str, Any]:
    action = {
        "action_id": "action-1",
        "action_class": "RISK_ADDING_PLACE",
        "origin_type": "ALGORITHM",
        "origin_id": "passive-chase",
        "intent_id": "intent-1",
        "intent_version": 1,
        "slice_id": "slice-1",
        "operation": "PLACE_ORDER",
        "payload": {
            "order": {
                "providerInstrumentRef": {
                    "provider": "simulated",
                    "providerInstrumentId": "NIFTY-TEST",
                    "exchangeSegment": "SIM",
                },
                "side": "BUY",
                "quantity": 10,
                "orderType": "LIMIT",
                "productType": "INTRADAY",
                "validity": "DAY",
                "price": 100,
            }
        },
    }
    action.update(overrides)
    return action


class CommandCommitGuardTests(unittest.IsolatedAsyncioTestCase):
    def make_guard(
        self,
        *,
        ledger: Any | None = None,
        broker: Any | None = None,
        intent_authority: Any | None = None,
        integrity_authority: Any | None = None,
        interrupt_authority: Any | None = None,
    ) -> tuple[CommandCommitGuard, list[tuple[str, dict[str, Any]]], RecordingLedger, SimulatedBroker]:
        trace: list[tuple[str, dict[str, Any]]] = []
        actual_ledger = ledger or RecordingLedger(trace)
        actual_broker = broker or SimulatedBroker(trace)
        self.addCleanup(actual_ledger._directory.cleanup)
        guard = CommandCommitGuard(
            broker_port=actual_broker,
            command_timeout_s=1,
            ledger=actual_ledger,
            clock=FakeClock(),
            intent_authority=intent_authority or AllowIntent(),
            integrity_authority=integrity_authority or AllowAuthority(),
            interrupt_authority=interrupt_authority or AllowAuthority(),
        )
        return guard, trace, actual_ledger, actual_broker

    async def test_write_ahead_happens_before_broker_mutation(self) -> None:
        guard, trace, ledger, broker = self.make_guard()

        result = await guard.commit(place_action())

        self.assertEqual(result["broker_result"]["operation"], "PLACE_ORDER")
        self.assertEqual(result["action"].correlation_id, "exec:action-1")
        rows = ledger.entries()
        self.assertEqual(rows[0]["eventType"], "MUTATION_INTENDED")
        self.assertEqual(rows[1]["eventType"], "DISPATCH_STARTED")
        self.assertEqual(rows[2]["eventType"], "BROKER_RESULT")
        self.assertEqual(rows[2]["status"], "ACKNOWLEDGED")
        event_names = [name for name, _ in trace]
        self.assertLess(
            event_names.index("ledger.append"),
            event_names.index("broker.command.applied"),
        )
        self.assertEqual(broker.applied, 1)

    async def test_ledger_failure_prevents_broker_mutation(self) -> None:
        trace: list[tuple[str, dict[str, Any]]] = []
        ledger = RecordingLedger(trace, fail_append=True)
        broker = SimulatedBroker(trace)
        guard, _, _, _ = self.make_guard(ledger=ledger, broker=broker)

        with self.assertRaises(CommandCommitGuardError) as raised:
            await guard.commit(place_action())

        self.assertEqual(raised.exception.code, CommandCommitGuardErrorCode.WRITE_AHEAD_FAILED)
        self.assertEqual(broker.calls, [])
        self.assertEqual(broker.applied, 0)

    async def test_stale_intent_is_rejected_before_ledger_or_broker(self) -> None:
        guard, _, ledger, broker = self.make_guard(intent_authority=DenyIntent())

        with self.assertRaises(CommandCommitGuardError) as raised:
            await guard.commit(place_action())

        self.assertEqual(raised.exception.code, CommandCommitGuardErrorCode.STALE_INTENT)
        self.assertEqual(ledger.entries(), [])
        self.assertEqual(broker.calls, [])

    async def test_integrity_denial_is_rejected_before_ledger_or_broker(self) -> None:
        guard, _, ledger, broker = self.make_guard(
            integrity_authority=DenyAuthority("market state stale")
        )

        with self.assertRaises(CommandCommitGuardError) as raised:
            await guard.commit(place_action())

        self.assertEqual(raised.exception.code, CommandCommitGuardErrorCode.INTEGRITY_DENIED)
        self.assertEqual(ledger.entries(), [])
        self.assertEqual(broker.calls, [])

    async def test_interrupt_conflict_is_rejected_before_ledger_or_broker(self) -> None:
        guard, _, ledger, broker = self.make_guard(
            interrupt_authority=DenyAuthority("flatten latch active")
        )

        with self.assertRaises(CommandCommitGuardError) as raised:
            await guard.commit(place_action())

        self.assertEqual(raised.exception.code, CommandCommitGuardErrorCode.INTERRUPT_CONFLICT)
        self.assertEqual(ledger.entries(), [])
        self.assertEqual(broker.calls, [])

    async def test_ambiguous_ack_is_recorded_and_same_action_cannot_blind_retry(self) -> None:
        trace: list[tuple[str, dict[str, Any]]] = []
        ledger = RecordingLedger(trace)
        broker = SimulatedBroker(trace, outcome=ProviderCommandOutcome.UNKNOWN)
        guard, _, _, _ = self.make_guard(ledger=ledger, broker=broker)
        action = place_action(action_id="action-ambiguous")

        with self.assertRaises(ProviderError) as raised:
            await guard.commit(action)
        self.assertEqual(raised.exception.outcome, ProviderCommandOutcome.UNKNOWN)

        rows = ledger.entries()
        result = next(
            row
            for row in rows
            if row["actionId"] == "action-ambiguous" and row["eventType"] == "BROKER_RESULT"
        )
        self.assertEqual(result["status"], "UNKNOWN")

        with self.assertRaises(CommandCommitGuardError) as duplicate:
            await guard.commit(action)
        self.assertEqual(duplicate.exception.code, CommandCommitGuardErrorCode.DUPLICATE_ACTION)
        self.assertEqual(broker.applied, 1)

    async def test_correlation_identity_cannot_be_reused(self) -> None:
        guard, _, _, broker = self.make_guard()
        await guard.commit(place_action(correlation_id="corr-shared"))

        with self.assertRaises(CommandCommitGuardError) as raised:
            await guard.commit(place_action(action_id="action-2", correlation_id="corr-shared"))

        self.assertEqual(raised.exception.code, CommandCommitGuardErrorCode.CORRELATION_COLLISION)
        self.assertEqual(broker.applied, 1)

    async def test_interrupt_action_may_omit_runtime_intent_identity(self) -> None:
        trace: list[tuple[str, dict[str, Any]]] = []
        ledger = RecordingLedger(trace)
        broker = SimulatedBroker(trace, outcome=ProviderCommandOutcome.KNOWN_NOT_APPLIED)
        guard, _, _, _ = self.make_guard(ledger=ledger, broker=broker)
        action = place_action(
            action_id="interrupt-cancel",
            action_class="EMERGENCY_CANCEL",
            origin_type="INTERRUPT",
            origin_id="interrupt-1",
            intent_id=None,
            intent_version=None,
            slice_id=None,
            operation="CANCEL_ORDER",
            payload={"orderId": "missing-order"},
        )

        with self.assertRaises(ProviderError) as raised:
            await guard.commit(action)

        self.assertEqual(raised.exception.outcome, ProviderCommandOutcome.KNOWN_NOT_APPLIED)
        rows = [row for row in ledger.entries() if row["actionId"] == "interrupt-cancel"]
        self.assertEqual(rows[0]["eventType"], "MUTATION_INTENDED")
        self.assertEqual(rows[2]["status"], "KNOWN_NOT_APPLIED")

    async def test_concurrent_duplicate_admission_releases_exactly_one_mutation(self) -> None:
        guard, _, _, broker = self.make_guard()
        action = place_action(action_id="action-concurrent")

        results = await asyncio.gather(
            guard.commit(action),
            guard.commit(action),
            return_exceptions=True,
        )

        successes = [result for result in results if not isinstance(result, BaseException)]
        failures = [result for result in results if isinstance(result, BaseException)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], CommandCommitGuardError)
        self.assertEqual(failures[0].code, CommandCommitGuardErrorCode.DUPLICATE_ACTION)
        self.assertEqual(broker.applied, 1)


if __name__ == "__main__":
    unittest.main()

