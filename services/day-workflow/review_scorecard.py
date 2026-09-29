#!/usr/bin/env python3
"""Local canonical append-only research events. No broker access or trading capabilities."""
import argparse
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
from zoneinfo import ZoneInfo

from volarb_paths import TRADING_ROOT
ROOT = TRADING_ROOT
LEDGER = ROOT / 'ledger/butterfly_reviews.json'
STORE_FORMAT = 'volarb.butterfly_reviews'
STORE_VERSION = 1
KINDS = {'REVIEW', 'FORECAST', 'OUTCOME', 'DECISION', 'EXECUTION'}

def timestamp(x):
    v = dt.datetime.fromisoformat(x)
    if v.tzinfo is None:
        raise ValueError('Timezone offset required')
    return v

def number(x):
    if isinstance(x, bool):
        raise ValueError('Boolean is not a numeric observation')
    v = float(x)
    if not math.isfinite(v):
        raise ValueError('Nonfinite number')
    return v

def reject_constant(value):
    raise ValueError('Nonfinite JSON value: ' + value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode_json(text):
    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)


def data(row):
    value = row.get('analytics_json') or {}
    if isinstance(value, str):
        value = decode_json(value)  # Accept existing callers; storage is a native object.
    if not isinstance(value, dict):
        raise ValueError('analytics_json must be an object')
    return value


def validate_document(document):
    if (not isinstance(document, dict) or document.get('format') != STORE_FORMAT or
            type(document.get('format_version')) is not int or document['format_version'] != STORE_VERSION):
        raise ValueError('Unsupported review JSON format/version')
    fields, events = document.get('event_fields'), document.get('events')
    if (not isinstance(fields, list) or not fields or not all(isinstance(f, str) and f for f in fields)
            or len(fields) != len(set(fields)) or not isinstance(events, list)):
        raise ValueError('Malformed review field schema/events')
    required = {'review_id', 'record_type', 'recorded_at_ist', 'strategy_id', 'analytics_json'}
    if not required.issubset(fields):
        raise ValueError('Required review fields absent')
    ids = set()
    for event in events:
        if not isinstance(event, dict) or set(event) != set(fields):
            raise ValueError('Stored review fields do not match schema')
        rid = event['review_id']
        if not isinstance(rid, str) or not rid or rid in ids:
            raise ValueError('Missing/duplicate stored event ID')
        if event['record_type'] not in KINDS or not isinstance(event['analytics_json'], dict):
            raise ValueError('Invalid stored event type/analytics')
        timestamp(event['recorded_at_ist'])
        ids.add(rid)
    # Validate storage, not modern business rules against immutable legacy events.
    json.dumps(document, allow_nan=False)
    return document


def read_document():
    return validate_document(decode_json(LEDGER.read_text(encoding='utf-8')))


def write_document(document):
    """Caller holds the shared lock. Atomic local replacement and exact readback."""
    validate_document(document)
    contents = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=LEDGER.parent, prefix='.review-write-',
                                         delete=False, encoding='utf-8', newline='') as f:
            name = f.name
            f.write(contents)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, LEDGER)
        name = None
    finally:
        if name:
            os.unlink(name)
    if LEDGER.read_text(encoding='utf-8') != contents or read_document() != document:
        raise OSError('STORAGE_READBACK_FAILED: review JSON')


def active(rows):
    superseded = {r.get('supersedes_review_id') for r in rows if r.get('supersedes_review_id')}
    return [r for r in rows if r['review_id'] not in superseded]

