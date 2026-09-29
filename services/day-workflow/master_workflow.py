#!/usr/bin/env python3
"""Machine-readable lifecycle router; emits next steps, never dispatches effects."""
import argparse
import datetime as dt
import json
from pathlib import Path

import day_workflow as w
from workflow_decision import compose
from workflow_observation import assess_manifest, decode, verified_account_evidence

POLICY_PATH = Path(__file__).resolve().parent / 'policy/master_algorithm.json'
ORDER = ['auth', 'account', 'session', 'deadline', 'ownership', 'loss', 'mandate', 'research']


def outcome(action, reason):
    return {'action': action, 'reason': reason}


def auth(p, at):
    a = p.get('auth', {})
    status = a.get('status')
    if status in {'ACCOUNT_MISMATCH', 'NETWORK_ERROR', 'AMBIGUOUS_RECOVERY', 'HUMAN_LOGIN_REQUIRED'}:
        return outcome('AUTH_HANDOFF', status + '; exposure is unverified, never presumed flat')
    if status in {'MISSING', 'EXPIRED', 'REJECTED', 'SHORT_LIVED', 'WEB_TOKEN_REQUIRED'}:
        if a.get('attempts_this_pass', 0) >= 1:
            return outcome('AUTH_HANDOFF', 'Recovery already attempted; reconcile before retry')
        if a.get('last_attempt_at') and (at-w.stamp(a['last_attempt_at'])).total_seconds() < 300:
            return outcome('AUTH_HANDOFF', 'Recovery cooldown')
        return outcome('RECOVER_WEB_TOKEN', 'Use existing Dhan Web recovery; verify identity then refresh account; no API/TOTP generation')
    if status != 'VALID':
        return outcome('VERIFY_TOKEN', 'Run existing on-demand token preflight')
    w.fresh(a['asof'], at)
    w.need(a.get('profile_verified') is True, 'TOKEN_PROFILE_UNVERIFIED')
    if (w.stamp(a['expires_at'])-at).total_seconds() < 7200:
        if a.get('attempts_this_pass', 0) >= 1 or (a.get('last_attempt_at') and (at-w.stamp(a['last_attempt_at'])).total_seconds() < 300):
            return outcome('AUTH_HANDOFF', 'Short-lived token recovery already attempted / cooling down')
        return outcome('RECOVER_WEB_TOKEN', 'Valid but short-lived; existing renewal/recovery helper, not repeated generation')


def account(p, at):
    a = p.get('_account', {})
    if a.get('account_verified') is not True:
        return outcome('ACQUIRE_ACCOUNT', 'Fresh verified positions AND orders required; access failure is not flatness')
    if a['account_state'] == 'OUTSTANDING_ORDERS':
        return outcome('RECONCILE_ORDERS', 'Do not resubmit, modify or cancel automatically; reconcile pending/partial fills')


def exposed(p):
    return p['_account']['account_state'] == 'EXPOSURE_PRESENT'


def session(p, at):
    s = p.get('session', {})
    if s.get('trading_day_verified') is not True or type(s.get('market_open')) is not bool:
        return outcome('VERIFY_SESSION', 'Dated exchange calendar and actionable session evidence required')
    w.fresh(s['asof'], at)
    w.need(bool(s['evidence_ref']), 'SESSION_SOURCE_REQUIRED')
    if not s['market_open']:
        return outcome('LOCKED_OVERNIGHT' if exposed(p) else 'NO_TRADE', 'Market not actionable; no pretend exit')


def deadline(p, at):
    if exposed(p) and (at.strftime('%H:%M') >= '14:45' or p.get('command') == 'CLOSE_AND_STOP'):
        return outcome('SQUARE_OFF', 'Intraday deadline / owner close; Aryan must execute; closure unverified')


