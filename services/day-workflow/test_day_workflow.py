import copy
import datetime as dt
import fcntl
import json
from pathlib import Path
import tempfile
import unittest

import day_workflow as w

DAY = '2026-09-29'
AT = DAY+'T10:00:00+05:30'


def gates(open_position=False):
    return {'data_health': 'HEALTHY', 'intraday_rv_state': 'FAVOURABLE',
            'intraday_rv_confidence': 'high', 'hard_risk_gate': 'PASS',
            'news_filter_status': 'CURRENT', 'expiry_exit_gate': 'PASS',
            'recenter_gate': 'NOT_APPLICABLE'}


def candidate(cid='nifty', symbol='NIFTY'):
    spec = {'symbol': symbol, 'expiry': '2026-10-06', 'lower': 24000,
            'center': 25000, 'upper': 26000, 'lots': 1}
    margin = {'candidate': spec, 'sequence': list(w.ROLES), 'status': 'PASS',
              'scope': 'ENTRY_ONLY', 'blockers': [], 'asof': AT,
              'validUntil': DAY+'T10:00:30+05:30', 'availableFundsRupees': 50000,
              'peakRequiredRupees': 40000, 'reserveRupees': 1000,
              'headroomAfterReserveRupees': 9000,
              'stages': [{'throughLeg': r, 'totalMarginRupees': n}
                         for r, n in zip(w.ROLES, [1000, 20000, 22000, 40000])]}
    # Deliberately synthetic; not a plausible/current market recommendation.
    return {'id': cid, 'spec': spec, 'lot_size': 10, 'contracts_verified': True,
            'wide_selection_verified': True, 'evidence_ref': 'synthetic-fixture',
            'asof': AT, 'limits': dict(zip(w.ROLES, [10, 470, 10, 470])),
            'roundtrip_cost_bound_rupees': 100, 'margin': margin, 'gates': gates()}


def packet(at=AT, eid='start'):
    return {'mode': 'SHADOW', 'day': DAY, 'event_id': eid, 'asof': at,
            'session': {'trading_day_verified': True, 'market_open': True},
            'account': {'verified': True, 'synthetic': True, 'asof': at,
                        'unassigned_exposure': False, 'pending_orders': 0,
                        'quantities': dict.fromkeys(w.ROLES, 0)},
            'index_reviews': {i: {'status': 'CANDIDATES' if i == 'NIFTY' else 'NO_TRADE',
                                 'evidence_ref': 'synthetic-fixture'} for i in w.INDICES},
            'ranking_evidence_ref': 'synthetic-cross-index-ranking',
            'ranked_candidates': [candidate()], 'gates': gates()}


def owned_packet(state, at, eid, close=False):
    p = packet(at, eid)
    c = state['selected']
    p['account']['candidate_id'] = c['id']
    if close:
        p['fills'] = [{'id': 'close-'+r, 'role': r, 'candidate_id': c['id'],
                       'synthetic': True, 'quantity': c['lot_size'], 'asof': at,
                       'price': c['limits'][r], 'side': 'SELL' if w.SIGNS[r] > 0 else 'BUY'} for r in w.ROLES]
    elif not state['fills']:
        p['fills'] = [{'id': 'open-'+r, 'role': r, 'candidate_id': c['id'],
                       'synthetic': True, 'quantity': c['lot_size'], 'asof': at,
                       'price': c['limits'][r], 'side': 'BUY' if w.SIGNS[r] > 0 else 'SELL'} for r in w.ROLES]
    if not close:
        p['account']['quantities'] = {r: w.SIGNS[r]*c['lot_size'] for r in w.ROLES}
    p['valuation'] = {'asof': at, 'basis': 'ALL_CYCLE_FILLS', 'incurred_charges_rupees': 40,
                      'remaining_exit_cost_bound_rupees': 0 if close else 60,
                      'quotes': {r: {'asof': at, 'bid': c['limits'][r], 'ask': c['limits'][r]+1,
                                      'bid_size': 10, 'ask_size': 10} for r in w.ROLES}}
    return p


