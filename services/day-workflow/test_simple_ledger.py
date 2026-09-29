import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from simple_ledger import project, validate_accounting, details, refresh
from review_scorecard import validate_event


class AccountingTests(unittest.TestCase):
    def row(self, **kw):
        r = dict(record_type='REVIEW', review_id='r1', strategy_id='s1',
                 structure='SHORT_IRON_BUTTERFLY', underlying='NIFTY', expiry='2026-09-22',
                 recorded_at_ist='2026-09-19T10:00:00+00:00',
                 prior_realized_pnl_inr='-200', broker_open_pnl_inr='500', charges_inr='20',
                 basis_status='RECONCILED', prior_realized_status='RECONCILED', charges_status='RECONCILED')
        r.update(kw)
        return r

    def with_account(self, row=None, **account):
        return dict(row or self.row(), analytics_json=json.dumps({'accounting':account}))

    def closed(self, **kw):
        return self.with_account(self.row(review_id='closed', recorded_at_ist='2026-09-20T10:00:00+00:00',
            broker_open_pnl_inr='0', structure='FLAT', **kw), cycle_id='s1', state='CLOSED',
            closed_at='2026-09-20T09:00:00+00:00', closure_source_ref='verified-contract-note', remaining_units=0)

    def test_net_and_timezone(self):
        r = project([self.row()])[0]
        self.assertEqual(r['Net P&L (INR)'], '280.00')
        self.assertEqual(r['Updated (IST)'], '2026-09-19 15:30:00')
        self.assertEqual(r['Opened (IST)'], 'Unknown')

    def test_unknown_and_provisional(self):
        for changes in [dict(charges_inr=''), dict(basis_status='incomplete'), dict(prior_realized_pnl_inr='NaN')]:
            r = project([self.row(**changes)])[0]
            self.assertEqual(r['Net P&L (INR)'], 'Unknown')
            self.assertIn('Provisional', r['Accounting status'])

    def test_exclude_non_accounting(self):
        self.assertEqual(project([self.row(record_type='FORECAST'), self.row(structure='CANDIDATE_NOT_HELD'),
                                  self.row(structure='FLAT'), self.row(structure='OTHER_POSITION')]), [])

    def test_repeated_reviews_are_one_row_not_added(self):
        rows = [self.row(), self.row(review_id='r2', recorded_at_ist='2026-09-19T11:00:00+00:00', broker_open_pnl_inr='600')]
        before = copy.deepcopy(rows)
        result = project(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['Net P&L (INR)'], '380.00')
        self.assertEqual(result[0]['Review reference'], 'r2')
        self.assertEqual(rows, before)
        self.assertEqual(project(rows), result)

    def test_correction_preserves_source_not_duplicate_summary(self):
        rows = [self.row(), self.row(review_id='r2', supersedes_review_id='r1', broker_open_pnl_inr='550')]
        self.assertEqual(len(project(rows)), 1)
        self.assertEqual(project(rows)[0]['Review reference'], 'r2')
        self.assertEqual(len(rows), 2)

    def test_late_correction_does_not_replace_newer_observation(self):
        rows = [self.row(review_as_of_ist='2026-09-19T09:00:00+00:00'),
                self.row(review_id='new', review_as_of_ist='2026-09-19T10:00:00+00:00'),
                self.row(review_id='correction', supersedes_review_id='r1',
                         recorded_at_ist='2026-09-19T11:00:00+00:00', review_as_of_ist='2026-09-19T09:00:00+00:00')]
        self.assertEqual(project(rows)[0]['Review reference'], 'new')

    def test_recenter_keeps_cycle_and_cumulative_losses(self):
        r1 = self.with_account(cycle_id='cycle-A')
        r2 = self.with_account(self.row(review_id='r2', strategy_id='changed-strikes',
             recorded_at_ist='2026-09-19T11:00:00+00:00', prior_realized_pnl_inr='-300'), cycle_id='cycle-A')
        validate_event(r2, [r1])
        result = project([r1, r2])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['Booked P&L (gross INR)'], '-300.00')
        self.assertEqual(result[0]['Net P&L (INR)'], '180.00')

    def test_same_contracts_separate_cycles(self):
        rows = [self.with_account(cycle_id='cycle-A'), self.with_account(self.row(review_id='r2'), cycle_id='cycle-B')]
        self.assertEqual(len(project(rows)), 2)
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            validate_accounting(self.row(review_id='r3'), rows)

    def test_closed_cycle_retained_even_when_structure_flat(self):
        rows = [self.row(), self.closed()]
        validate_event(rows[-1], rows[:-1])
        result = project(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['State'], 'Completed')
        self.assertEqual(result[0]['Net P&L (INR)'], '-220.00')
        self.assertEqual(result[0]['Closed (IST)'], '2026-09-20 14:30:00')
        # An unrelated verified-flat review cannot remove the completed cycle.
        self.assertEqual(project(rows+[self.row(review_id='flat', structure='FLAT')]), result)

    def test_closed_unknown_charges_stay_unknown(self):
        self.assertEqual(project([self.row(), self.closed(charges_inr='')])[0]['Net P&L (INR)'], 'Unknown')

    def test_close_recommendation_is_not_completion(self):
        r = self.row(recommendation='CLOSE', units_per_leg='0', execution_status='NOT_VERIFIED')
        self.assertEqual(project([r])[0]['State'], 'Open at last check')

    def test_closure_evidence_and_zero_checks(self):
        for field, value in [('closure_source_ref', ''), ('remaining_units', 1), ('remaining_units', False), ('closed_at', ''),
                             ('closed_at', '2026-09-21T10:00:00+00:00')]:
            row = self.closed()
            a = json.loads(row['analytics_json'])
            a['accounting'][field] = value
            row['analytics_json'] = json.dumps(a)
            with self.assertRaises(ValueError):
                validate_event(row, [self.row()])
        row = self.closed()
        row['broker_open_pnl_inr'] = '1'
        with self.assertRaises(ValueError):
            project([self.row(), row])

    def test_no_unowned_or_candidate_completion(self):
        row = self.closed()
        row['structure'] = 'SHORT_IRON_BUTTERFLY'
        with self.assertRaisesRegex(ValueError, 'previously owned'):
            validate_accounting(row, [])
        row['structure'] = 'CANDIDATE_SHORT_IRON_BUTTERFLY_NOT_HELD'
        with self.assertRaisesRegex(ValueError, 'previously owned'):
            validate_accounting(row, [self.row()])

    def test_reentry_needs_new_cycle(self):
        row = self.with_account(self.row(review_id='reentry', recorded_at_ist='2026-09-21T10:00:00+00:00'), cycle_id='s1')
        with self.assertRaisesRegex(ValueError, 'Re-entry'):
            validate_accounting(row, [self.row(), self.closed()])
        row = self.with_account(row, cycle_id='s2')
        validate_accounting(row, [self.row(), self.closed()])
        self.assertEqual(len(project([self.row(), self.closed(), row])), 2)

    def test_cross_expiry_rejected(self):
        with self.assertRaisesRegex(ValueError, 'underlying/expiry'):
            validate_accounting(self.with_account(self.row(review_id='r2', expiry='2026-09-29'), cycle_id='s1'), [self.row()])

    def test_new_review_needs_explicit_identity_legacy_continues(self):
        with self.assertRaisesRegex(ValueError, 'cycle_id'):
            validate_event(self.row(), [])
        validate_event(self.with_account(cycle_id='s1'), [])
        validate_event(self.row(review_id='r2'), [self.row()])

    def test_entry_time_cannot_be_invented_from_review_time(self):
        self.assertEqual(project([self.row()])[0]['Opened (IST)'], 'Unknown')
        with self.assertRaisesRegex(ValueError, 'Entry time'):
            validate_accounting(self.with_account(cycle_id='s1', opened_at='2026-09-18T10:00:00+00:00'), [])

    def test_correction_cannot_move_cycle(self):
        with self.assertRaisesRegex(ValueError, 'another cycle'):
            project([self.row(), self.with_account(self.row(review_id='r2', supersedes_review_id='r1'), cycle_id='other')])

    def test_historical_mark_and_no_forward_fill(self):
        self.assertIn('historical prices', project([self.row(quote_status='HISTORICAL')])[0]['Accounting status'])
        rows = [self.row(), self.row(review_id='r2', recorded_at_ist='2026-09-19T11:00:00+00:00', prior_realized_pnl_inr='')]
        self.assertEqual(project(rows)[0]['Booked P&L (gross INR)'], 'Unknown')

    def test_details_no_guessed_assignment(self):
        with patch('trade_ledger.validate_rows', return_value=[
                {'event_id':'a', 'event_type':'OPENING_BALANCE', 'cycle_id':''},
                {'event_id':'b', 'event_type':'FILL', 'cycle_id':'s1'},
                {'event_id':'c', 'event_type':'FILL', 'cycle_id':'other'}]):
            result = details([self.row()], [], 's1')
        self.assertEqual(result['unassigned_broker_event_ids'], ['a'])
        self.assertEqual([r['event_id'] for r in result['active_linked_broker_events']], ['b'])
        self.assertEqual(result['review_history_ids'], ['r1'])

    def test_no_local_fallback(self):
        with self.assertRaisesRegex(OSError, 'STORAGE_UNAVAILABLE'):
            refresh([self.row()], Path('/nonexistent-ledger'))


if __name__ == '__main__':
    unittest.main()