def ownership(p, at):
    if p['mode'] == 'OBSERVE' and not exposed(p) and not p.get('cycle_id'):
        import trade_ledger
        rows = trade_ledger.read_ledger(trade_ledger.DEFAULT_LEDGER)
        if any(r['event_type']=='FILL' and r['broker']=='DHAN' and r['account_alias']=='DHAN_PRIMARY' and r['trading_date']==at.date().isoformat() for r in trade_ledger.validate_rows(rows)):
            return outcome('RECONCILE_POSITION', 'Recorded day fills require explicit cycle reconciliation before any new entry')
    if p['mode'] == 'OBSERVE' and (exposed(p) or p.get('cycle_id')):
        try:
            import trade_ledger
            from workflow_accounting import reconcile
            kwargs = {'now': at}
            if p.get('_evidence_root') is not None:
                kwargs['root'] = p['_evidence_root']
            receipt, evidence = verified_account_evidence(p['account_manifest'], **kwargs)
            rows = trade_ledger.read_ledger(trade_ledger.DEFAULT_LEDGER)
            state = reconcile(evidence, receipt, rows, p.get('cycle_id'), at)
            p['_reconciliation'] = state
            if state['status'] != 'RECONCILED':
                return outcome('RECONCILE_POSITION', state['status'])
            if state['closed']:
                return outcome('STOP', 'Broker-verified cycle closure; record canonical closure and publish; no automatic re-entry')
            p['ownership_verified'] = True
        except (ValueError, KeyError, TypeError, OSError) as error:
            return outcome('RECONCILE_POSITION', str(error))
    if exposed(p) and p.get('ownership_verified') is not True:
        return outcome('RECONCILE_POSITION', 'Exact strategy ownership required')


def loss(p, at):
    if not exposed(p):
        return
    if p['mode'] == 'OBSERVE':
        value = p.get('_reconciliation', {})
        if value.get('valuation_status') != 'RECONCILED':
            p['_valuation_blocker'] = value.get('valuation_blocker', 'FILL_BASED_VALUATION_UNAVAILABLE')
            return
        # Only the independently derived fill/quote P&L is accepted, never inline P&L.
        net = w.number(value['net_liquidation_pnl_rupees'])
        if net <= -1000:
            return outcome('SQUARE_OFF', 'Recorded fills, executable liquidation and incurred costs breach daily budget')
        bound = p.get('exit_cost_bound', {})
        try:
            w.fresh(bound['asof'], at)
            w.need(bound['cycle_id'] == value['cycle_id'] and bound['evidence_ref'], 'EXIT_COST_BOUND_UNBOUND')
            cost = w.number(bound['rupees'])
            w.need(cost >= 0, 'NEGATIVE_EXIT_COST_BOUND')
        except (ValueError, KeyError, TypeError) as error:
            p['_valuation_blocker'] = str(error)
            return
        if net-cost <= -1000:
            return outcome('SQUARE_OFF', 'Liquidation P&L including remaining exit-cost bound breaches daily budget')
    elif p.get('valuation'):
        value = p['valuation']
        w.fresh(value['asof'], at)
        w.need(value.get('basis') == 'ALL_CYCLE_FILLS' and value.get('costs_included') is True, 'PNL_BASIS_UNVERIFIED')
        if w.number(value['net_liquidation_pnl_rupees']) <= -1000:
            return outcome('SQUARE_OFF', 'Daily risk-budget threshold; not a guaranteed realized-loss cap')


def mandate(p, at):
    m = p.get('mandate', {})
    if m.get('day') != at.date().isoformat() or m.get('activated') is not True:
        return outcome('ACTIVATE_DAY', 'Day-scoped activation required; existing exposure needs operator handoff')
    if not exposed(p) and m.get('cycle_closed') is True:
        return outcome('STOP', 'No automatic re-entry; reconcile ledger/publication and day-owned jobs')
    if not exposed(p) and (at.strftime('%H:%M') < '09:20' or at.strftime('%H:%M') >= '14:30'):
        return outcome('NO_TRADE', 'Outside conservative entry window')
    if p.get('review_due') is not True and p.get('material_trigger') not in {'BROKER_WARNING', 'EXECUTION_ANOMALY', 'BREAK_EVEN_THREAT', 'SURFACE_DISLOCATION', 'MATERIAL_EVENT'}:
        return outcome('WAIT_REVIEW', 'No scheduled window or objective risk trigger; no monitoring installed')


