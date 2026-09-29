"""Read-only research composition. No network, orders, schedules or ledger writes.

Consumes analyst-produced news/risk/selection packets and raw HF observations.
Recomputes RV and exact-candidate checks; never accepts supplied RV PASS flags.
These are decision-support outputs, never executor authorization.
"""
import copy
import datetime as dt
import importlib.util
import hashlib
import hmac
from pathlib import Path
import sys

import day_workflow as w
from workflow_observation import ROOT, FORMAT, decode, private_bytes

SKILLS = w.SOURCE.parents[2]


def load_script(skill, name):
    path = SKILLS / skill / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location('_volarb_' + name, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def news_packet(packet, at, horizon):
    w.need(packet['producer'] == 'market-news-signal-filter', 'NEWS_CHILD_REQUIRED')
    w.fresh(packet['asof'], at, 300)
    w.need(packet['horizon_minutes'] == horizon, 'NEWS_HORIZON_MISMATCH')
    w.need(w.stamp(packet['valid_until']) >= at + dt.timedelta(minutes=horizon), 'NEWS_HORIZON_EXPIRED')
    w.need(bool(packet['source_refs']), 'NEWS_SOURCES_REQUIRED')
    out = copy.deepcopy(packet['normalized'])
    w.need(out['status'] in {'CURRENT', 'STALE_CALIBRATION'}, 'NEWS_UNAVAILABLE')
    w.need(out['aggregate_state'] in {'CALM', 'NOISY_BUT_BENIGN', 'EVENTFUL', 'HIGH_UNCERTAINTY', 'TAIL_RISK_ACTIVE'}, 'NEWS_STATE_INVALID')
    w.need(out['max_butterfly_relevance'] in {'ignore', 'watch', 'material', 'critical'}, 'NEWS_RELEVANCE_INVALID')
    w.need(out['max_latency_severity'] in {'low', 'medium', 'high', 'critical'}, 'NEWS_LATENCY_INVALID')
    age = (at.date() - dt.date.fromisoformat(out['calibration_asof'])).days
    w.need(age >= 0, 'FUTURE_NEWS_CALIBRATION')
    if age > 45:
        out['status'] = 'STALE_CALIBRATION'
    w.need(isinstance(out['events'], list), 'NEWS_EVENTS_REQUIRED')
    latency = ['low', 'medium', 'high', 'critical']
    relevance = ['ignore', 'watch', 'material', 'critical']
    for event in out['events']:
        w.need(event['latency_severity'] in latency and event['butterfly_relevance'] in relevance,
               'NEWS_EVENT_FIELDS_INVALID')
        w.need(latency.index(event['latency_severity']) <= latency.index(out['max_latency_severity'])
               and relevance.index(event['butterfly_relevance']) <= relevance.index(out['max_butterfly_relevance']),
               'NEWS_AGGREGATE_CONTRADICTION')
    if out['status'] == 'STALE_CALIBRATION':
        w.need(packet.get('live_crossasset_confirmation_ref'), 'STALE_NEWS_PRIOR_NEEDS_LIVE_CONFIRMATION')
    return out


def load_hf_manifest(manifest_file, symbol, at, root=ROOT):
    """Read only immutable, hash-bound observations from the dedicated HF sampler."""
    manifest = decode(private_bytes(manifest_file, root))
    w.need(manifest['format'] == FORMAT+'.manifest' and manifest['provenance'] == 'OBSERVED', 'HF_MANIFEST_REQUIRED')
    source = Path(root)/(manifest['collection_id']+'.json')
    w.need(manifest['evidence_file'] == str(source), 'HF_PATH_MISMATCH')
    content = private_bytes(source, root)
    w.need(hmac.compare_digest(hashlib.sha256(content).hexdigest(), manifest['sha256']), 'HF_HASH_MISMATCH')
    evidence = decode(content)
    w.need(evidence['format'] == FORMAT and evidence['scope'] == 'HF' and evidence['mode'] == 'READ_ONLY'
           and evidence['provenance'] == 'OBSERVED' and evidence['collection_id'] == manifest['collection_id']
           and evidence['completed_at'] == manifest['completed_at'], 'HF_IDENTITY_MISMATCH')
    w.fresh(evidence['completed_at'], at, 10)
    instruments = [i for i in evidence['instruments'] if i['symbol'] == symbol]
    w.need(len(instruments) == 1, 'HF_INSTRUMENT_BINDING_REQUIRED')
    return {'hf_quotes': evidence['hf_quotes'][symbol], 'evidence_ref': manifest['sha256'],
            'instrument_ref': instruments[0]}


def forecast(raw, news, symbol, at, horizon):
    w.need(raw['symbol'] == symbol and raw['horizon_minutes'] == horizon, 'HF_IDENTITY_HORIZON_MISMATCH')
    w.need(not raw.get('config'), 'HF_CONFIG_OVERRIDE_DISABLED')
    w.fresh(raw['current_asof'], at)
    quotes = raw['hf_quotes']
    w.need(isinstance(quotes, list) and bool(quotes), 'HF_BLOCK_REQUIRED')
    times = [w.stamp(q['timestamp']) for q in quotes]
    w.need(times == sorted(set(times)), 'HF_CLOCK_ORDER_OR_DUPLICATE')
    w.fresh(times[-1].isoformat(), at, 10)
    w.need(times[0].date() == at.date() and 270 <= (times[-1]-times[0]).total_seconds() <= 330, 'HF_FIVE_MINUTE_BLOCK_REQUIRED')
    w.need(raw.get('evidence_ref') and raw.get('instrument_ref'), 'HF_SOURCE_REQUIRED')
    data = copy.deepcopy(raw)
    data['news_filter'] = news  # one normalized packet shared across every index/gate
    return load_script('intraday-realized-volatility-forecast', 'forecast_intraday_rv').evaluate(data)


def exact_quotes(candidate, at):
    """Bind executable side/depth to four explicitly resolved option contracts."""
    spec, lot = candidate['spec'], candidate['lot_size']
    w.need(spec['center']-spec['lower'] == spec['upper']-spec['center'], 'SYMMETRIC_WIDE_FLY_REQUIRED')
    legs = candidate['legs']
    w.need(set(legs) == set(w.ROLES), 'FOUR_CONTRACTS_REQUIRED')
    seen = set()
    for role, strike, option in [('putWing', spec['lower'], 'PE'), ('putBody', spec['center'], 'PE'),
                                  ('callWing', spec['upper'], 'CE'), ('callBody', spec['center'], 'CE')]:
        leg = legs[role]
        identity = (leg['exchange_segment'], str(leg['security_id']))
        w.need(identity not in seen and identity[1].isdigit(), 'DUPLICATE_OR_INVALID_CONTRACT')
        seen.add(identity)
        w.need(leg['symbol'] == spec['symbol'] and leg['expiry'] == spec['expiry'] and
               leg['strike'] == strike and leg['option_type'] == option and leg['lot_size'] == lot,
               'CONTRACT_GEOMETRY_MISMATCH')
        w.need(identity[0] == ('BSE_FNO' if spec['symbol'] == 'SENSEX' else 'NSE_FNO'), 'CONTRACT_SEGMENT_MISMATCH')
        w.need(bool(leg['resolver_ref']), 'CONTRACT_RESOLVER_REQUIRED')
        q = leg['quote']
        w.fresh(q['asof'], at)
        w.fresh(q['exchange_time'], at)
        bid, ask = w.number(q['bid']), w.number(q['ask'])
        w.need(0 < bid <= ask, 'INVALID_BOOK')
        buy = w.SIGNS[role] > 0
        w.need(w.number(q['ask_size' if buy else 'bid_size']) >= lot, 'INSUFFICIENT_ENTRY_DEPTH')
        limit = candidate['limits'][role]
        w.need(limit >= ask if buy else limit <= bid, 'LIMIT_NOT_EXECUTABLE')


def compose(packet, at, open_position=False, observed=False):
    """Progressively evaluate research. Absent later evidence never masks an exit."""
    horizon = packet['horizon_minutes']
    w.need(type(horizon) is int and 15 <= horizon <= 30, 'REVIEW_HORIZON_REQUIRED')
    indices = packet['indices']
    w.need(set(indices) == (set([packet['position_symbol']]) if open_position else w.INDICES), 'INDEX_COVERAGE_REQUIRED')
    results, accepted, rejections = {}, {}, []
    normalized_news = None
    for symbol, item in indices.items():
        try:
            w.fresh(item['asof'], at)
            w.need(item['data_health'] in {'HEALTHY', 'DEGRADED', 'STALE', 'INVALID'}, 'DATA_HEALTH_UNVERIFIED')
            if not open_position and item['data_health'] in {'STALE', 'INVALID'}:
                results[symbol] = {'action': 'NO_TRADE', 'terminal_gate': 'DATA_HEALTH'}
                continue
            if normalized_news is None:
                normalized_news = news_packet(packet['news'], at, horizon)
            try:
                hf = copy.deepcopy(item['hf'])
                if observed:
                    hf.update(load_hf_manifest(item['hf_manifest'], symbol, at))
                rv = forecast(hf, normalized_news, symbol, at, horizon)
            except (KeyError, ValueError, TypeError):
                rv = {'short_gamma_state': 'INSUFFICIENT_DATA', 'confidence': 'low'}
            gates = {'mode': 'OPEN_POSITION' if open_position else 'CANDIDATE',
                     'branch': 'OPEN_INTRADAY' if open_position else 'CANDIDATE_INTRADAY',
                     'data_health': item['data_health'], 'intraday_rv_state': rv['short_gamma_state'],
                     'intraday_rv_confidence': rv['confidence'], 'news_filter_status': normalized_news['status']}
            early = w.controller(gates, at)
            if early['terminal_gate'] == 'INTRADAY_RV_DRIFT':
                results[symbol] = {**early, 'rv': rv}
                continue
            w.need(item['hard_risk_gate'] in {'PASS', 'BLOCK', 'FAIL'} and item['risk_evidence_ref'], 'HARD_RISK_UNVERIFIED')
            gates['hard_risk_gate'] = item['hard_risk_gate']
            if gates['hard_risk_gate'] != 'PASS':
                results[symbol] = {**w.controller(gates, at), 'rv': rv}
                continue
            if open_position:
                w.need(item['expiry_exit_gate'] in {'PASS', 'FAIL', 'BLOCK', 'EXIT', 'NOT_APPLICABLE'} and item['expiry_evidence_ref'], 'EXPIRY_GATE_UNVERIFIED')
                gates.update(expiry_exit_gate=item['expiry_exit_gate'], recenter_gate='NOT_APPLICABLE')
                decision = w.controller(gates, at)
                minutes = 10 if rv['short_gamma_state'] == 'MARGINAL' else horizon
                decision['next_review'] = min(at+dt.timedelta(minutes=minutes), at.replace(hour=14, minute=45, second=0, microsecond=0)).isoformat() if decision['action'] == 'HOLD' else None
                results[symbol] = {**decision, 'rv': rv}
                continue
            for raw_candidate in item.get('candidates', []):
                c = copy.deepcopy(raw_candidate)
                try:
                    w.need(c['spec']['symbol'] == symbol and c['id'] not in accepted, 'CANDIDATE_IDENTITY_MISMATCH')
                    c['gates'] = gates
                    exact_quotes(c, at)
                    bound = w.candidate_check(c, at)
                    accepted[c['id']] = {'id': c['id'], 'spec': c['spec'], 'checked_max_loss_rupees': bound,
                                          'upper_forecast_sigma_move_points': rv.get('upper_forecast_sigma_move_points')}
                except (KeyError, ValueError, TypeError) as error:
                    rejections.append({'id': c.get('id'), 'reason': str(error)})
            results[symbol] = {'action': 'CANDIDATES' if any(c['spec']['symbol'] == symbol for c in accepted.values()) else 'NO_TRADE', 'rv': rv}
        except (KeyError, ValueError, TypeError) as error:
            results[symbol] = {'action': 'NEED_EVIDENCE', 'reason': str(error)}
    if open_position:
        return {**next(iter(results.values())), 'indices': results}
    if any(r['action'] == 'NEED_EVIDENCE' for r in results.values()):
        return {'action': 'NEED_EVIDENCE', 'indices': results, 'rejections': rejections}
    if not accepted:
        return {'action': 'NO_TRADE', 'indices': results, 'rejections': rejections}
    ranking = packet['ranking']
    w.fresh(ranking['asof'], at)
    w.need(ranking['evidence_ref'] and set(accepted) <= set(ranking['candidate_ids']), 'CROSS_INDEX_RANKING_REQUIRED')
    chosen = next(cid for cid in ranking['candidate_ids'] if cid in accepted)
    return {'action': 'CANDIDATE_VALIDATED', 'selected': accepted[chosen], 'indices': results, 'rejections': rejections}
