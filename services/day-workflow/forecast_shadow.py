#!/usr/bin/env python3
"""Transparent shadow scenario prototype. No trading, probabilities or model promotion."""
import json
import math
import statistics
import sys
from review_scorecard import active, data, number, read_rows, timestamp
from decision_table import payoff_cap

VERSION='joint-analog-black76-shadow-v1'
YEAR_SECONDS=365*24*3600


def black76(forward,strike,iv,years,rate,kind):
    f,k,v,t,r=map(number,(forward,strike,iv,years,rate))
    if f<=0 or k<=0 or v<0 or t<0 or kind not in {'CE','PE'}:
        raise ValueError('Invalid option inputs')
    sign=1 if kind=='CE' else -1
    discount=math.exp(-r*t)
    if t==0 or v==0: return discount*max(sign*(f-k),0)
    sd=v*math.sqrt(t); d1=math.log(f/k)/sd+sd/2; d2=d1-sd
    normal=lambda z: 0.5*(1+math.erf(z/math.sqrt(2)))
    return discount*sign*(f*normal(sign*d1)-k*normal(sign*d2))


def reprice(x, shock):
    start,end,expiry=map(timestamp,(x['as_of'],x['target_at'],x['expiry_at']))
    if not start<end<=expiry: raise ValueError('Target must be after as-of and no later than verified expiry time')
    f=number(x['forward'])*math.exp(number(shock['log_forward_return']))
    t=(expiry-end).total_seconds()/YEAR_SECONDS
    legs=x['legs']; payoff_cap(legs)
    bump=shock['iv_changes']; spread=number(shock['spread_multiplier'])
    if len(bump)!=len(legs) or spread<0: raise ValueError('Four-leg IV changes and nonnegative spread multiplier required')
    debit=0; marks=[]
    for leg,change in zip(legs,bump):
        iv=number(leg['iv'])+number(change)
        if iv<=0: raise ValueError('Nonpositive scenario IV; do not silently clip')
        mid=black76(f,leg['strike'],iv,t,x['rate'],leg['type'])
        half=number(leg['half_spread_points'])*spread
        if half<0: raise ValueError('Negative spread')
        qty=number(leg['qty'])
        price=mid+half if qty<0 else max(0,mid-half)
        if t==0: price=mid  # settlement intrinsic, costs handled separately
        debit-=qty*price
        marks.append({'type':leg['type'],'strike':leg['strike'],'iv':iv,'model_mid':mid,'model_exit_side':price})
    return {'close_debit_inr':debit,'forward':f,'legs':marks}


def select_analogs(rows,x):
    available=active(rows); ids={r['review_id']:r for r in available}; matches=[]; used=set()
    for r in sorted(available,key=lambda z:timestamp(z['recorded_at_ist']),reverse=True):
        if r['record_type']!='OUTCOME': continue
        o=data(r); f=ids.get(o.get('forecast_id'))
        if not f or o.get('quote_status')!='EXECUTABLE': continue
        a=data(f); state=a.get('state'); end=o.get('state')
        if not state or not end: continue
        if timestamp(o['observed_at'])>=timestamp(x['as_of']) or timestamp(r['recorded_at_ist'])>=timestamp(x['as_of']): continue
        if a.get('cluster_id')==x['cluster_id'] or a.get('cluster_id') in used: continue
        keys=['underlying','horizon','regime','dte_bucket','time_bucket','event_class']
        if any(state.get(k)!=x.get(k) or state.get(k) is None for k in keys): continue
        elapsed=(timestamp(a['target_at'])-timestamp(a['issued_at'])).total_seconds()
        horizon=(timestamp(x['target_at'])-timestamp(x['as_of'])).total_seconds()
        if abs(elapsed-horizon)>number(x.get('horizon_tolerance_seconds',60)): continue
        if abs((timestamp(o['observed_at'])-timestamp(a['target_at'])).total_seconds())>number(a.get('outcome_tolerance_seconds',60)): continue
        if len(state.get('ivs',[]))!=len(x['legs']) or len(end.get('ivs',[]))!=len(x['legs']): continue
        if state.get('leg_roles')!=[l['role'] for l in x['legs']] or end.get('leg_roles')!=state.get('leg_roles'): continue
        old_spread=number(state['spread_total_points'])
        if old_spread<=0: continue
        shock={'label':r['review_id'],'log_forward_return':math.log(number(end['forward'])/number(state['forward'])),'iv_changes':[number(v)-number(u) for u,v in zip(state['ivs'],end['ivs'])],'spread_multiplier':number(end['spread_total_points'])/old_spread}
        matches.append({'shock':shock,'outcome_at':o['observed_at'],'recorded_at':r['recorded_at_ist'],'cluster_id':a['cluster_id']}); used.add(a['cluster_id'])
    return matches


