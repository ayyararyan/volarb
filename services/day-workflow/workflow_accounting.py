"""Observed broker-fill ingress and cycle reconciliation using canonical accounting.

No ownership inference, synthetic fills, order endpoints or alternate live ledgers.
Pure normalization/reconciliation functions also support isolated synthetic tests.
"""
import argparse
import datetime as dt
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import day_workflow as w
import trade_ledger as trades
import review_scorecard as reviews
from workflow_observation import ROOT, decode, verified_account_evidence

BROKER, ACCOUNT = 'DHAN', 'DHAN_PRIMARY'


def amount(value):
    w.need(not isinstance(value, bool) and value is not None, 'NUMERIC_EVIDENCE_REQUIRED')
    return trades.decimal(value, 'broker numeric')


def broker_time(value):
    w.need(isinstance(value, str) and bool(value), 'BROKER_TIME_REQUIRED')
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=w.IST) if parsed.tzinfo is None else parsed.astimezone(w.IST)


def broker_fill(raw, source_ref, sha, at):
    side = raw['transactionType']
    w.need(side in {'BUY', 'SELL'}, 'UNKNOWN_FILL_SIDE')
    quantity = amount(raw['tradedQuantity'])
    w.need(quantity > 0 and quantity == int(quantity), 'INVALID_FILL_UNITS')
    when = broker_time(raw.get('exchangeTime') or raw.get('createTime'))
    w.need(when.date() == at.date() and when <= at, 'FILL_OUTSIDE_CURRENT_SESSION')
    segment = raw['exchangeSegment']
    w.need(segment in {'NSE_FNO', 'BSE_FNO'}, 'NON_INDEX_OPTION_TRADE_REQUIRES_MANUAL_RECONCILIATION')
    option = {'PUT':'PE', 'CALL':'CE'}.get(raw['drvOptionType'], raw['drvOptionType'])
    name = raw['tradingSymbol']
    # Contract symbol is used only for underlying naming, never cycle assignment.
    underlying = next((s for s in ('BANKNIFTY','NIFTY','SENSEX') if name.startswith(s)), None)
    w.need(underlying is not None, 'UNKNOWN_INDEX_CONTRACT')
    w.need(str(raw['securityId']).isdigit(), 'INVALID_SECURITY_ID')
    fid = str(raw.get('exchangeTradeId') or raw.get('tradeId') or '')
    w.need(fid and raw.get('orderId'), 'BROKER_FILL_AND_ORDER_IDS_REQUIRED')
    return trades.normalize(dict(event_type='FILL', event_time=when.isoformat(), trading_date=when.date().isoformat(),
        broker=BROKER, account_alias=ACCOUNT, source_record_id=fid, source_ref=source_ref, source_sha256=sha,
        source_kind='BROKER_EXPORT', provenance='OBSERVED', exchange=segment.split('_')[0], segment='FNO',
        security_id=str(raw['securityId']), symbol=name, underlying=underlying,
        expiry=raw['drvExpiryDate'][:10], strike=raw['drvStrikePrice'], option_type=option,
        product=raw['productType'], broker_order_id=str(raw['orderId']), broker_fill_id=fid, side=side,
        quantity_units=str(quantity if side=='BUY' else -quantity), price_per_unit=raw['tradedPrice'], currency='INR'))


ECONOMIC = ('event_time','trading_date','broker','account_alias','exchange','segment','security_id','underlying',
            'expiry','strike','option_type','product','broker_order_id','broker_fill_id','side','quantity_units','price_per_unit')


def same_fill(a, b):
    return all((w.stamp(a[k]) == w.stamp(b[k])) if k == 'event_time' else a[k] == b[k] for k in ECONOMIC)


def observed_fills(evidence, source_ref, sha, at):
    found = {}
    for raw in evidence['endpoints']['trades']['data']:
        row = broker_fill(raw, source_ref, sha, at)
        key = trades.identity(row)
        w.need(key not in found or same_fill(found[key], row), 'CONFLICTING_BROKER_FILL_DUPLICATE')
        found[key] = row
    return list(found.values())


