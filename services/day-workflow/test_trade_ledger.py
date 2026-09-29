"""Synthetic-only acceptance tests. No fixture is a real trade or live ledger entry."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import trade_ledger as ledger


def fill(fill_id="FILL-A", units="65", price="10", **changes):
    row = dict(event_type="FILL", event_time="2026-09-18T15:20:00+05:30", trading_date="2026-09-18", broker="TEST_BROKER", account_alias="SYNTHETIC_ONLY", source_record_id=fill_id, source_ref="synthetic-fixture.json", source_sha256=hashlib.sha256(b"SYNTHETIC TEST ONLY").hexdigest(), source_kind="BROKER_EXPORT", provenance="OBSERVED", exchange="NSE", segment="FNO", security_id="TEST-CONTRACT", symbol="TEST-CE", underlying="TEST_INDEX", expiry="2026-09-22", strike="25000", option_type="CE", product="MARGIN", broker_order_id="ORDER-1", broker_fill_id=fill_id, side="BUY" if int(units) > 0 else "SELL", quantity_units=units, lot_size_units="65", price_per_unit=price, currency="INR")
    row.update(changes)
    return row


def baseline(units="-130", **changes):
    row = fill()
    row.update(event_type="OPENING_BALANCE", source_record_id="baseline-test", event_time="2026-09-19T10:00:00+05:30", trading_date="2026-09-19", quantity_units=units)
    for key in ("broker_fill_id", "broker_order_id", "side", "price_per_unit"):
        row.pop(key)
    row.update(changes)
    return row


def cost(component="TOTAL", amount="-12.5", **changes):
    row = {k: v for k, v in fill().items() if k in {"event_time", "trading_date", "broker", "account_alias", "source_ref", "source_sha256", "source_kind", "provenance", "currency"}}
    row.update(event_type="COST", source_record_id="contract-note-cost-" + component, source_kind="CONTRACT_NOTE", cost_component=component, gross_cashflow=amount)
    row.update(changes)
    return row


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "tradelog.csv"

    def tearDown(self):
        self.temp.cleanup()

    def test_header_init_repeat_zero_rows_preserves_exact_bytes(self):
        self.assertEqual(ledger.import_rows(self.path, [])['total_rows'], 0)
        before = self.path.read_bytes()
        mtime = self.path.stat().st_mtime_ns
        self.assertEqual(ledger.import_rows(self.path, [])['added'], 0)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(mtime, self.path.stat().st_mtime_ns)

    def test_repeat_fill_deduplicates_across_different_exports(self):
        ledger.import_rows(self.path, [fill()])
        again = fill(source_ref="new-export.json", source_record_id="different-row-id", source_sha256="a" * 64)
        before = self.path.read_bytes()
        result = ledger.import_rows(self.path, [again, again])
        self.assertEqual(result["duplicates"], 2)
        self.assertEqual(result["added"], 0)
        self.assertEqual(before, self.path.read_bytes())

    def test_partial_fills_same_order_are_distinct_and_not_rounded_to_lots(self):
        ledger.import_rows(self.path, [fill("PART-1", "20"), fill("PART-2", "45")])
        rows = ledger.read_ledger(self.path)
        self.assertEqual(len(rows), 2)
        report = ledger.summary(rows)
        self.assertEqual(report['positions'][0]['recorded_execution_delta_units'], "65")
        self.assertIsNone(report['positions'][0]['derived_units_since_baseline'])
        self.assertEqual(report['recorded_cashflows_by_currency']['INR']['gross_execution_and_settlement'], "-650")

    def test_reused_security_id_for_different_expiry_remains_separate_contract(self):
        later = fill('LATER-FILL', event_time='2026-10-01T10:00:00+05:30', trading_date='2026-10-01', expiry='2026-10-06')
        ledger.import_rows(self.path, [fill(), later])
        report = ledger.summary(ledger.read_ledger(self.path))
        self.assertEqual(len(report['positions']), 2)
        self.assertEqual({p['expiry'] for p in report['positions']}, {'2026-09-22', '2026-10-06'})
        self.assertTrue(all(p['recorded_execution_delta_units'] == '65' for p in report['positions']))

    def test_conflicting_duplicate_aborts_entire_batch(self):
        ledger.import_rows(self.path, [fill()])
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ledger.LedgerError, "Conflicting duplicate"):
            ledger.import_rows(self.path, [fill("NEW"), fill(price="11")])
        self.assertEqual(before, self.path.read_bytes())

    def test_explicit_correction_preserves_original_without_double_cashflow(self):
        ledger.import_rows(self.path, [fill()])
        old = ledger.read_ledger(self.path)[0]
        revised = fill(price="11", source_revision="2", supersedes_event_id=old['event_id'])
        ledger.import_rows(self.path, [revised])
        self.assertEqual(len(ledger.read_ledger(self.path)), 2)
        report = ledger.summary(ledger.read_ledger(self.path))
        self.assertEqual(report['active_rows'], 1)
        self.assertEqual(report['recorded_cashflows_by_currency']['INR']['gross_execution_and_settlement'], "-715")
        self.assertEqual(ledger.import_rows(self.path, [revised])['added'], 0)

    def test_same_identity_new_revision_without_correction_rejected(self):
        ledger.import_rows(self.path, [fill()])
        with self.assertRaisesRegex(ledger.LedgerError, "Economic identity"):
            ledger.import_rows(self.path, [fill(source_revision="2")])

    def test_cost_repeat_and_total_itemized_double_count_rejected(self):
        ledger.import_rows(self.path, [cost()])
        self.assertEqual(ledger.import_rows(self.path, [cost()])['duplicates'], 1)
        with self.assertRaisesRegex(ledger.LedgerError, "double-count"):
            ledger.import_rows(self.path, [cost("BROKERAGE", "-5")])
        report = ledger.summary(ledger.read_ledger(self.path))
        self.assertEqual(report['recorded_cashflows_by_currency']['INR']['recorded_cost_cashflow'], "-12.5")

    def test_cost_correction_is_replacement_not_extra_cost(self):
        ledger.import_rows(self.path, [cost()])
        original = ledger.read_ledger(self.path)[0]
        ledger.import_rows(self.path, [cost(amount="-15", source_revision="2", supersedes_event_id=original['event_id'])])
        self.assertEqual(ledger.summary(ledger.read_ledger(self.path))['recorded_cashflows_by_currency']['INR']['recorded_cost_cashflow'], "-15")

    def test_carry_opening_unsettled_unknown_basis_has_no_cashflow_or_pnl(self):
        ledger.import_rows(self.path, [baseline()])
        report = ledger.summary(ledger.read_ledger(self.path))
        self.assertEqual(report['positions'][0]['derived_units_since_baseline'], "-130")
        self.assertEqual(report['positions'][0]['basis_status'], "UNKNOWN")
        self.assertEqual(report['recorded_cashflows_by_currency'], {})
        self.assertIsNone(report['realized_pnl'])
        self.assertEqual(len(report['unassigned_event_ids']), 1)

    def test_carry_cannot_fabricate_execution_or_reconciled_basis(self):
        with self.assertRaisesRegex(ledger.LedgerError, "never synthetic"):
            ledger.import_rows(self.path, [baseline(price_per_unit="10")])
        with self.assertRaisesRegex(ledger.LedgerError, "basis_evidence_ref"):
            ledger.import_rows(self.path, [baseline(basis_status="RECONCILED")])

    def test_historical_fills_not_added_twice_to_opening_inventory(self):
        ledger.import_rows(self.path, [fill(units="-130"), baseline(), fill("MONDAY", "65", event_time="2026-09-21T09:30:00+05:30", trading_date="2026-09-21")])
        state = ledger.summary(ledger.read_ledger(self.path))['positions'][0]
        self.assertEqual(state['derived_units_since_baseline'], "-65")
        self.assertEqual(state['executions_at_or_before_baseline_not_readded'], 1)

    def test_settlement_closes_inventory_but_not_inferred_profit(self):
        settled = fill("SETTLE", "130", price="8", event_type="SETTLEMENT", event_time="2026-09-22T15:30:00+05:30", trading_date="2026-09-22")
        for key in ('broker_fill_id', 'broker_order_id', 'side'):
            settled.pop(key)
        ledger.import_rows(self.path, [baseline(), settled])
        report = ledger.summary(ledger.read_ledger(self.path))
        self.assertEqual(report['positions'][0]['derived_units_since_baseline'], "0")
        self.assertEqual(report['recorded_cashflows_by_currency']['INR']['gross_execution_and_settlement'], "-1040")
        self.assertIsNone(report['realized_pnl'])

    def test_snapshot_matching_does_not_claim_inventory_completeness(self):
        snapshot = baseline("-130", event_type="POSITION_SNAPSHOT", source_record_id="snapshot-test", event_time="2026-09-21T09:30:00+05:30", trading_date="2026-09-21")
        ledger.import_rows(self.path, [baseline(), snapshot])
        report = ledger.summary(ledger.read_ledger(self.path))
        self.assertTrue(report['positions'][0]['snapshot_quantity_match'])
        self.assertIn('completeness is not inferred', report['inventory_status'])

    def test_snapshot_alone_is_observation_not_opening_or_fill(self):
        ledger.import_rows(self.path, [baseline(event_type="POSITION_SNAPSHOT")])
        state = ledger.summary(ledger.read_ledger(self.path))['positions'][0]
        self.assertEqual(state['latest_observed_quantity_units'], '-130')
        self.assertIsNone(state['derived_units_since_baseline'])

    def test_explicit_strategy_assignment_never_guesses_grouping(self):
        ledger.import_rows(self.path, [fill()])
        target = ledger.read_ledger(self.path)[0]['event_id']
        assignment = {k: v for k, v in fill().items() if k in {'event_time', 'trading_date', 'broker', 'account_alias', 'source_ref', 'source_sha256'}}
        assignment.update(event_type='ASSIGNMENT', source_record_id='assignment-test', source_kind='USER_RECORD', provenance='USER_RECORDED', reference_event_id=target, strategy_id='CONFIRMED-STRATEGY', cycle_id='CONFIRMED-CYCLE', strategy_version='1', leg_id='LEG-1', lifecycle_role='ENTRY', linkage_provenance='USER_CONFIRMED')
        ledger.import_rows(self.path, [assignment])
        self.assertEqual(ledger.summary(ledger.read_ledger(self.path))['unassigned_event_ids'], [])
        ledger.import_rows(self.path, [fill(price='11', source_revision='2', supersedes_event_id=target)])
        report = ledger.summary(ledger.read_ledger(self.path))
        self.assertEqual(len(report['unassigned_event_ids']), 1)
        self.assertEqual(len(report['orphaned_assignment_event_ids']), 1)

    def test_void_preserves_original_and_removes_economic_effect(self):
        ledger.import_rows(self.path, [cost()])
        target = ledger.read_ledger(self.path)[0]['event_id']
        void = cost()
        for key in ('currency', 'cost_component', 'gross_cashflow'):
            void.pop(key)
        void.update(event_type='VOID', source_record_id='void-cost-test', supersedes_event_id=target)
        ledger.import_rows(self.path, [void])
        report = ledger.summary(ledger.read_ledger(self.path))
        self.assertEqual(report['rows'], 2)
        self.assertEqual(report['active_rows'], 0)
        self.assertEqual(report['recorded_cashflows_by_currency'], {})

    def test_bad_sign_nonfinite_timestamp_and_inferred_provenance_rejected(self):
        for bad in [fill(side="SELL"), fill(price="NaN"), fill(event_time="2026-09-18T15:00:00"), fill(provenance="INFERRED"), fill(quantity_lots="2")]:
            with self.subTest(row=bad), self.assertRaises(ledger.LedgerError):
                ledger.import_rows(self.path, [bad])
        self.assertFalse(self.path.exists())

    def test_existing_incompatible_csv_is_never_overwritten(self):
        self.path.write_text("legacy,header\n1,2\n")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ledger.LedgerError, 'schema mismatch'):
            ledger.import_rows(self.path, [])
        self.assertEqual(before, self.path.read_bytes())

    def test_concurrent_cli_imports_are_serialized_and_idempotent(self):
        fixture = Path(self.temp.name) / "events.json"
        fixture.write_text(json.dumps([fill()]))
        cmd = [sys.executable, str(Path(ledger.__file__)), "--ledger", str(self.path), "import", str(fixture)]
        processes = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
        outputs = [p.communicate(timeout=10) for p in processes]
        self.assertEqual([p.returncode for p in processes], [0] * 4, outputs)
        self.assertEqual(sum(json.loads(out)['added'] for out, err in outputs), 1)
        self.assertEqual(len(ledger.read_ledger(self.path)), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