def validate_event(event, rows):
    ids = {r['review_id']: r for r in rows}
    rid = event['review_id']
    if not rid or rid in ids:
        raise ValueError('Missing/duplicate event ID')
    kind = event['record_type']
    if kind not in KINDS:
        raise ValueError('Unknown record type')
    timestamp(event['recorded_at_ist'])
    a = data(event)
    parent = event.get('parent_review_id')
    if kind != 'REVIEW':
        if parent not in ids or ids[parent]['record_type'] != 'REVIEW':
            raise ValueError('Non-review event requires an existing REVIEW parent')
        if event.get('strategy_id') != ids[parent]['strategy_id']:
            raise ValueError('Strategy must match parent review')
    sup = event.get('supersedes_review_id')
    if sup:
        if sup not in {r['review_id'] for r in active(rows)}:
            raise ValueError('Correction must supersede a current event')
        old = ids[sup]
        if (old['record_type'],old.get('parent_review_id'),old['strategy_id']) != (kind,parent,event['strategy_id']):
            raise ValueError('Correction cannot change event identity/type/parent')
    if kind == 'FORECAST':
        if a.get('forecast_role') not in {'ACTUAL','BENCHMARK'}:
            raise ValueError('Explicit ACTUAL forecast or BENCHMARK classification required')
        if a['forecast_role']=='ACTUAL':
            for field in ['central_thesis','confidence','rationale','evidence','disconfirming_evidence','invalidation']:
                if not a.get(field): raise ValueError('Actual forecast requires '+field)
            if not a.get('predictions') and not a.get('event_prediction'):
                raise ValueError('Actual forecast requires a predeclared testable outcome')
        if a.get('event_prediction'):
            rule=a['event_prediction']
            if rule.get('operator') not in {'LT','GT'} or not rule.get('metric') or not isinstance(rule.get('predicted'),bool):
                raise ValueError('Invalid event prediction')
            number(rule['threshold'])
        if any(r['record_type']=='FORECAST' and r.get('parent_review_id')==parent and data(r).get('model_version')==a.get('model_version') and data(r).get('cluster_id')==a.get('cluster_id') and r['review_id']!=sup for r in active(rows)):
            raise ValueError('One active forecast per review/model/trade-cycle; append correction explicitly')
        start, end = timestamp(a['issued_at']), timestamp(a['target_at'])
        if end <= start or timestamp(event['recorded_at_ist']) >= end or start > timestamp(event['recorded_at_ist']):
            raise ValueError('Forecast must be recorded before target; cannot backdate issue time into future')
        if a['horizon'] not in {'INTRADAY','OVERNIGHT','EXPIRY'}:
            raise ValueError('Invalid horizon')
        if not a.get('model_version') or not a.get('cluster_id'):
            raise ValueError('Model version and trade-cycle cluster required')
        for name, pred in a['predictions'].items():
            number(pred['point'])
            if 'low' in pred or 'high' in pred:
                if not number(pred['low']) <= number(pred['high']):
                    raise ValueError('Invalid forecast interval')
                if not 0 < number(pred['coverage']) < 1:
                    raise ValueError('Interval nominal coverage required')
        if 'p_hold_beats_close' in a and not 0 <= number(a['p_hold_beats_close']) <= 1:
            raise ValueError('Probability outside [0,1]')
        if a.get('training_latest_outcome_at') and timestamp(a['training_latest_outcome_at']) >= start:
            raise ValueError('Training lookahead')
        if a.get('training_latest_recorded_at') and timestamp(a['training_latest_recorded_at']) >= start:
            raise ValueError('Training availability lookahead')
    if kind == 'OUTCOME':
        fid = a['forecast_id']
        if fid not in ids or ids[fid]['record_type']!='FORECAST' or ids[fid]['parent_review_id']!=parent:
            raise ValueError('Outcome must link to a forecast of this review')
        if any(r['record_type']=='OUTCOME' and data(r).get('forecast_id')==fid and r['review_id']!=sup for r in active(rows)):
            raise ValueError('Duplicate outcome; use correction event')
        target=timestamp(data(ids[fid])['target_at'])
        observed=timestamp(a['observed_at'])
        if observed < target or observed > timestamp(event['recorded_at_ist']):
            raise ValueError('Outcome before target or future observation')
        if not a.get('source_ref') or a.get('quote_status') not in {'EXECUTABLE','SETTLEMENT','INDEX_OBSERVATION','HISTORICAL','UNAVAILABLE'}:
            raise ValueError('Outcome source and quote status required')
        if a.get('quote_status')=='INDEX_OBSERVATION' and set(a.get('observed',{}))!={'spot'}:
            raise ValueError('Index observation must contain spot only')
        for v in a.get('observed',{}).values():
            if v is not None: number(v)
        for k in ['exit_costs_inr','actual_execution_costs_inr']:
            if a.get(k) is not None and number(a[k]) < 0:
                raise ValueError('Costs cannot be negative')
    if kind == 'REVIEW':
        from simple_ledger import validate_accounting
        validate_accounting(event, rows)
    if kind in {'DECISION','EXECUTION'} and not a.get('source_ref'):
        raise ValueError('User/broker evidence required; recommendations are not executions')
    return event