class WorkflowTest(unittest.TestCase):
    def start(self):
        return w.transition(w.initial(DAY), packet())

    def opened(self):
        s = self.start()
        return w.transition(s, owned_packet(s, DAY+'T10:01:00+05:30', 'filled'))

    def test_complete_cycle_and_no_reentry(self):
        s = self.opened()
        self.assertEqual(s['phase'], 'OPEN')
        self.assertEqual(s['net_liquidation_pnl_rupees'], -120)
        p = owned_packet(s, DAY+'T10:16:00+05:30', 'risk')
        p['gates']['intraday_rv_state'] = 'UNFAVOURABLE'
        s = w.transition(s, p)
        self.assertEqual(s['phase'], 'EXIT_PENDING')
        s = w.transition(s, owned_packet(s, DAY+'T10:17:00+05:30', 'closed', True))
        self.assertEqual(s['phase'], 'DONE')
        self.assertEqual(s['net_liquidation_pnl_rupees'], -40)
        self.assertTrue(all(not j['enabled'] for j in s['jobs'].values()))
        p = packet(DAY+'T10:18:00+05:30', 'again')
        p['account']['candidate_id'] = s['selected']['id']
        s = w.transition(s, p)
        self.assertEqual(len([e for e in s['outbox'] if e['kind'] == 'SIMULATE_ENTRY']), 1)

    def test_duplicate_start_is_idempotent_and_changed_id_rejected(self):
        s = self.start()
        self.assertEqual(s, w.transition(s, packet()))
        p = packet(); p['ranked_candidates'] = []
        with self.assertRaisesRegex(ValueError, 'different content'):
            w.transition(s, p)

    def test_loss_threshold_includes_fills_quotes_and_costs(self):
        s = self.opened()
        p = owned_packet(s, DAY+'T10:16:00+05:30', 'loss')
        for r in ('putBody', 'callBody'):
            p['valuation']['quotes'][r]['ask'] = 520
        s = w.transition(s, p)
        self.assertEqual(s['net_liquidation_pnl_rupees'], -1100)
        self.assertEqual(s['phase'], 'EXIT_PENDING')

    def test_deadline_exit_does_not_depend_on_news_pnl_or_margin(self):
        s = self.opened()
        p = owned_packet(s, DAY+'T14:45:00+05:30', 'deadline')
        del p['gates']; del p['valuation']; del p['ranked_candidates']
        s = w.transition(s, p)
        self.assertEqual(s['phase'], 'EXIT_PENDING')
        p = owned_packet(s, DAY+'T15:00:00+05:30', 'breach')
        s = w.transition(s, p)
        self.assertEqual(len([e for e in s['outbox'] if e['kind'] == 'SIMULATE_EXIT']), 1)
        self.assertTrue(any('deadline-breach' in e['id'] for e in s['outbox']))

    def test_partial_and_pending_require_recovery(self):
        for status in ('PARTIAL', 'TIMEOUT', 'UNKNOWN', 'REJECTED'):
            s = self.start()
            p = packet(DAY+'T10:01:00+05:30', status)
            p['account']['candidate_id'] = 'nifty'; p['execution_status'] = status
            s = w.transition(s, p)
            self.assertEqual(s['phase'], 'RECOVERY_REQUIRED')
            self.assertEqual(len([e for e in s['outbox'] if e['kind'] == 'SIMULATE_ENTRY']), 1)

    def test_uncovered_and_oversize_inventory_rejected(self):
        for qty in (11,):
            s = self.start(); p = owned_packet(s, DAY+'T10:01:00+05:30', 'bad')
            for f in p['fills']: f['quantity'] = qty
            p['account']['quantities'] = {r: w.SIGNS[r]*qty for r in w.ROLES}
            with self.assertRaisesRegex(ValueError, 'one lot'):
                w.transition(s, p)
        s = self.start(); p = owned_packet(s, DAY+'T10:01:00+05:30', 'naked')
        p['fills'] = [f for f in p['fills'] if f['role'] != 'putWing']
        p['account']['quantities']['putWing'] = 0
        with self.assertRaisesRegex(ValueError, 'Uncovered'):
            w.transition(s, p)

    def test_stale_margin_sequence_and_missing_gates_fail_closed(self):
        for mutate in (lambda c: c['margin'].update(sequence=['putWing','callWing','putBody','callBody']),
                       lambda c: c['margin'].update(asof=DAY+'T09:58:00+05:30'),
                       lambda c: c['gates'].pop('hard_risk_gate'),
                       lambda c: c['margin'].update(reserveRupees=0),
                       lambda c: c['spec'].update(lots=2),
                       lambda c: c['limits'].update(putBody=400),
                       lambda c: c['gates'].update(intraday_rv_state='MARGINAL')):
            p = packet(); mutate(p['ranked_candidates'][0])
            self.assertEqual(w.transition(w.initial(DAY), p)['phase'], 'NO_TRADE')

    def test_all_indices_required_and_ranked_survivor_selected(self):
        p = packet(); del p['index_reviews']['SENSEX']
        with self.assertRaisesRegex(ValueError, 'three indices'):
            w.transition(w.initial(DAY), p)
        p = packet(); bad = candidate('bad'); bad['spec']['lots'] = 2
        p['ranked_candidates'].insert(0, bad)
        s = w.transition(w.initial(DAY), p)
        self.assertEqual(s['selected']['id'], 'nifty')
        self.assertEqual(len(s['rejections']), 1)

    def test_missing_account_is_not_flat(self):
        p = packet(); p['account']['verified'] = False
        with self.assertRaisesRegex(ValueError, 'not flatness'):
            w.transition(w.initial(DAY), p)

    def test_stale_quote_and_missing_costs_do_not_hold(self):
        for mutate in (lambda p: p['valuation']['quotes']['putBody'].update(asof=AT),
                       lambda p: p['valuation'].pop('incurred_charges_rupees')):
            s = self.opened(); p = owned_packet(s, DAY+'T10:16:00+05:30', 'bad')
            mutate(p)
            with self.assertRaises((ValueError, KeyError)):
                w.transition(s, p)

    def test_marginal_shortens_review_missing_hf_alone_does_not_exit(self):
        for rv, minute in [('MARGINAL', '10:26'), ('INSUFFICIENT_DATA', '10:31')]:
            s = self.opened(); p = owned_packet(s, DAY+'T10:16:00+05:30', 'rv')
            p['gates']['intraday_rv_state'] = rv
            s = w.transition(s, p)
            self.assertEqual(s['phase'], 'OPEN')
            self.assertIn(minute, s['jobs']['review']['at'])

    def test_after_close_and_next_day_never_start_or_pretend_exit(self):
        s = self.opened(); p = owned_packet(s, DAY+'T15:40:00+05:30', 'late')
        p['session']['market_open'] = False
        self.assertEqual(w.transition(s, p)['phase'], 'LOCKED_OVERNIGHT')
        p = owned_packet(s, '2026-09-30T10:00:00+05:30', 'next')
        self.assertEqual(w.transition(s, p)['phase'], 'RECOVERY_REQUIRED')

    def test_deadline_jobs_exist_before_entry_intent(self):
        s = self.start()
        self.assertEqual(set(s['jobs']), {'review', 'deadline', 'flat_check'})
        self.assertEqual(s['outbox'][-1]['kind'], 'SIMULATE_ENTRY')

    def test_live_mode_and_ledger_storage_rejected(self):
        p = packet(); p['mode'] = 'LIVE'
        with self.assertRaisesRegex(ValueError, 'LIVE'):
            w.transition(w.initial(DAY), p)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'ledger'):
                w.run(Path(d)/'ledger', packet())

    def test_restart_replays_no_duplicate_and_preserves_intent_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            s = w.run(d, packet())
            self.assertEqual(s, w.run(d, packet()))
            p = packet(DAY+'T10:01:00+05:30', 'bad'); p['account']['verified'] = False
            s = w.run(d, p)
            self.assertEqual(s['phase'], 'ENTRY_PENDING')
            self.assertIn('last_blocker', s)
            p = owned_packet(s, DAY+'T10:02:00+05:30', 'fixed')
            s = w.run(d, p)
            self.assertEqual(s['phase'], 'OPEN')
            self.assertNotIn('last_blocker', s)
            self.assertEqual(json.loads((Path(d)/(DAY+'.json')).read_text()), s)

    def test_changed_duplicate_fill_and_out_of_order_rejected(self):
        s = self.opened(); p = owned_packet(s, DAY+'T10:16:00+05:30', 'badfill')
        f = copy.deepcopy(s['fills']['open-putWing']); f['price'] += 1; p['fills'] = [f]
        with self.assertRaisesRegex(ValueError, 'Changed duplicate fill'):
            w.transition(s, p)
        p = owned_packet(s, AT, 'old')
        with self.assertRaisesRegex(ValueError, 'Out-of-order'):
            w.transition(s, p)

    def test_pause_hands_off_and_requires_explicit_resume(self):
        s = self.opened()
        p = owned_packet(s, DAY+'T10:05:00+05:30', 'pause'); p['command'] = 'PAUSE'
        s = w.transition(s, p)
        self.assertEqual(s['phase'], 'PAUSED')
        self.assertTrue(all(not j['enabled'] for j in s['jobs'].values()))
        p = owned_packet(s, DAY+'T10:16:00+05:30', 'ordinary')
        s = w.transition(s, p)
        self.assertEqual(s['phase'], 'PAUSED')
        p = owned_packet(s, DAY+'T10:17:00+05:30', 'resume'); p['command'] = 'RESUME'
        s = w.transition(s, p)
        self.assertEqual(s['phase'], 'OPEN')
        self.assertTrue(s['jobs']['deadline']['enabled'])

    def test_decreasing_cumulative_charges_block(self):
        s = self.opened(); p = owned_packet(s, DAY+'T10:16:00+05:30', 'costs')
        p['valuation']['incurred_charges_rupees'] = 0
        with self.assertRaisesRegex(ValueError, 'charges decreased'):
            w.transition(s, p)

    def test_pending_orders_at_deadline_alert_not_false_done(self):
        s = self.opened(); p = owned_packet(s, DAY+'T15:00:00+05:30', 'pending')
        p['account']['pending_orders'] = 1
        s = w.transition(s, p)
        self.assertEqual(s['phase'], 'RECOVERY_REQUIRED')
        self.assertTrue(any('deadline-breach' in e['id'] for e in s['outbox']))

    def test_overlap_lock_prevents_second_writer(self):
        with tempfile.TemporaryDirectory() as d:
            with (Path(d)/'workflow.lock').open('a') as f:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    w.run(d, packet())

    def test_early_exit_does_not_need_optional_journal_or_margin(self):
        s = self.opened(); p = owned_packet(s, DAY+'T10:05:00+05:30', 'close')
        p['command'] = 'CLOSE_AND_STOP'; del p['valuation']; del p['gates']
        s = w.transition(s, p)
        self.assertEqual(s['phase'], 'EXIT_PENDING')

    def test_unresolved_prior_day_cannot_be_bypassed_by_new_run(self):
        with tempfile.TemporaryDirectory() as d:
            w.run(d, packet())
            p = packet('2026-09-30T10:00:00+05:30', 'tomorrow'); p['day'] = '2026-09-30'
            s = w.run(d, p)
            self.assertIn('Another day', s['last_blocker']['reason'])
            self.assertFalse(s['entry_requested'])


if __name__ == '__main__':
    unittest.main()