def quantile(xs,p):
    values=sorted(xs); i=(len(values)-1)*p; lo=int(i); hi=math.ceil(i)
    return values[lo]+(values[hi]-values[lo])*(i-lo)


def forecast(x,rows):
    payoff_cap(x['legs'])
    if len(x['legs'])!=4: raise ValueError('Prototype supports four-leg structures only')
    if not x.get('source_ref'): raise ValueError('State evidence required')
    reference=x.get('reference_only') is True and x.get('quote_status')=='HISTORICAL'
    if x.get('quote_status')!='EXECUTABLE' and not reference: raise ValueError('Fresh executable state or explicit historical reference-only mode required')
    if reference and (not x.get('reference_at') or not x.get('reference_assumptions')): raise ValueError('Historical reference time and assumptions required')
    base=reprice(x,{'log_forward_return':0,'iv_changes':[0]*4,'spread_multiplier':1})
    analogs=select_analogs(rows,x)
    minimum=int(x.get('minimum_clusters',30))
    if minimum<30: raise ValueError('Minimum research floor is 30 distinct trade cycles, not a validation guarantee')
    outcomes=[reprice(x,a['shock']) for a in analogs]
    stress=[dict(label=s['label'],**reprice(x,s)) for s in x.get('stress_scenarios',[])]
    pred={'close_debit_inr':{'point':base['close_debit_inr']}}
    enough=len(analogs)>=minimum
    if len(analogs)>=minimum:
        values=[o['close_debit_inr'] for o in outcomes]
        pred={'close_debit_inr':{'point':statistics.mean(values),'low':quantile(values,0.1),'high':quantile(values,0.9),'coverage':0.8}}
    return {'forecast_role':'BENCHMARK','model_version':'historical-reference-black76-v1' if reference else (VERSION if enough else 'constant-forward-iv-shadow-v1'),'mode':'HISTORICAL_CONDITIONAL_ONLY' if reference else 'SHADOW_ONLY','status':'CONDITIONAL_SCENARIOS_NOT_EXECUTABLE' if reference else ('UNVALIDATED_EMPIRICAL_FORECAST' if enough else 'BASELINE_ONLY_INSUFFICIENT_MATCHED_HISTORY'),'issued_at':x['as_of'],'reference_at':x.get('reference_at'),'reference_assumptions':x.get('reference_assumptions'),'target_at':x['target_at'],'horizon':x['horizon'],'cluster_id':x['cluster_id'],'predictions':pred,'baseline':{'close_debit_inr':number(x['current_close_debit_inr'])},'constant_forward_iv_decay_baseline':base,'baseline_quote_status':x['quote_status'],'close_now_debit_inr':x['current_close_debit_inr'],'close_now_costs_inr':x.get('close_now_costs_inr'),'n_distinct_training_cycles':len(analogs),'training_latest_outcome_at':max((a['outcome_at'] for a in analogs),key=timestamp,default=None),'training_latest_recorded_at':max((a['recorded_at'] for a in analogs),key=timestamp,default=None),'training_event_ids':[a['shock']['label'] for a in analogs],'stress_scenarios':stress,'state':{**{k:x[k] for k in ['underlying','horizon','regime','dte_bucket','time_bucket','event_class','forward']},'ivs':[l['iv'] for l in x['legs']],'leg_roles':[l['role'] for l in x['legs']],'spread_total_points':sum(2*number(l['half_spread_points']) for l in x['legs'])},'caveats':['Empirical interval is uncalibrated; not a real-world probability guarantee.','Fixed-strike per-leg IV shock approximation; no full volatility-surface arbitrage fit.','Forward input must match expiry; rate and settlement time must be verified.','Sparse event regimes may never supply enough analogs; stress scenarios carry no probabilities.','No automatic live promotion. Chronological scorecard comparison required.']}

if __name__=='__main__':
    try: print(json.dumps(forecast(json.load(sys.stdin),read_rows()),indent=2,allow_nan=False))
    except (ValueError,KeyError,TypeError,OSError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e),'fallback_created':False})); sys.exit(2)