def append_event(event):
    # Canonical ledger must already exist; never create an alternate ledger on failure.
    if not ROOT.is_dir() or not LEDGER.is_file():
        raise OSError('STORAGE_UNAVAILABLE: canonical JSON ledger missing')
    lock = ROOT/'ledger/.butterfly_reviews.lock'
    with lock.open('a') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        document = read_document()
        fields, rows = document['event_fields'], document['events']
        event = dict(event)
        event.setdefault('recorded_at_ist', dt.datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(timespec='seconds'))
        event.setdefault('schema_version', '2')
        if set(event) - set(fields):
            raise ValueError('Unknown fields: ' + str(set(event)-set(fields)))
        event = {key: event.get(key, '') for key in fields}
        event['analytics_json'] = data(event)
        validate_event(event, rows)
        updated = dict(document, events=[*rows, event])
        write_document(updated)
        check = read_rows()
        if check != [*rows, event]:
            raise OSError('STORAGE_READBACK_FAILED: event history changed')
        from simple_ledger import refresh
        try:
            simple = refresh(check, ROOT)
        except Exception as exc:
            raise OSError('REVIEW_COMMITTED_BUT_SIMPLE_LEDGER_FAILED: ' + event['review_id'] +
                          '; repair with code/simple_ledger.py, do not append the event again: ' + str(exc)) from exc
        return {'status':'APPENDED_AND_READBACK_VERIFIED','review_id':event['review_id'],'rows':len(check),'simple_ledger':simple,'storage':'LOCAL_CANONICAL'}


def read_rows():
    return read_document()['events']