def research(p, at):
    if p.get('_reconciliation'):
        state = p['_reconciliation']
        w.need(p['research']['position_symbol'] == state['symbol'], 'RESEARCH_POSITION_SYMBOL_MISMATCH')
        w.need(p['research']['indices'][state['symbol']]['expiry'] == state['expiry'], 'RESEARCH_POSITION_EXPIRY_MISMATCH')
    result = compose(p['research'], at, exposed(p), observed=p['mode'] == 'OBSERVE')
    if result['action'] == 'HOLD' and p.get('_valuation_blocker'):
        return outcome('NEED_EVIDENCE', p['_valuation_blocker'])
    return result


HANDLERS = {fn.__name__: fn for fn in (auth, account, session, deadline, ownership, loss, mandate, research)}


def evaluate(packet, *, now=None, evidence_root=None):
    at = (now or dt.datetime.now(dt.timezone.utc)).astimezone(w.IST)
    result = {'format': 'volarb.master-result.v1', 'mode': packet.get('mode'), 'asof': at.isoformat(),
              'orders_sent': False, 'jobs_scheduled': False, 'production_ledger_written': False,
              'execution_authorized': False, 'journal_published': False, 'trace': []}
    try:
        policy = decode(POLICY_PATH.read_text())
        w.need(policy['format'] == 'volarb.master-policy.v1' and policy['first_terminal_rule_wins'] is True, 'INVALID_MASTER_POLICY')
        w.need([r['handler'] for r in policy['rules']] == ORDER, 'MASTER_PRECEDENCE_CHANGED')
        w.need(not any(policy['capabilities'].values()), 'LIVE_CAPABILITY_NOT_IMPLEMENTED')
        w.need(policy['limits'] == {k: w.POLICY[k] for k in policy['limits']}, 'MASTER_LIMITS_DRIFT')
        w.need(packet.get('mode') in {'SHADOW', 'OBSERVE'}, 'LIVE_MODE_NOT_IMPLEMENTED')
        w.fresh(packet['asof'], at)
        p = {k: v for k, v in packet.items() if not k.startswith('_')}
        p['_evidence_root'] = evidence_root
        # Ignore caller-provided account receipt in OBSERVE mode.
        if p['mode'] == 'OBSERVE':
            kwargs = {'now': at}
            if evidence_root is not None:
                kwargs['root'] = evidence_root
            p['_account'] = assess_manifest(p['account_manifest'], **kwargs) if p.get('account_manifest') else {}
        else:
            w.need(p.get('synthetic') is True, 'SHADOW_REQUIRES_SYNTHETIC_FIXTURE')
            p['_account'] = p.get('account', {})
            if p['_account'].get('account_verified') is True:
                w.fresh(p['_account']['asof'], at)
                w.need(p['_account']['account_state'] in {'VERIFIED_FLAT', 'EXPOSURE_PRESENT', 'OUTSTANDING_ORDERS'}, 'INVALID_ACCOUNT_STATE')
        for rule in policy['rules']:
            result['trace'].append(rule['id'])
            answer = HANDLERS[rule['handler']](p, at)
            if answer:
                result.update(answer, terminal_rule=rule['id'])
                result['effect'] = policy['effects'].get(answer['action'], {'dispatch': 'none'})
                if p.get('_reconciliation'):
                    result['reconciliation'] = p['_reconciliation']
                break
        return result
    except (KeyError, ValueError, TypeError, OSError) as error:
        result.update(action='NEED_EVIDENCE', reason=str(error), terminal_rule=result['trace'][-1] if result['trace'] else 'INPUT')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    args_group = parser.add_mutually_exclusive_group(required=True)
    args_group.add_argument('--input')
    args_group.add_argument('--describe', action='store_true', help='Print the complete machine-readable policy and adapter contracts')
    args = parser.parse_args()
    if args.describe:
        print(POLICY_PATH.read_text(), end='')
        return 0
    result = evaluate(decode(Path(args.input).read_text()))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 2 if result['action'] in {'NEED_EVIDENCE', 'AUTH_HANDOFF'} else 0


if __name__ == '__main__':
    raise SystemExit(main())
