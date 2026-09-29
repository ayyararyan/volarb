#!/usr/bin/env python3
"""Offline incremental decision arithmetic. All INR amounts are total position amounts."""
import json
import sys
from review_scorecard import number, timestamp


def payoff_cap(legs):
    if not legs or any(number(x['strike'])<=0 or number(x['qty'])==0 or int(number(x['qty']))!=number(x['qty']) or x['type'] not in {'CE','PE'} for x in legs):
        raise ValueError('Invalid signed-unit legs')
    if sum(number(x['qty']) for x in legs if x['type']=='CE') < 0:
        raise ValueError('Unbounded call-side loss')
    def liability(s):
        return -sum(number(x['qty'])*max((s-number(x['strike'])) if x['type']=='CE' else (number(x['strike'])-s),0) for x in legs)
    grid=[0]+[number(x['strike']) for x in legs]
    return max(liability(s) for s in grid)


def quote_check(quote, asof, max_age):
    if quote.get('status')!='EXECUTABLE' or quote.get('depth_verified') is not True:
        return False
    age=(timestamp(asof)-timestamp(quote['as_of'])).total_seconds()
    return 0<=age<=max_age


def compare(x):
    asof=x['as_of']; timestamp(asof)
    q=x['close_now']; max_age=number(x.get('max_quote_age_seconds',30))
    if max_age<=0: raise ValueError('Positive quote freshness threshold required')
    valid=quote_check(q,asof,max_age)
    D=number(q['debit_inr']); cap=payoff_cap(x['legs'])
    c0=q.get('costs_inr'); stress=number(x['extra_cost_stress_inr'])
    if stress<0: raise ValueError('Negative stress buffer')
    if c0 is not None and number(c0)<0: raise ValueError('Negative costs')
    limit=x.get('max_additional_loss_inr')
    if limit is not None and number(limit)<0: raise ValueError('Negative loss budget')
    rows=[{'action':'CLOSE','incremental_net_pnl_inr':0 if valid and c0 is not None else None,'quote_status':'EXECUTABLE' if valid else 'REFERENCE_ONLY','note':'Zero is the comparison baseline, not total trade profit'}]
    for action in ['HOLD','RECENTER']:
        item=x.get(action.lower())
        if not item:
            rows.append({'action':action,'status':'NOT_PRICED'}); continue
        issues=[]
        if not valid: issues.append('Current exit quote stale/unverified')
        if c0 is None: issues.append('Current exit costs unknown')
        entry=0; entry_cost=0; newcap=cap
        if action=='RECENTER':
            if not item.get('legs'): issues.append('Replacement legs missing')
            else: newcap=payoff_cap(item['legs'])
            en=item.get('entry',{})
            if not quote_check(en,asof,max_age): issues.append('Replacement entry quote stale/unverified')
            entry=en.get('credit_inr'); entry_cost=en.get('costs_inr')
            if entry is None or entry_cost is None: issues.append('Replacement entry credit/costs unknown')
            if not item.get('legging_plan'): issues.append('Temporary legging exposure not assessed')
        scenarios=item.get('scenarios',[]); vals=[]; weights=[]; detail=[]
        labels={s['label'] for s in scenarios}
        if not {'CALM','UP','DOWN'}.issubset(labels): issues.append('Calm/up/down scenarios required')
        for s in scenarios:
            debit=number(s['close_debit_inr']); cost=s.get('exit_costs_inr')
            if cost is not None and number(cost)<0: raise ValueError('Negative exit costs')
            value=None
            if cost is not None and c0 is not None and entry is not None and entry_cost is not None:
                value=D+number(c0)-debit-number(cost) if action=='HOLD' else number(entry)-number(entry_cost)-debit-number(cost)
                vals.append(value)
            else: issues.append('Scenario costs missing')
            w=s.get('weight'); weights.append(None if w is None else number(w))
            gross=D-debit if action=='HOLD' else (None if entry is None else number(entry)-debit)
            detail.append({'label':s['label'],'incremental_gross_pnl_inr':gross,'incremental_net_pnl_inr':value,'stressed_incremental_net_pnl_inr':None if value is None else value-stress})
        weighted=None
        if vals and len(vals)==len(scenarios) and all(w is not None and w>=0 for w in weights) and abs(sum(weights)-1)<1e-8:
            weighted=sum(v*w for v,w in zip(vals,weights))
        future_cost_cap=item.get('exit_cost_upper_bound_inr')
        if future_cost_cap is not None and number(future_cost_cap)<0: raise ValueError('Negative cost bound')
        worst=None
        if future_cost_cap is not None and c0 is not None and entry is not None and entry_cost is not None:
            worst=max(0,newcap-D+number(future_cost_cap)-number(c0)+stress) if action=='HOLD' else max(0,newcap-number(entry)+number(entry_cost)+number(future_cost_cap)+stress)
        if limit is None: risk='UNKNOWN'
        elif worst is None: risk='UNKNOWN'
        else: risk='PASS' if worst<=number(limit) else 'FAIL'
        if risk!='PASS': issues.append('Risk limit '+risk)
        # User labels cannot promote a prototype to validated. No automatic live approval.
        status='BLOCKED' if issues else 'RESEARCH_ONLY'
        rows.append({'action':action,'status':status,'scenario_weighted_incremental_inr':weighted,'weighted_value_status':'INDICATIVE_NOT_VALIDATED_EXPECTATION' if weighted is not None else 'NO_SUPPORTED_WEIGHTS','adverse_scenario_incremental_inr':min(vals) if vals else None,'max_additional_loss_inr':worst,'max_additional_loss_gross_inr':max(0,cap-D) if action=='HOLD' else (None if entry is None else max(0,newcap-number(entry))),'risk_limit_status':risk,'stressed_weighted_incremental_inr':None if weighted is None else weighted-stress,'scenarios':detail,'issues':sorted(set(issues))})
    return {'as_of':asof,'table':rows,'decision_status':'ANALYST_REVIEW_REQUIRED','portfolio_risk_status':'NOT_ASSESSED_BY_SINGLE_POSITION_TABLE','note':'Recommendations never execute orders. Entry P&L and sunk losses do not change incremental comparison. Bounds include supplied cost bound/stress, not a guaranteed execution price.'}

def compare_portfolio(x):
    tables=[compare(p) for p in x['positions']]
    cap=x.get('portfolio_max_additional_loss_inr')
    if cap is not None and number(cap)<0: raise ValueError('Negative portfolio limit')
    held=[next(r for r in t['table'] if r['action']=='HOLD') for t in tables]
    losses=[r.get('max_additional_loss_inr') for r in held]
    total=sum(losses) if losses and all(v is not None for v in losses) else None
    complete=x.get('all_account_exposures_included') is True
    risk='UNKNOWN' if total is None or cap is None or not complete else ('PASS' if total<=number(cap) else 'FAIL')
    return {'positions':tables,'combined_hold_max_additional_loss_inr':total,'portfolio_risk_limit_status':risk,'note':'Conservative sum of position tail bounds; no diversification credit. PASS requires complete account exposures, known costs and user limit. Individual quote/evidence blockers still apply.'}

if __name__=='__main__':
    try:
        x=json.load(sys.stdin)
        print(json.dumps(compare_portfolio(x) if 'positions' in x else compare(x),indent=2,allow_nan=False))
    except (KeyError,ValueError,TypeError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e)})); sys.exit(2)