def score(rows):
    current=active(rows); ids={r['review_id']:r for r in current}; groups={}; exclusions=[]
    for out in current:
        if out['record_type']!='OUTCOME': continue
        o=data(out); f=ids.get(o['forecast_id'])
        if not f:
            exclusions.append({'id':out['review_id'],'reason':'Forecast superseded/missing'}); continue
        a=data(f)
        tolerance=number(a.get('outcome_tolerance_seconds',60))
        if tolerance<0: raise ValueError('Negative target tolerance')
        if abs((timestamp(o['observed_at'])-timestamp(a['target_at'])).total_seconds()) > tolerance:
            exclusions.append({'id':out['review_id'],'reason':'Outside predeclared target tolerance'}); continue
        if o['quote_status'] not in {'EXECUTABLE','SETTLEMENT','INDEX_OBSERVATION'}:
            exclusions.append({'id':out['review_id'],'reason':'Non-executable/unverified outcome'}); continue
        role=a.get('forecast_role','UNCLASSIFIED')
        key=(role,a['model_version'],a['horizon'])
        g=groups.setdefault(key,{'pairs':[]})
        pair={'cluster':a['cluster_id'],'forecast_id':f['review_id'],'metrics':{}}
        obs=o.get('observed',{})
        for metric,pred in a['predictions'].items():
            if obs.get(metric) is None: continue
            y=number(obs[metric]); point=number(pred['point']); m={'absolute_error':abs(y-point)}
            if 'low' in pred:
                low,high=number(pred['low']),number(pred['high']); alpha=1-number(pred['coverage'])
                m.update(covered=float(low<=y<=high),nominal_coverage=number(pred['coverage']),interval_score=high-low+2/alpha*max(low-y,0)+2/alpha*max(y-high,0))
            base=a.get('baseline',{}).get(metric)
            if base is not None: m['baseline_absolute_error']=abs(y-number(base))
            pair['metrics'][metric]=m
        if a.get('event_prediction'):
            rule=a['event_prediction']; value=obs.get(rule['metric'])
            if value is not None:
                occurred=number(value)<number(rule['threshold']) if rule['operator']=='LT' else number(value)>number(rule['threshold'])
                pair['metrics']['event_prediction']={'correct':float(occurred==rule['predicted'])}
        # Incremental HOLD result relative to contemporaneous CLOSE, not entry P&L.
        if a.get('baseline_quote_status')=='EXECUTABLE' and all(v is not None for v in [a.get('close_now_debit_inr'),a.get('close_now_costs_inr'),obs.get('close_debit_inr'),o.get('exit_costs_inr')]):
            delta=number(a['close_now_debit_inr'])+number(a['close_now_costs_inr'])-number(obs['close_debit_inr'])-number(o['exit_costs_inr'])
            pair['counterfactual_hold_minus_close_inr']=delta
            if 'p_hold_beats_close' in a: pair['brier_score']=(number(a['p_hold_beats_close'])-float(delta>0))**2
        for k in ['actual_execution_costs_inr','actual_slippage_inr']:
            if o.get(k) is not None: pair[k]=number(o[k])
        g['pairs'].append(pair)
    result=[]
    for (role,model,horizon),g in groups.items():
        pairs=g['pairs']; clusters=sorted({p['cluster'] for p in pairs}); metrics={}
        for metric in {m for p in pairs for m in p['metrics']}:
            fields={k for p in pairs for k in p['metrics'].get(metric,{})}
            metrics[metric]={}
            for field in fields:
                means=[]
                for cluster in clusters:
                    vals=[p['metrics'][metric][field] for p in pairs if p['cluster']==cluster and field in p['metrics'].get(metric,{})]
                    if vals: means.append(statistics.mean(vals))
                metrics[metric][field]=statistics.mean(means)
            metrics[metric]['n_scored']=sum(metric in p['metrics'] for p in pairs)
        result.append({'forecast_role':role,'model_version':model,'horizon':horizon,'n_outcomes':len(pairs),'n_trade_cycle_clusters':len(clusters),'metrics_cluster_weighted':metrics,'pairs':pairs})
    actual=[g for g in result if g['forecast_role']=='ACTUAL']
    benchmarks=[g for g in result if g['forecast_role']!='ACTUAL']
    pending=lambda role:sum(r['record_type']=='FORECAST' and data(r).get('forecast_role')==role and not any(x['record_type']=='OUTCOME' and data(x).get('forecast_id')==r['review_id'] for x in current) for r in current)
    return {'status':'SCORED' if actual else 'INSUFFICIENT_EVIDENCE','groups':actual,'benchmark_groups':benchmarks,'pending_benchmarks':pending('BENCHMARK'),'excluded':exclusions,'pending_forecasts':pending('ACTUAL'),'legacy_unscored_reviews':sum(r['record_type']=='REVIEW' and not any(x['record_type']=='FORECAST' and x.get('parent_review_id')==r['review_id'] for x in current) for r in current),'note':'No automatic model promotion; no synthetic rows in production. Cluster counts are not proof of independence.'}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['status','score','append']); args=parser.parse_args()
    if args.command=='append': result=append_event(json.load(sys.stdin))
    else:
        rows=read_rows(); result=score(rows)
        if args.command=='status': result.update(total_rows=len(rows),ledger=str(LEDGER))
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':
    try: main()
    except (OSError,ValueError,KeyError,TypeError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e),'fallback_created':False})); sys.exit(2)