def linked_rows(rows):
    active = trades.validate_rows(rows)
    links = {r['reference_event_id']:r for r in active if r['event_type']=='ASSIGNMENT'}
    output = []
    fields = ('strategy_id','cycle_id','strategy_version','leg_id','lifecycle_role','linkage_provenance')
    for row in active:
        item = dict(row)
        if row['event_id'] in links:
            link = links[row['event_id']]
            w.need(not row['cycle_id'] or all(row[k] == link[k] for k in fields), 'CONFLICTING_CYCLE_ASSIGNMENT')
            item.update({k:link[k] for k in fields})
        output.append(item)
    return output


def preview_import(evidence, receipt, rows, at):
    observed = observed_fills(evidence, receipt['evidence_manifest'], receipt['evidence_sha256'], at)
    existing = {trades.identity(r): r for r in trades.validate_rows(rows) if r['event_type']=='FILL'}
    new = []
    for row in observed:
        prior = existing.get(trades.identity(row))
        if prior:
            w.need(same_fill(prior,row), 'BROKER_LEDGER_FILL_CONFLICT')
        else:
            new.append(row)  # no guessed cycle, order ownership or lot size
    return new


def reconcile(evidence, receipt, rows, cycle_id, at):
    w.need(isinstance(cycle_id,str) and bool(cycle_id.strip()), 'EXPLICIT_CYCLE_ID_REQUIRED')
    active = linked_rows(rows)
    owned = [r for r in active if r['cycle_id']==cycle_id and r['broker']==BROKER and r['account_alias']==ACCOUNT]
    w.need(owned and all(r['event_type'] in {'FILL','ASSIGNMENT'} for r in owned), 'COMPLETE_INTRADAY_FILL_BASIS_REQUIRED')
    fills = [r for r in owned if r['event_type']=='FILL']
    w.need(fills and all(r['trading_date']==at.date().isoformat() for r in fills), 'CYCLE_NOT_CURRENT_INTRADAY')
    w.need(len({r['strategy_id'] for r in fills})==1 and len({(r['underlying'],r['expiry']) for r in fills})==1,
           'CYCLE_IDENTITY_CONFLICT')
    w.need(all(r['product']=='INTRADAY' and r['lifecycle_role'] in {'ENTRY','EXIT'} for r in fills), 'UNSUPPORTED_PRODUCT_OR_RECENTER')
    today = [r for r in active if r['event_type']=='FILL' and r['broker']==BROKER and r['account_alias']==ACCOUNT and r['trading_date']==at.date().isoformat()]
    w.need(all(r['cycle_id']==cycle_id for r in today), 'OTHER_OR_UNASSIGNED_DAY_FILLS')
    observed = observed_fills(evidence, receipt['evidence_manifest'], receipt['evidence_sha256'], at)
    book = {trades.identity(r):r for r in observed}
    w.need(set(book)=={trades.identity(r) for r in fills}, 'BROKER_FILL_COVERAGE_MISMATCH')
    w.need(all(same_fill(r,book[trades.identity(r)]) for r in fills), 'BROKER_LEDGER_FILL_CONFLICT')
    contracts = {}
    for r in fills:
        key=(r['exchange']+'_FNO',r['security_id'],r['product'])
        previous=contracts.setdefault(key, {'row':r,'quantity':0,'entry':0,'exit':0})
        w.need(trades.instrument_key(previous['row']) == trades.instrument_key(r), 'RECYCLED_CONTRACT_ID')
        quantity=int(r['quantity_units'])
        previous['quantity']+=quantity
        previous[r['lifecycle_role'].lower()]+=quantity
    w.need(len(contracts)==4, 'EXACT_FOUR_CONTRACT_BASIS_REQUIRED')
    bytype={o:sorted((v for v in contracts.values() if v['row']['option_type']==o),key=lambda v:amount(v['row']['strike'])) for o in ('PE','CE')}
    w.need(len(bytype['PE'])==len(bytype['CE'])==2, 'IRON_BUTTERFLY_GEOMETRY_REQUIRED')
    roles=dict(zip(w.ROLES,[bytype['PE'][0],bytype['PE'][1],bytype['CE'][1],bytype['CE'][0]]))
    lower,body,upper,callbody=[amount(roles[r]['row']['strike']) for r in w.ROLES]
    w.need(lower < body == callbody < upper and body-lower==upper-body, 'SYMMETRIC_IRON_FLY_REQUIRED')
    lots={amount(v['row']['lot_size_units']) for v in contracts.values() if v['row']['lot_size_units']}
    w.need(len(lots)==1 and all(v['row']['lot_size_units'] for v in contracts.values()), 'VERIFIED_CONTRACT_LOT_REQUIRED')
    lot=lots.pop()
    w.need(all(r['lot_size_units'] and amount(r['lot_size_units'])==lot for r in fills), 'INCONSISTENT_FILL_LOT_SIZE')
    w.need(lot>0 and lot==int(lot), 'INVALID_LOT_SIZE')
    for role,v in roles.items():
        sign=w.SIGNS[role]
        w.need(v['entry']==sign*lot and 0<=sign*v['quantity']<=lot and sign*v['exit']<=0, 'PARTIAL_OVERSIZE_OR_REENTRY_CYCLE')
    w.need(roles['putWing']['quantity']>=-roles['putBody']['quantity'] and roles['callWing']['quantity']>=-roles['callBody']['quantity'], 'UNHEDGED_RESIDUAL')
    positions={}
    for p in evidence['endpoints']['positions_after']['data']:
        q=amount(p['netQty'])
        if q==0: continue
        key=(p['exchangeSegment'],str(p['securityId']),p['productType'])
        w.need(key in contracts and key not in positions, 'UNASSIGNED_OR_DUPLICATE_POSITION')
        row=contracts[key]['row']
        w.need(p['drvExpiryDate'][:10]==row['expiry'] and amount(p['drvStrikePrice'])==amount(row['strike']) and
            {'PUT':'PE','CALL':'CE'}.get(p['drvOptionType'],p['drvOptionType'])==row['option_type'], 'BROKER_POSITION_CONTRACT_MISMATCH')
        positions[key]=q
    w.need(all(positions.get(k,0)==v['quantity'] for k,v in contracts.items()), 'FILL_POSITION_MISMATCH')
    w.need(evidence['account']['pending_order_count']==0, 'PENDING_ORDERS_PREVENT_RECONCILIATION')
    closed=not any(v['quantity'] for v in contracts.values())
    result={'status':'RECONCILED','cycle_id':cycle_id,'strategy_id':fills[0]['strategy_id'],
        'symbol':fills[0]['underlying'],'expiry':fills[0]['expiry'],'closed':closed,'lot_size':int(lot),
        'fill_ids':[r['event_id'] for r in fills], 'source_ref':receipt['evidence_manifest'],
        'asof':at.isoformat(),'net_liquidation_pnl_rupees':None,'valuation_status':'UNAVAILABLE',
        'remaining_units':sum(abs(v['quantity']) for v in contracts.values()), 'cost_event_ids':[]}
    if not closed and any(v['quantity']!=w.SIGNS[role]*lot for role,v in roles.items()):
        result['status']='PARTIAL_EXIT_REQUIRES_RECOVERY'
        return result
    cash=sum((amount(r['gross_cashflow']) for r in fills),Decimal(0))
    result['gross_cashflow_rupees']=float(cash)
    costs=[r for r in active if r['event_type']=='COST' and r['broker']==BROKER and r['account_alias']==ACCOUNT and r['trading_date']==at.date().isoformat() and r['currency']=='INR']
    # Only a recorded complete TOTAL charge can establish complete daily costs.
    total=[r for r in costs if r['cost_component']=='TOTAL']
    if len(total)!=1 or amount(total[0]['gross_cashflow'])>0:
        result['valuation_blocker']='COMPLETE_RECORDED_COSTS_UNAVAILABLE'
        return result
    w.need(max(w.stamp(r['event_time']) for r in fills)<=w.stamp(total[0]['event_time'])<=at, 'COST_EVIDENCE_DOES_NOT_COVER_FILLS')
    charges=-amount(total[0]['gross_cashflow'])
    result['incurred_charges_rupees']=float(charges)
    result['cost_event_ids']=[total[0]['event_id']]
    if not closed:
        # Costs for future liquidation remain a separately supplied conservative bound.
        endpoint=evidence['endpoints'].get('position_quotes',{})
        w.need(endpoint.get('status')=='OK', 'EXECUTABLE_POSITION_QUOTES_REQUIRED')
        w.fresh(endpoint['requested_at'],at)
        w.fresh(endpoint['received_at'],at)
        quotes={(q['exchangeSegment'],str(q['securityId'])):q for q in endpoint['data']}
        w.need(len(quotes)==len(endpoint['data']), 'DUPLICATE_POSITION_QUOTES')
        for key,v in contracts.items():
            q=quotes[key[:2]]
            w.fresh(broker_time(q['last_trade_time']).isoformat(),at)
            bid,ask=amount(q['bid']),amount(q['ask'])
            w.need(0<bid<=ask, 'INVALID_LIQUIDATION_BOOK')
            qty=v['quantity']
            w.need(amount(q['bid_size' if qty>0 else 'ask_size'])>=abs(qty), 'INSUFFICIENT_LIQUIDATION_DEPTH')
            cash+=qty*(bid if qty>0 else ask)
    result.update(valuation_status='RECONCILED',gross_liquidation_pnl_rupees=float(cash),
        net_liquidation_pnl_rupees=float(cash-charges), costs_included=True, basis='ALL_CYCLE_FILLS')
    return result


