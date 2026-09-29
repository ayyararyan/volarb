#!/usr/bin/env python3
"""Offline day-workflow runner. No network, broker orders, real jobs or live ledger writes.

The output is a durable SHADOW outbox for integration testing, not authorization.
Normalized research comes from the adopted controller, never a replacement model.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')
INDICES = {'NIFTY', 'BANKNIFTY', 'SENSEX'}
ROLES = ('putWing', 'putBody', 'callWing', 'callBody')
SIGNS = dict(zip(ROLES, (1, -1, 1, -1)))
# Publication copy resolves the controller within this checkout, not the host Drive.
SOURCE = Path(__file__).resolve().parents[2] / 'skill/butterfly-market-outlook/scripts/decision_controller.py'
POLICY = {'mode': 'SHADOW', 'lots': 1, 'daily_loss_rupees': 1000,
          'reserve_rupees': 1000, 'max_cycles': 1,
          'entry_cutoff': '14:30', 'exit_start': '14:45', 'flat_deadline': '15:00',
          'review_minutes': 15, 'marginal_review_minutes': 10}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def number(x):
    need(type(x) in (int, float) and math.isfinite(x), 'Finite numeric evidence required')
    return x


def stamp(x):
    value = dt.datetime.fromisoformat(x.replace('Z', '+00:00'))
    need(value.tzinfo is not None, 'Timezone required')
    return value.astimezone(IST)


def fresh(x, at, seconds=30):
    need(0 <= (at-stamp(x)).total_seconds() <= seconds, 'Stale/future evidence')


def digest(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, allow_nan=False).encode()).hexdigest()


def initial(day):
    dt.date.fromisoformat(day)
    return {'version': 1, 'mode': 'SHADOW', 'day': day, 'run_id': 'shadow-'+day,
            'policy': copy.deepcopy(POLICY), 'phase': 'READY', 'selected': None,
            'fills': {}, 'events': {}, 'outbox': [], 'jobs': {}, 'reviews': [],
            'entry_requested': False, 'exit_requested': False, 'last_at': None}


def emit(s, kind, key, data):
    eid = s['run_id']+':'+key
    prior = next((e for e in s['outbox'] if e['id'] == eid), None)
    if prior is None:
        s['outbox'].append({'id': eid, 'kind': kind, 'mode': 'SHADOW', 'payload': data})
    return eid


def schedule(s, key, at):
    # These are simulation records, NOT Gateway jobs or protective monitoring.
    s['jobs'][key] = {'at': at.isoformat(), 'enabled': True, 'simulated': True}
    emit(s, 'SCHEDULE_SIMULATION', key+':'+at.isoformat(), s['jobs'][key])


def stop_jobs(s):
    for key, job in s['jobs'].items():
        if job['enabled']:
            job['enabled'] = False
            emit(s, 'CANCEL_SIMULATED_JOB', 'cancel:'+key, {'key': key})


def clock_on(s, hhmm):
    return stamp(s['day']+'T'+hhmm+':00+05:30')


def controller(gates, at):
    """Load the existing controller; virtual clock is isolated to this module instance.

    This clock substitution is SHADOW-only, enabling historical synthetic fixtures.
    """
    spec = importlib.util.spec_from_file_location('_shadow_volarb_controller', SOURCE)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz or dt.timezone.utc)
    module.datetime = Clock
    return module.decide(gates)


def gate_packet(raw, candidate):
    # Do not let the upstream controller's absent-field PASS defaults approve risk.
    need(isinstance(raw, dict), 'Missing normalized controller evidence')
    for key in ('data_health', 'intraday_rv_state', 'intraday_rv_confidence',
                'hard_risk_gate', 'news_filter_status'):
        need(key in raw, 'Missing controller field: '+key)
    need(raw['data_health'] in {'HEALTHY', 'DEGRADED', 'STALE', 'INVALID'}, 'Unknown data health')
    need(raw['hard_risk_gate'] in {'PASS', 'BLOCK', 'FAIL'}, 'Unverified hard risk gate')
    need(raw['news_filter_status'] in {'CURRENT', 'STALE_CALIBRATION'}, 'News evidence unavailable')
    need(raw['intraday_rv_state'] in {'FAVOURABLE', 'MARGINAL', 'UNFAVOURABLE', 'INSUFFICIENT_DATA'}, 'Unknown RV state')
    need(raw['intraday_rv_confidence'] in {'low', 'medium', 'high'}, 'Unknown RV confidence')
    out = copy.deepcopy(raw)
    out.update(mode='CANDIDATE' if candidate else 'OPEN_POSITION',
               branch='CANDIDATE_INTRADAY' if candidate else 'OPEN_INTRADAY')
    if not candidate:
        need(raw.get('expiry_exit_gate') in {'PASS', 'BLOCK', 'FAIL', 'EXIT', 'NOT_APPLICABLE'}, 'Expiry gate unverified')
        need(raw.get('recenter_gate') == 'NOT_APPLICABLE', 'Automatic recenter not enabled')
    return out


def candidate_check(c, at):
    spec = c['spec']
    need(set(spec) == {'symbol', 'expiry', 'lower', 'center', 'upper', 'lots'}, 'Exact geometry required')
    need(spec['symbol'] in INDICES and type(spec['lots']) is int and spec['lots'] == 1, 'One lot total only')
    need(dt.date.fromisoformat(spec['expiry']) >= at.date(), 'Expired contract')
    low, body, high = [number(spec[k]) for k in ('lower', 'center', 'upper')]
    need(0 < low < body < high, 'Invalid geometry')
    lot = number(c['lot_size'])
    need(type(lot) is int and lot > 0, 'Verified integer contract lot size required')
    need(c.get('contracts_verified') is True and c.get('wide_selection_verified') is True,
         'Contract/wide-selection evidence required')
    need(bool(c.get('evidence_ref')), 'Missing local evidence reference')
    fresh(c['asof'], at)
    need(set(c['limits']) == set(ROLES), 'Four entry price bounds required')
    for role in ROLES:
        need(number(c['limits'][role]) > 0, 'Positive price bounds required')
    # Worst admitted credit from order limits, not midpoint or optimistic fills.
    credit = sum(-SIGNS[r]*c['limits'][r] for r in ROLES)
    costs = number(c['roundtrip_cost_bound_rupees'])
    need(costs >= 0 and 0 < credit < min(body-low, high-body), 'Cost bound and valid credit required')
    max_loss = max(0, (max(body-low, high-body)-credit)*lot) + costs
    need(max_loss <= POLICY['daily_loss_rupees'], 'Payoff loss plus cost bound exceeds ₹1,000')
    margin = c['margin']
    need(margin.get('candidate') == spec and margin.get('sequence') == list(ROLES), 'Margin geometry/sequence mismatch')
    need(margin.get('reserveRupees') == 1000, 'Require ₹1,000 cash reserve')
    stages = margin.get('stages', [])
    need(len(stages) == 4 and [v.get('throughLeg') for v in stages] == list(ROLES), 'Four exact sequence stages required')
    totals = [number(v['totalMarginRupees']) for v in stages]
    need(min(totals) >= 0 and max(totals) == margin.get('peakRequiredRupees'), 'Invalid peak margin')
    gates = gate_packet(c['gates'], True)
    gates.update(candidate_count=1, candidate_ids=[c['id']], candidate_specs={c['id']: spec},
                 candidate_margin_checks={c['id']: margin})
    decision = controller(gates, at)
    need(decision['action'] == 'CANDIDATES', 'Controller rejected: '+decision['terminal_gate'])
    return max_loss


def ingest_fills(s, p):
    for fill in p.get('fills', []):
        need(s['selected'] is not None and s['entry_requested'], 'Unowned fill')
        need(fill.get('synthetic') is True and fill.get('candidate_id') == s['selected']['id'], 'Only bound synthetic receipts accepted')
        need(fill.get('role') in ROLES and fill.get('side') in {'BUY', 'SELL'}, 'Invalid fill')
        qty, price = number(fill['quantity']), number(fill['price'])
        need(type(qty) is int and qty > 0 and price > 0, 'Invalid fill units/price')
        need(isinstance(fill.get('id'), str) and bool(fill['id']), 'Fill ID required')
        fresh(fill['asof'], stamp(p['asof']), 86400)
        need(stamp(fill['asof']).date().isoformat() == s['day'], 'Fill outside mandate day')
        old = s['fills'].get(fill['id'])
        need(old is None or old == fill, 'Changed duplicate fill')
        s['fills'][fill['id']] = copy.deepcopy(fill)


def quantities(s):
    result = dict.fromkeys(ROLES, 0)
    for f in s['fills'].values():
        result[f['role']] += f['quantity']*(1 if f['side'] == 'BUY' else -1)
    return result


def account_check(s, p, at):
    a = p['account']
    need(a.get('verified') is True and a.get('synthetic') is True, 'Synthetic verified account required; failure is not flatness')
    fresh(a['asof'], at)
    need(a.get('unassigned_exposure') is False, 'Unassigned exposure blocks workflow')
    need(type(a.get('pending_orders')) is int and a['pending_orders'] >= 0, 'Unknown order status')
    need(set(a['quantities']) == set(ROLES), 'All four role quantities required')
    need(all(type(v) is int for v in a['quantities'].values()), 'Integer account units required')
    if s['selected']:
        need(a.get('candidate_id') == s['selected']['id'], 'Account/selected geometry mismatch')
    need(a['quantities'] == quantities(s), 'Account differs from deduplicated fill evidence')
    return a


def liquidation_pnl(s, p, at):
    q = quantities(s)
    cash = sum((-1 if f['side'] == 'BUY' else 1)*f['quantity']*f['price'] for f in s['fills'].values())
    value = p['valuation']
    fresh(value['asof'], at)
    charges = number(value['incurred_charges_rupees'])
    exit_cost = number(value['remaining_exit_cost_bound_rupees'])
    need(charges >= 0 and exit_cost >= 0, 'Charges/exit-cost bounds missing')
    need(charges >= s.get('incurred_charges_rupees', 0), 'Cumulative charges decreased; reconciliation required')
    s['incurred_charges_rupees'] = charges
    need(value.get('basis') == 'ALL_CYCLE_FILLS', 'P&L must include the whole cycle')
    for role, qty in q.items():
        if qty == 0:
            continue
        quote = value['quotes'][role]
        fresh(quote['asof'], at)
        bid, ask = number(quote['bid']), number(quote['ask'])
        need(0 < bid <= ask, 'Invalid executable book')
        need(number(quote['bid_size' if qty > 0 else 'ask_size']) >= abs(qty), 'Insufficient closing depth')
        cash += qty*(bid if qty > 0 else ask)
    return round(cash-charges-exit_cost, 2)


def exit_intent(s, reason):
    if not s['exit_requested']:
        s['exit_requested'] = True
        emit(s, 'SIMULATE_EXIT', 'exit', {'candidate_id': s['selected']['id'],
             'sequence': list(reversed(ROLES)), 'reason': reason,
             'requires_fresh_exit_limits': True, 'never_market_fallback': True})
    s['phase'] = 'EXIT_PENDING'


def transition(state, p):
    need(state.get('mode') == 'SHADOW' and p.get('mode') == 'SHADOW', 'LIVE EXECUTION IS NOT IMPLEMENTED OR AUTHORIZED')
    need(state['policy'] == POLICY, 'Policy changed; explicit migration required')
    eid = p.get('event_id')
    need(isinstance(eid, str) and bool(eid), 'Event ID required')
    if eid in state['events']:
        need(state['events'][eid] == digest(p), 'Event ID reused with different content')
        return copy.deepcopy(state)
    s = copy.deepcopy(state)
    s.pop('last_blocker', None)
    at = stamp(p['asof'])
    if s['last_at']:
        need(at >= stamp(s['last_at']), 'Out-of-order event')
    s['last_at'] = at.isoformat()
    s['events'][eid] = digest(p)
    ingest_fills(s, p)
    a = account_check(s, p, at)
    exposure = any(a['quantities'].values())
    if p.get('command') == 'PAUSE':
        s['paused'] = True
        s['phase'] = 'PAUSED'
        emit(s, 'ALERT_SIMULATION', 'pause:'+eid,
             {'reason': 'Operator handoff; pausing does not flatten exposure or cancel pending orders',
              'exposure': exposure, 'pending_orders': a['pending_orders']})
        stop_jobs(s)
        return s
    if s.get('paused'):
        if p.get('command') not in {'RESUME', 'CLOSE_AND_STOP'}:
            return s
        s['paused'] = False
        if exposure:
            schedule(s, 'deadline', max(at, clock_on(s, POLICY['exit_start'])))
            schedule(s, 'flat_check', max(at, clock_on(s, POLICY['flat_deadline'])))
    if at.date().isoformat() != s['day']:
        s['phase'] = 'RECOVERY_REQUIRED' if exposure or a['pending_orders'] else 'EXPIRED'
        emit(s, 'ALERT_SIMULATION', 'date-expired', {'reason': 'Mandate expired; no new entry or automatic next-day trading'})
        return s
    if p.get('execution_status') in {'UNKNOWN', 'TIMEOUT', 'PARTIAL', 'REJECTED'} or a['pending_orders']:
        s['phase'] = 'RECOVERY_REQUIRED'
        emit(s, 'ALERT_SIMULATION', 'recovery:'+eid, {'reason': 'Reconcile pending/partial/uncertain execution; never blindly resubmit'})
        if at >= clock_on(s, POLICY['flat_deadline']):
            emit(s, 'ALERT_SIMULATION', 'deadline-breach', {'reason': 'Unresolved orders/exposure at 15:00'})
        return s
    if s['phase'] in {'DONE', 'NO_TRADE', 'EXPIRED'}:
        need(not exposure, 'Exposure after terminal state requires operator recovery')
        return s
    if exposure:
        q = a['quantities']
        lot = s['selected']['lot_size']
        need(all(0 <= SIGNS[r]*q[r] <= lot for r in ROLES), 'Quantity exceeds one lot or reverses ownership')
        need(q['putWing'] >= -q['putBody'] and q['callWing'] >= -q['callBody'], 'Uncovered short body')
        if p.get('session', {}).get('market_open') is not True:
            s['phase'] = 'LOCKED_OVERNIGHT'
            emit(s, 'ALERT_SIMULATION', 'market-closed', {'reason': 'Residual exposure; no pretend executable exit'})
            return s
        if at >= clock_on(s, POLICY['exit_start']) or p.get('command') == 'CLOSE_AND_STOP':
            exit_intent(s, 'Deadline' if at >= clock_on(s, POLICY['exit_start']) else 'Owner close')
        elif any(q[r] != SIGNS[r]*lot for r in ROLES):
            s['phase'] = 'RECOVERY_REQUIRED'
            emit(s, 'ALERT_SIMULATION', 'partial:'+eid, {'reason': 'Residual partial structure; explicit recovery required'})
        elif s['exit_requested']:
            s['phase'] = 'EXIT_PENDING'
        else:
            pnl = liquidation_pnl(s, p, at)
            s['net_liquidation_pnl_rupees'] = pnl
            if pnl <= -POLICY['daily_loss_rupees']:
                exit_intent(s, 'Daily loss threshold including costs')
            else:
                gates = gate_packet(p['gates'], False)
                decision = controller(gates, at)
                s['reviews'].append({'at': at.isoformat(), 'decision': decision, 'pnl': pnl, 'synthetic': True})
                if decision['action'] == 'SQUARE_OFF':
                    exit_intent(s, decision['terminal_gate'])
                else:
                    need(decision['action'] == 'HOLD', 'Unsupported controller action')
                    mins = POLICY['marginal_review_minutes'] if gates['intraday_rv_state'] == 'MARGINAL' else POLICY['review_minutes']
                    nxt = min(at+dt.timedelta(minutes=mins), clock_on(s, POLICY['exit_start']))
                    s['phase'] = 'OPEN'
                    schedule(s, 'review', nxt)
        if at >= clock_on(s, POLICY['flat_deadline']):
            emit(s, 'ALERT_SIMULATION', 'deadline-breach', {'reason': 'Not flat by 15:00; retain exit/recovery state'})
        return s
    if s['entry_requested']:
        need(s['fills'], 'Entry unresolved; no fills is not confirmed closure')
        s['net_liquidation_pnl_rupees'] = liquidation_pnl(s, p, at)
        s['phase'] = 'DONE'
        stop_jobs(s)
        emit(s, 'ACCOUNTING_SIMULATION', 'closure', {'candidate_id': s['selected']['id'],
             'fill_ids': list(s['fills']), 'net_pnl_rupees': s['net_liquidation_pnl_rupees'],
             'production_ledger_written': False})
        return s
    session = p.get('session', {})
    need(session.get('trading_day_verified') is True and session.get('market_open') is True,
         'Verified trading calendar/session required')
    if at < clock_on(s, '09:20') or at >= clock_on(s, POLICY['entry_cutoff']) or p.get('command') == 'STOP_NEW_TRADING':
        s['phase'] = 'NO_TRADE'
        return s
    need(set(p['index_reviews']) == INDICES, 'All three indices require a result or explicit rejection')
    for item in p['index_reviews'].values():
        need(item.get('status') in {'CANDIDATES', 'NO_TRADE'} and bool(item.get('evidence_ref')),
             'Each index needs an explicit evidenced result')
    need(bool(p.get('ranking_evidence_ref')), 'Current cross-index ranking evidence required')
    candidates = p['ranked_candidates']
    need(len({c['id'] for c in candidates}) == len(candidates), 'Duplicate candidate IDs')
    rejected = []
    for c in candidates:
        try:
            need(p['index_reviews'][c['spec']['symbol']]['status'] == 'CANDIDATES', 'Index not eligible')
            bound = candidate_check(c, at)
        except (ValueError, KeyError, TypeError) as e:
            rejected.append({'id': c.get('id'), 'reason': str(e)})
            continue
        s['selected'] = copy.deepcopy(c)
        s['selected']['checked_max_loss_rupees'] = bound
        s['entry_requested'] = True
        s['phase'] = 'ENTRY_PENDING'
        schedule(s, 'deadline', clock_on(s, POLICY['exit_start']))
        schedule(s, 'flat_check', clock_on(s, POLICY['flat_deadline']))
        schedule(s, 'review', min(at+dt.timedelta(minutes=15), clock_on(s, POLICY['exit_start'])))
        emit(s, 'SIMULATE_ENTRY', 'entry', {'spec': c['spec'], 'limits': c['limits'], 'sequence': list(ROLES)})
        break
    else:
        s['phase'] = 'NO_TRADE'
    s['rejections'] = rejected
    return s


def atomic(path, value):
    tmp = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as f:
            tmp = f.name
            os.chmod(tmp, 0o600)
            json.dump(value, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if tmp:
            os.unlink(tmp)


def run(directory, packet):
    directory = Path(directory).resolve()
    # Synthetic operational artifacts never become an alternate live ledger.
    need('ledger' not in directory.parts, 'Cannot store simulation in a ledger directory')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    need(packet.get('mode') == 'SHADOW', 'LIVE EXECUTION IS NOT IMPLEMENTED OR AUTHORIZED')
    day = dt.date.fromisoformat(packet['day']).isoformat()
    target = directory/(day+'.json')
    with (directory/'workflow.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(target.read_text()) if target.exists() else initial(day)
        try:
            for other in directory.glob('????-??-??.json'):
                if other == target:
                    continue
                previous = json.loads(other.read_text())
                need(previous.get('mode') == 'SHADOW', 'Mixed-mode state directory')
                need(not previous.get('entry_requested') or previous.get('phase') == 'DONE',
                     'Another day has unresolved execution/exposure; reconcile before starting')
            result = transition(state, packet)
            emit(result, 'JOURNAL_SIMULATION', 'journal:'+packet['event_id'],
                 {'at': packet['asof'], 'phase': result['phase'], 'published': False})
        except (KeyError, TypeError, ValueError) as e:
            # Preserve exposure/intent state; validation failure never implies flat.
            result = copy.deepcopy(state)
            result['last_blocker'] = {'event_id': packet.get('event_id'), 'reason': str(e), 'at': packet.get('asof')}
            emit(result, 'ALERT_SIMULATION', 'blocked:'+str(packet.get('event_id')), result['last_blocker'])
        atomic(target, result)
        return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--state-dir', required=True)
    ap.add_argument('--input', required=True)
    args = ap.parse_args()
    result = run(args.state_dir, json.loads(Path(args.input).read_text()))
    print(json.dumps({'mode': 'SHADOW', 'phase': result['phase'], 'blocker': result.get('last_blocker'),
                      'state_dir': str(Path(args.state_dir).resolve()), 'orders_sent': False,
                      'real_jobs_scheduled': False, 'production_ledger_written': False}, indent=2))
    return 2 if result.get('last_blocker') else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error), 'orders_sent': False,
                          'real_jobs_scheduled': False, 'production_ledger_written': False}))
        raise SystemExit(2)
