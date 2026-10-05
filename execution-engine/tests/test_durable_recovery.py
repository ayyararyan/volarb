"""Real-file, cross-process and broker-evidence recovery tests; no live I/O."""

from __future__ import annotations

import asyncio
import copy
import multiprocessing
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_command_commit_guard import (AllowAuthority, AllowIntent, FakeClock, SimulatedBroker, SCOPE, place_action)
from volarb_execution.contracts.provider_error import ProviderCommandOutcome, ProviderError
from volarb_execution.recovery.command_commit_guard import CommandCommitGuard, CommandCommitGuardError
from volarb_execution.recovery.execution_action_envelope import normalize_execution_action
from volarb_execution.recovery.execution_scope import AccountBrokerPort, ExecutionScope
from volarb_execution.recovery.scoped_reconciliation import ScopedReconciler
from volarb_execution.recovery.sqlite_ledger import LedgerAdmissionError, LedgerIntentAuthority, SQLiteExecutionLedger


def guard(ledger, broker, *, clock=None, intent=None, integrity=None, timeout=1):
    return CommandCommitGuard(ledger=ledger, broker_port=broker, clock=clock or FakeClock(),
                              intent_authority=intent or AllowIntent(), integrity_authority=integrity or AllowAuthority(),
                              interrupt_authority=AllowAuthority(), command_timeout_s=timeout)


class TruthBroker(SimulatedBroker):
    def __init__(self, *, outcome=None):
        super().__init__([], outcome=outcome)
        self.order = {
            "brokerOrderRef": "synthetic-order-1", "brokerCorrelationRef": "native-correlation",
            "instrument": {"provider": "simulated", "providerInstrumentId": "NIFTY-TEST", "exchangeSegment": "SIM"},
            "side": "BUY", "productType": "INTRADAY", "orderType": "LIMIT", "status": "PARTIALLY_FILLED",
            "requestedQuantity": 10, "filledQuantity": 3, "remainingQuantity": 7, "limitPrice": 100,
        }
        self.trades = [{"brokerOrderRef": "synthetic-order-1", "exchangeTradeRef": "synthetic-trade-1",
                        "instrument": copy.deepcopy(self.order["instrument"]), "side": "BUY", "productType": "INTRADAY",
                        "quantity": 3, "price": 100}]
        self.positions = [{"instrument": copy.deepcopy(self.order["instrument"]), "productType": "INTRADAY", "netQuantity": 3}]
        self.query_calls = []
        self.hook = None

    async def call(self, request):
        if request["kind"] == "COMMAND":
            return await super().call(request)
        self.query_calls.append(copy.deepcopy(request))
        op = request["operation"]
        if op in {"GET_ORDER", "GET_ORDER_BY_CORRELATION"}:
            data = copy.deepcopy(self.order)
            if op == "GET_ORDER_BY_CORRELATION":
                data.update(coreCorrelationId=request["payload"]["correlationId"], providerCorrelationRef="native-correlation")
        elif op == "GET_ORDER_TRADES":
            data = copy.deepcopy(self.trades)
        elif op == "GET_POSITIONS":
            data = copy.deepcopy(self.positions)
        else:
            raise AssertionError(op)
        result = {"contractVersion": "1.0", "provider": "simulated", "kind": "QUERY", "operation": op,
                  "observedAt": "1970-01-01T00:00:00Z", "data": data}
        if self.hook:
            self.hook(result)
        return result


def concurrent_worker(path, barrier, queue, action_id):
    ledger = SQLiteExecutionLedger(path)
    broker = SimulatedBroker([])
    barrier.wait(timeout=10)
    try:
        asyncio.run(guard(ledger, broker).commit(place_action(action_id=action_id)))
        queue.put(("ACKNOWLEDGED", broker.applied))
    except CommandCommitGuardError as error:
        queue.put((error.code.name, broker.applied))