def commit_fills(manifest_file, *, now=None):
    """Explicit ingress only; uses existing writer, leaves new fills UNASSIGNED."""
    at=now or dt.datetime.now(w.IST)
    receipt,evidence=verified_account_evidence(manifest_file,now=at)
    w.need(trades.DEFAULT_LEDGER.is_file(), 'CANONICAL_TRADE_LEDGER_MISSING')
    # Serialize adapter invocations; trade writer retains its own canonical lock.
    import fcntl
    with (reviews.ROOT/'ledger/.workflow_accounting.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rows=trades.read_ledger(trades.DEFAULT_LEDGER)
        incoming=preview_import(evidence,receipt,rows,at)
        written=trades.import_rows(trades.DEFAULT_LEDGER,incoming)
        check=trades.read_ledger(trades.DEFAULT_LEDGER)
        w.need(not preview_import(evidence,receipt,check,at), 'FILL_IMPORT_READBACK_FAILED')
        return {'status':'FILLS_IMPORTED','unassigned_new_fills':written['added'],
            'trade_ledger_written':written['added']>0,'cycle_assignment_inferred':False,
            'review_ledger_written':False,'orders_sent':False,'jobs_scheduled':False}


def commit_cycle(manifest_file, cycle_id, parent_review_id, *, now=None):
    """Persist verified execution audit and (if flat) closure through shared writers.

    No source is created, cycle inferred, fee guessed or broker action performed.
    Review append and summary projection retain the canonical writer's recovery rules.
    """
    at = now or dt.datetime.now(w.IST)
    receipt, evidence = verified_account_evidence(manifest_file, now=at)
    import fcntl
    with (reviews.ROOT/'ledger/.workflow_accounting.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with trades.locked(trades.DEFAULT_LEDGER):
            rows = trades.read_ledger(trades.DEFAULT_LEDGER)
            state = reconcile(evidence, receipt, rows, cycle_id, at)
            w.need(state['status'] == 'RECONCILED', 'PARTIAL_CYCLE_CANNOT_BE_FINALIZED')
            history = reviews.read_rows()
            parents = [r for r in reviews.active(history) if r['review_id']==parent_review_id and r['record_type']=='REVIEW']
            w.need(len(parents)==1, 'EXISTING_ACTIVE_REVIEW_REQUIRED')
            parent = parents[0]
            w.need(parent['strategy_id']==state['strategy_id'] and
                   reviews.data(parent).get('accounting',{}).get('cycle_id')==cycle_id, 'PARENT_CYCLE_MISMATCH')
            linked = {r['event_id']:r for r in linked_rows(rows)}
            appended = []
            for fid in state['fill_ids']:
                row = linked[fid]
                rid = 'workflow-execution-'+fid
                old = [r for r in reviews.read_rows() if r['review_id']==rid]
                if old:
                    w.need(reviews.data(old[0]).get('trade_event_id')==fid and old[0]['strategy_id']==state['strategy_id'], 'EXECUTION_AUDIT_CONFLICT')
                    continue
                event = {'review_id':rid, 'record_type':'EXECUTION','strategy_id':state['strategy_id'],
                    'parent_review_id':parent_review_id,'analytics_json':{
                        'source_ref':row['source_ref'],'trade_event_id':fid,'cycle_id':cycle_id,
                        'broker_fill_id':row['broker_fill_id'],'event_time':row['event_time'],
                        'signed_quantity_units':int(row['quantity_units']), 'price_per_unit':row['price_per_unit']}}
                reviews.append_event(event)
                appended.append(rid)
            closure_id = None
            if state['closed']:
                closure_id = 'workflow-closure-'+hashlib.sha256(json.dumps([cycle_id,sorted(state['fill_ids']),state['cost_event_ids']]).encode()).hexdigest()[:24]
                previous = next((r for r in reviews.read_rows() if r['review_id']==closure_id),None)
                if not previous:
                    retain=('strategy_id','underlying','expiry','lot_size','long_put_strike',
                            'short_put_strike','short_call_strike','long_call_strike')
                    event = {k:parent[k] for k in retain if k in parent}
                    old_closures=[r for r in reviews.active(reviews.read_rows()) if
                        r['review_id'].startswith('workflow-closure-') and
                        reviews.data(r).get('accounting',{}).get('cycle_id')==cycle_id]
                    w.need(len(old_closures)<=1, 'MULTIPLE_ACTIVE_CLOSURE_RECORDS')
                    for key in ('recorded_at_ist','supersedes_review_id','parent_review_id'):
                        event.pop(key,None)
                    known_costs = state['valuation_status']=='RECONCILED'
                    event.update(review_id=closure_id,record_type='REVIEW',review_as_of_ist=at.isoformat(),
                        structure='CLOSED_IRON_BUTTERFLY',source_refs=state['source_ref'],
                        prior_realized_pnl_inr=str(state['gross_cashflow_rupees']),broker_open_pnl_inr='0',
                        charges_inr=str(state['incurred_charges_rupees']) if known_costs else '',
                        basis_status='RECONCILED',prior_realized_status='RECONCILED',
                        charges_status='RECONCILED' if known_costs else 'UNAVAILABLE',quote_status='NOT_APPLICABLE',
                        analytics_json={'source_ref':state['source_ref'],'accounting':{
                            'cycle_id':cycle_id,'state':'CLOSED','remaining_units':0,
                            'closed_at':at.isoformat(),'closure_source_ref':state['source_ref']},
                            'reconciled_fill_ids':state['fill_ids'],
                            'net_realized_pnl_rupees':state['net_liquidation_pnl_rupees']})
                    if old_closures:
                        event['supersedes_review_id']=old_closures[0]['review_id']
                    for key,value in {'units_per_leg':'0','lots_per_leg':'0','regular_open_order_count':'0',
                            'execution_status':'VERIFIED_CLOSED','recommendation':'NO POSITION',
                            'findings':'Verified fill/position closure; no new market outlook',
                            'next_review_at_ist':'','reminder_configured':'NO'}.items():
                        if key in parent: event[key]=value
                    # Preserve established opening-time evidence, never manufacture it.
                    for key in ('opened_at','entry_source_ref'):
                        value=reviews.data(parent).get('accounting',{}).get(key)
                        if value: event['analytics_json']['accounting'][key]=value
                    reviews.append_event(event)
                    appended.append(closure_id)
            # Retry also repairs a previously committed event whose projection failed.
            from simple_ledger import refresh
            with (reviews.ROOT/'ledger/.butterfly_reviews.lock').open('a') as review_lock:
                fcntl.flock(review_lock,fcntl.LOCK_EX)
                refresh(reviews.read_rows(),reviews.ROOT)
            return {'status':'CYCLE_AUDIT_RECORDED','appended_ids':appended,'closure_id':closure_id,
                    'journal_published':False,'orders_sent':False,'jobs_scheduled':False,
                    'net_realized_pnl_rupees':state['net_liquidation_pnl_rupees'] if state['closed'] else None}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--preview',action='store_true')
    group.add_argument('--commit-fills',action='store_true')
    group.add_argument('--commit-cycle',action='store_true')
    parser.add_argument('--cycle-id')
    parser.add_argument('--parent-review-id')
    args=parser.parse_args()
    if args.commit_cycle:
        w.need(args.cycle_id and args.parent_review_id, 'CYCLE_AND_PARENT_REQUIRED')
        result=commit_cycle(args.manifest,args.cycle_id,args.parent_review_id)
    elif args.commit_fills:
        result=commit_fills(args.manifest)
    else:
        at=dt.datetime.now(w.IST)
        receipt,evidence=verified_account_evidence(args.manifest,now=at)
        incoming=preview_import(evidence,receipt,trades.read_ledger(trades.DEFAULT_LEDGER),at)
        result={'status':'PREVIEW_ONLY','new_unassigned_fill_count':len(incoming),'ledger_written':False}
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