def crash_worker(path, marker):
    class CrashBroker(SimulatedBroker):
        async def call(self, request):
            with open(marker, "w") as handle:
                handle.write("broker applied before process crash")
                handle.flush()
                os.fsync(handle.fileno())
            os._exit(17)
    asyncio.run(guard(SQLiteExecutionLedger(path), CrashBroker([])).commit(place_action(action_id="crashed-action")))


class DurableRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "execution.sqlite3"
        self.ledger = SQLiteExecutionLedger(self.path)
        self.broker = TruthBroker()

    def reconciler(self, *, ledger=None, broker=None, clock=None):
        return ScopedReconciler(ledger=ledger or self.ledger, broker_port=broker or self.broker,
                                clock=clock or FakeClock(), max_observation_age_ms=1000, query_timeout_s=1)

    async def assert_blocked(self, *, ledger=None, action_id="replacement", broker=None):
        with self.assertRaises(CommandCommitGuardError) as error:
            await guard(ledger or self.ledger, broker or self.broker).commit(place_action(action_id=action_id))
        self.assertEqual(error.exception.code.name, "SCOPE_UNRESOLVED")

    async def test_acknowledgement_needs_broker_reconciliation_before_next_mutation(self):
        result = await guard(self.ledger, self.broker).commit(place_action())
        self.assertTrue(result["reconciliation_required"])
        await self.assert_blocked()
        recovery = await self.reconciler().reconcile()
        self.assertEqual(recovery["state"], "CLEAN")
        self.assertEqual(recovery["confirmedFilledQuantity"], 3)
        self.assertEqual(recovery["confirmedUnfilledQuantity"], 7)
        self.assertTrue(recovery["orderStillFillable"])
        self.assertIsNone(self.ledger.pending(SCOPE))
        await guard(self.ledger, self.broker).commit(place_action(action_id="deliberately-new-work"))
        self.assertEqual(self.broker.applied, 2)

    async def test_lost_ack_blocks_new_ids_after_restart_and_positive_evidence_resolves(self):
        self.broker.outcome = ProviderCommandOutcome.UNKNOWN
        with self.assertRaises(ProviderError):
            await guard(self.ledger, self.broker).commit(place_action())
        restarted = SQLiteExecutionLedger(self.path)
        await self.assert_blocked(ledger=restarted)
        self.assertEqual((await self.reconciler(ledger=restarted).reconcile())["state"], "CLEAN")
        self.assertEqual(self.broker.applied, 1)
        self.assertTrue(all(r["kind"] == "QUERY" for r in self.broker.query_calls))

    async def test_duplicate_action_and_correlation_remain_reserved_after_resolution_and_restart(self):
        await guard(self.ledger, self.broker).commit(place_action())
        await self.reconciler().reconcile()
        restarted = SQLiteExecutionLedger(self.path)
        for action, code in [(place_action(), "DUPLICATE_ACTION"),
                             (place_action(action_id="different", correlation_id="exec:action-1"), "CORRELATION_COLLISION")]:
            with self.assertRaises(CommandCommitGuardError) as error:
                await guard(restarted, self.broker).commit(action)
            self.assertEqual(error.exception.code.name, code)

    async def test_unknown_scope_does_not_block_other_broker_accounts(self):
        await guard(self.ledger, self.broker).commit(place_action())
        other_scope = ExecutionScope("simulated", "other-synthetic-account")
        delegate = SimulatedBroker([])
        delegate.scope = other_scope
        other = AccountBrokerPort(other_scope, delegate)
        await guard(self.ledger, other).commit(place_action(action_id="other-action"))
        self.assertIsNotNone(self.ledger.pending(SCOPE))
        self.assertIsNotNone(self.ledger.pending(other.scope))

    async def test_empty_lookup_is_not_proof_of_non_application(self):
        await guard(self.ledger, self.broker).commit(place_action())
        self.broker.hook = lambda result: result.update(data={})
        result = await self.reconciler().reconcile()
        self.assertEqual(result["state"], "AMBIGUOUS")
        await self.assert_blocked()

    async def test_correlated_order_cannot_contradict_persisted_acknowledgement(self):
        await guard(self.ledger, self.broker).commit(place_action())
        self.broker.order["brokerOrderRef"] = "contradictory-order"
        for _ in range(2):
            result = await self.reconciler().reconcile()
            self.assertEqual(result["state"], "AMBIGUOUS")
            self.assertIn("contradicts acknowledged order identity", result["reason"])
            await self.assert_blocked()

    async def test_bad_or_stale_evidence_never_releases_scope(self):
        await guard(self.ledger, self.broker).commit(place_action())
        mutations = [lambda r: r.update(provider="wrong-provider"),
                     lambda r: r.update(operation="GET_FUNDS"),
                     lambda r: r.update(observedAt="1969-12-31T23:59:59Z"),
                     lambda r: r.update(observedAt="1970-01-01T00:00:01Z"),
                     lambda r: r["data"].update(coreCorrelationId="different") if isinstance(r["data"], dict) else None,
                     lambda r: r["data"].update(brokerCorrelationRef="different") if isinstance(r["data"], dict) else None]
        for mutation in mutations:
            self.broker.hook = mutation
            self.assertEqual((await self.reconciler().reconcile())["state"], "AMBIGUOUS")
            await self.assert_blocked()

    async def test_trade_duplicates_are_deduplicated_but_conflicts_are_rejected(self):
        await guard(self.ledger, self.broker).commit(place_action())
        conflicting = copy.deepcopy(self.broker.trades[0]); conflicting["quantity"] = 2
        self.broker.trades.append(conflicting)
        self.assertEqual((await self.reconciler().reconcile())["state"], "AMBIGUOUS")
        self.broker.trades[1] = copy.deepcopy(self.broker.trades[0])
        result = await self.reconciler().reconcile()
        self.assertEqual(result["state"], "CLEAN")
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["confirmedFilledQuantity"], 3)

    async def test_missing_fills_or_order_changes_preserve_uncertainty(self):
        await guard(self.ledger, self.broker).commit(place_action())
        original = self.broker.trades
        self.broker.trades = []
        self.assertEqual((await self.reconciler().reconcile())["state"], "AMBIGUOUS")
        self.broker.trades = original
        def fill_during_snapshot(result):
            if result["operation"] == "GET_ORDER":
                result["data"].update(filledQuantity=4, remainingQuantity=6)
        self.broker.hook = fill_during_snapshot
        self.assertEqual((await self.reconciler().reconcile())["state"], "AMBIGUOUS")
        await self.assert_blocked()

    async def test_cancel_race_resolves_terminal_order_and_exact_fills(self):
        action = place_action(operation="CANCEL_ORDER", payload={"orderId": "synthetic-order-1"})
        await guard(self.ledger, self.broker).commit(action)
        self.assertEqual((await self.reconciler().reconcile())["state"], "AMBIGUOUS")
        self.broker.order.update(status="CANCELLED", remainingQuantity=0)
        result = await self.reconciler().reconcile()
        self.assertEqual(result["state"], "CLEAN")
        self.assertEqual(result["resolution"], "TARGET_ORDER_TERMINAL")
        self.assertFalse(result["orderStillFillable"])
        self.assertEqual(result["confirmedUnfilledQuantity"], 7)

    async def test_modify_field_match_alone_cannot_clear_uncertain_command(self):
        self.broker.outcome = ProviderCommandOutcome.UNKNOWN
        action = place_action(operation="MODIFY_ORDER", payload={"orderId": "synthetic-order-1", "changes": {"price": 100}})
        with self.assertRaises(ProviderError):
            await guard(self.ledger, self.broker).commit(action)
        self.assertEqual((await self.reconciler().reconcile())["state"], "AMBIGUOUS")
        self.broker.order.update(status="FILLED", filledQuantity=10, remainingQuantity=0)
        self.broker.trades[0]["quantity"] = 10
        self.broker.positions[0]["netQuantity"] = 10
        self.assertEqual((await self.reconciler().reconcile())["state"], "CLEAN")

    async def test_ledger_failure_after_broker_call_leaves_dispatch_block_across_restart(self):
        with patch.object(self.ledger, "record_outcome", side_effect=OSError("disk full")):
            with self.assertRaises(CommandCommitGuardError) as error:
                await guard(self.ledger, self.broker).commit(place_action())
        self.assertEqual(error.exception.code.name, "POST_MUTATION_LEDGER_FAILED")
        self.assertEqual(self.broker.applied, 1)
        restarted = SQLiteExecutionLedger(self.path)
        self.assertEqual(restarted.pending(SCOPE)["status"], "DISPATCHING")
        await self.assert_blocked(ledger=restarted)
        self.assertEqual((await self.reconciler(ledger=restarted).reconcile())["state"], "CLEAN")

    async def test_dispatch_marker_failure_never_sends(self):
        with patch.object(self.ledger, "mark_dispatch", side_effect=OSError("disk full")):
            with self.assertRaises(CommandCommitGuardError):
                await guard(self.ledger, self.broker).commit(place_action())
        self.assertEqual(self.broker.calls, [])
        result = await self.reconciler().reconcile()
        self.assertEqual(result["resolution"], "NOT_SENT")
        self.assertEqual(self.broker.query_calls, [])

    async def test_dispatch_commit_with_lost_local_receipt_stays_uncertain(self):
        original = self.ledger.mark_dispatch
        def commit_then_fail(lease, action_id, now_ms):
            original(lease, action_id, now_ms)
            raise OSError("commit receipt lost")
        with patch.object(self.ledger, "mark_dispatch", side_effect=commit_then_fail):
            with self.assertRaises(CommandCommitGuardError):
                await guard(self.ledger, self.broker).commit(place_action())
        self.assertEqual(self.broker.calls, [])
        self.assertEqual(self.ledger.pending(SCOPE)["status"], "DISPATCHING")
        self.broker.hook = lambda result: result.update(data={})
        self.assertEqual((await self.reconciler().reconcile())["state"], "AMBIGUOUS")
        await self.assert_blocked()

    async def test_mutating_authority_cannot_change_write_ahead_request(self):
        class MutatingAuthority:
            count = 0
            def allows(self, action):
                self.count += 1
                if self.count == 2:
                    action.payload["order"]["quantity"] = 100
                return True
        with self.assertRaises(ValueError):
            await guard(self.ledger, self.broker, integrity=MutatingAuthority()).commit(place_action())
        self.assertEqual(self.broker.calls, [])
        self.assertEqual(self.ledger.entries()[0]["request"]["order"]["quantity"], 10)
        self.assertIsNone(self.ledger.pending(SCOPE))

    async def test_malformed_acknowledgement_stays_unknown(self):
        class BadAck(SimulatedBroker):
            async def call(self, request):
                result = await super().call(request)
                result["provider"] = "another-provider"
                return result
        broker = BadAck([])
        with self.assertRaises(ValueError):
            await guard(self.ledger, broker).commit(place_action())
        self.assertEqual(broker.applied, 1)
        self.assertEqual(self.ledger.pending(SCOPE)["status"], "UNKNOWN")

    async def test_query_failure_cannot_be_used_as_command_non_application(self):
        class Misattributed(SimulatedBroker):
            async def call(self, request):
                try:
                    return await super().call(request)
                except ProviderError as error:
                    error.kind = "QUERY"
                    raise
        broker = Misattributed([], outcome=ProviderCommandOutcome.KNOWN_NOT_APPLIED)
        with self.assertRaises(ProviderError):
            await guard(self.ledger, broker).commit(place_action())
        self.assertEqual(self.ledger.pending(SCOPE)["status"], "UNKNOWN")

    async def test_timeout_leaves_uncertainty_and_releases_os_lock(self):
        class NeverAcknowledges(SimulatedBroker):
            async def call(self, request):
                await asyncio.Event().wait()
        with self.assertRaises(TimeoutError):
            await guard(self.ledger, NeverAcknowledges([]), timeout=0.01).commit(place_action())
        self.assertEqual(self.ledger.pending(SCOPE)["status"], "UNKNOWN")
        await self.assert_blocked()

    async def test_known_non_application_releases_scope_but_keeps_action_identity(self):
        broker = SimulatedBroker([], outcome=ProviderCommandOutcome.KNOWN_NOT_APPLIED)
        with self.assertRaises(ProviderError):
            await guard(self.ledger, broker).commit(place_action())
        self.assertIsNone(self.ledger.pending(SCOPE))
        with self.assertRaises(CommandCommitGuardError) as error:
            await guard(self.ledger, self.broker).commit(place_action())
        self.assertEqual(error.exception.code.name, "DUPLICATE_ACTION")
        await guard(self.ledger, self.broker).commit(place_action(action_id="new-planned-attempt"))

    async def test_changed_authority_after_admission_aborts_before_dispatch(self):
        class ChangingAuthority:
            count = 0
            def allows(self, action):
                self.count += 1
                return self.count == 1
        with self.assertRaises(CommandCommitGuardError) as error:
            await guard(self.ledger, self.broker, integrity=ChangingAuthority()).commit(place_action())
        self.assertEqual(error.exception.code.name, "INTEGRITY_DENIED")
        self.assertEqual(self.broker.calls, [])
        self.assertIsNone(self.ledger.pending(SCOPE))

    async def test_task_cancellation_during_send_is_durable_unknown(self):
        started, finish = asyncio.Event(), asyncio.Event()
        class Delayed(SimulatedBroker):
            async def call(self, request):
                started.set()
                await finish.wait()
        task = asyncio.create_task(guard(self.ledger, Delayed([])).commit(place_action()))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.ledger.pending(SCOPE)["status"], "UNKNOWN")
        await self.assert_blocked()

    async def test_sender_and_reconciler_cannot_run_in_same_account_concurrently(self):
        started, finish = asyncio.Event(), asyncio.Event()
        class Delayed(SimulatedBroker):
            async def call(self, request):
                started.set()
                await finish.wait()
                return await super().call(request)
        task = asyncio.create_task(guard(self.ledger, Delayed([])).commit(place_action()))
        await started.wait()
        try:
            with self.assertRaises(LedgerAdmissionError) as error:
                await self.reconciler(ledger=SQLiteExecutionLedger(self.path)).reconcile()
            self.assertEqual(error.exception.code, "SCOPE_BUSY")
            self.assertEqual(self.broker.query_calls, [])
        finally:
            finish.set()
            await task

    async def test_durable_intent_versions_share_dispatch_fence(self):
        self.ledger.publish_intent(SCOPE, "intent-1", 1)
        authority = LedgerIntentAuthority(self.ledger, SCOPE)
        self.ledger.publish_intent(SCOPE, "intent-1", 2)
        with self.assertRaises(CommandCommitGuardError) as error:
            await guard(self.ledger, self.broker, intent=authority).commit(place_action())
        self.assertEqual(error.exception.code.name, "STALE_INTENT")
        self.assertEqual(self.broker.applied, 0)
        with self.ledger.lock_scope(SCOPE):
            with self.assertRaises(LedgerAdmissionError) as busy:
                SQLiteExecutionLedger(self.path).publish_intent(SCOPE, "intent-1", 3)
            self.assertEqual(busy.exception.code, "SCOPE_BUSY")

    async def test_actual_process_crash_after_send_retains_scope_block(self):
        ctx = multiprocessing.get_context("spawn")
        marker = str(Path(self.tmp.name) / "broker-applied.txt")
        process = ctx.Process(target=crash_worker, args=(str(self.path), marker))
        process.start()
        await asyncio.to_thread(process.join, 10)
        if process.is_alive():
            process.kill(); process.join(); self.fail("crash worker did not finish")
        self.assertEqual(process.exitcode, 17)
        self.assertTrue(Path(marker).exists())
        restarted = SQLiteExecutionLedger(self.path)
        self.assertEqual(restarted.pending(SCOPE)["status"], "DISPATCHING")
        await self.assert_blocked(ledger=restarted)
        self.assertEqual((await self.reconciler(ledger=restarted).reconcile())["state"], "CLEAN")

    async def test_two_processes_admit_only_one_broker_mutation(self):
        ctx = multiprocessing.get_context("spawn")
        barrier, queue = ctx.Barrier(2), ctx.Queue()
        processes = [ctx.Process(target=concurrent_worker, args=(str(self.path), barrier, queue, f"process-{i}")) for i in range(2)]
        for process in processes: process.start()
        for process in processes:
            await asyncio.to_thread(process.join, 15)
            if process.is_alive():
                process.kill(); process.join(); self.fail("admission worker did not finish")
            self.assertEqual(process.exitcode, 0)
        results = [queue.get(timeout=2) for _ in processes]
        queue.close(); queue.join_thread()
        self.assertEqual(sum(applied for _, applied in results), 1)
        self.assertEqual(sum(status == "ACKNOWLEDGED" for status, _ in results), 1)
        self.assertTrue(all(status in {"ACKNOWLEDGED", "SCOPE_BUSY", "SCOPE_UNRESOLVED"} for status, _ in results))

    async def test_reconciliation_persistence_failure_does_not_release_block(self):
        await guard(self.ledger, self.broker).commit(place_action())
        with patch.object(self.ledger, "record_reconciliation", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await self.reconciler().reconcile()
        await self.assert_blocked(ledger=SQLiteExecutionLedger(self.path))

    async def test_reconciliation_revision_cannot_clear_a_changed_record(self):
        await guard(self.ledger, self.broker).commit(place_action())
        with self.ledger.lock_scope(SCOPE) as lease:
            pending = self.ledger.pending(SCOPE)
            with self.assertRaises(LedgerAdmissionError):
                self.ledger.record_reconciliation(lease, pending["action_id"], pending["revision"] - 1, resolved=True, details={})
        await self.assert_blocked()

    async def test_atomic_admission_rolls_back_when_event_write_fails(self):
        with patch.object(self.ledger, "_event", side_effect=OSError("disk full")):
            with self.assertRaises(CommandCommitGuardError):
                await guard(self.ledger, self.broker).commit(place_action())
        self.assertEqual(self.ledger.entries(), [])
        self.assertIsNone(self.ledger.pending(SCOPE))
        self.assertEqual(self.broker.applied, 0)

    def test_weak_ledger_and_unbound_provider_are_rejected(self):
        class Weak:
            def append(self, entry): pass
            def entries(self): return []
        with self.assertRaises(TypeError):
            guard(Weak(), self.broker)
        class Unbound:
            async def call(self, request): pass
        with self.assertRaises(TypeError):
            guard(self.ledger, Unbound())

    def test_mismatched_account_bindings_are_rejected(self):
        other_scope = ExecutionScope("simulated", "other-synthetic-account")
        with self.assertRaises(ValueError):
            AccountBrokerPort(other_scope, self.broker)
        with self.assertRaises(ValueError):
            guard(self.ledger, self.broker, intent=LedgerIntentAuthority(self.ledger, other_scope))

    async def test_existing_ledger_never_recreates_missing_account_blocks(self):
        await guard(self.ledger, self.broker).commit(place_action())
        with self.ledger._connection() as db:
            db.execute("DROP TABLE scopes")
        with self.assertRaises(sqlite3.DatabaseError):
            SQLiteExecutionLedger(self.path)
        with self.ledger._connection() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='scopes'").fetchone())

    async def test_restart_rejects_unresolved_action_without_account_block(self):
        await guard(self.ledger, self.broker).commit(place_action())
        with self.ledger._connection() as db:
            db.execute("UPDATE scopes SET pending_action_id=NULL")
        with self.assertRaises(RuntimeError):
            SQLiteExecutionLedger(self.path)

    def test_schema_and_durable_configuration_fail_closed(self):
        with self.assertRaises(ValueError): SQLiteExecutionLedger(":memory:")
        with self.ledger._connection() as db:
            self.assertEqual(db.execute("PRAGMA synchronous").fetchone()[0], 3)
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            db.execute("PRAGMA user_version=99")
        with self.assertRaises(RuntimeError): SQLiteExecutionLedger(self.path)


if __name__ == "__main__":
    unittest.main()
