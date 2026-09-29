import copy
import json
import math
import unittest
from review_scorecard import validate_event, score, active
from decision_table import compare, payoff_cap, compare_portfolio
from forecast_shadow import black76, reprice, forecast, select_analogs

R={'review_id':'r','record_type':'REVIEW','strategy_id':'s','recorded_at_ist':'2026-09-01T10:00:00+05:30'}
A={'forecast_role':'ACTUAL','central_thesis':'synthetic prediction','confidence':'LOW','rationale':'test','evidence':'test','disconfirming_evidence':'test','invalidation':'test','issued_at':'2026-09-01T10:00:00+05:30','target_at':'2026-09-01T15:00:00+05:30','horizon':'INTRADAY','model_version':'test','cluster_id':'cycle1','predictions':{'close_debit_inr':{'point':100,'low':90,'high':110,'coverage':0.8}},'baseline':{'close_debit_inr':120},'close_now_debit_inr':120,'close_now_costs_inr':2,'baseline_quote_status':'EXECUTABLE'}
def event(rid,kind,a,when='2026-09-01T10:01:00+05:30'):
 return {'review_id':rid,'record_type':kind,'parent_review_id':'r','strategy_id':'s','recorded_at_ist':when,'analytics_json':json.dumps(a)}
F=event('f','FORECAST',A)
O=event('o','OUTCOME',{'forecast_id':'f','observed_at':'2026-09-01T15:00:00+05:30','source_ref':'synthetic-test-only','quote_status':'EXECUTABLE','observed':{'close_debit_inr':105},'exit_costs_inr':3},'2026-09-01T15:01:00+05:30')
LEGS=[{'qty':1,'strike':90,'type':'PE','iv':0.2,'half_spread_points':0.1,'role':'LONG_PUT'},{'qty':-1,'strike':100,'type':'PE','iv':0.2,'half_spread_points':0.1,'role':'SHORT_PUT'},{'qty':-1,'strike':100,'type':'CE','iv':0.2,'half_spread_points':0.1,'role':'SHORT_CALL'},{'qty':1,'strike':110,'type':'CE','iv':0.2,'half_spread_points':0.1,'role':'LONG_CALL'}]

def decision():
 return {'as_of':'2026-09-01T10:00:00+05:30','close_now':{'debit_inr':4,'costs_inr':0.2,'status':'EXECUTABLE','depth_verified':True,'as_of':'2026-09-01T09:59:50+05:30'},'legs':LEGS,'extra_cost_stress_inr':0.1,'max_additional_loss_inr':10,'hold':{'exit_cost_upper_bound_inr':0.4,'scenarios':[{'label':k,'close_debit_inr':v,'exit_costs_inr':0.3,'weight':w} for k,v,w in [('CALM',2,0.5),('UP',6,0.25),('DOWN',8,0.25)]]}}

def state():
 return {'as_of':'2026-09-01T10:00:00+05:30','target_at':'2026-09-01T15:00:00+05:30','expiry_at':'2026-09-02T15:30:00+05:30','forward':100,'rate':0.05,'legs':copy.deepcopy(LEGS),'source_ref':'synthetic-only','current_close_debit_inr':4,'quote_status':'EXECUTABLE','horizon':'INTRADAY','underlying':'TEST','cluster_id':'new','regime':'NORMAL','dte_bucket':'1-2','time_bucket':'10:00','event_class':'NONE'}

class ScoreTests(unittest.TestCase):
 def test_valid_link(self): validate_event(F,[R]);validate_event(O,[R,F])
 def test_duplicate(self):
  with self.assertRaises(ValueError):validate_event(F,[R,F])
 def test_late_forecast(self):
  f=dict(F,recorded_at_ist='2026-09-01T15:01:00+05:30')
  with self.assertRaises(ValueError):validate_event(f,[R])
 def test_training_leakage(self):
  a=dict(A,training_latest_outcome_at=A['target_at'])
  with self.assertRaises(ValueError):validate_event(event('f','FORECAST',a),[R])
 def test_future_outcome(self):
  with self.assertRaises(ValueError):validate_event(dict(O,recorded_at_ist=A['issued_at']),[R,F])
 def test_duplicate_outcome(self):
  with self.assertRaises(ValueError):validate_event(dict(O,review_id='o2'),[R,F,O])
 def test_corrected_outcome_preserves_history(self):
  o=dict(O,review_id='o2',supersedes_review_id='o');validate_event(o,[R,F,O]);self.assertEqual(len(active([R,F,O,o])),3)
 def test_score_and_counterfactual(self):
  g=score([R,F,O])['groups'][0];self.assertEqual(g['metrics_cluster_weighted']['close_debit_inr']['absolute_error'],5);self.assertEqual(g['pairs'][0]['counterfactual_hold_minus_close_inr'],14)
 def test_missing_cost_not_zero(self):
  a=json.loads(O['analytics_json']);a.pop('exit_costs_inr');o=dict(O,analytics_json=json.dumps(a));self.assertNotIn('counterfactual_hold_minus_close_inr',score([R,F,o])['groups'][0]['pairs'][0])
 def test_historical_excluded(self):
  a=json.loads(O['analytics_json']);a['quote_status']='HISTORICAL';self.assertEqual(score([R,F,dict(O,analytics_json=json.dumps(a))])['status'],'INSUFFICIENT_EVIDENCE')
 def test_late_outcome_excluded(self):
  a=json.loads(O['analytics_json']);a['observed_at']='2026-09-01T15:10:00+05:30';self.assertTrue(score([R,F,dict(O,analytics_json=json.dumps(a))])['excluded'])
 def test_benchmark_not_counted_as_forecast(self):
  a=dict(A,forecast_role='BENCHMARK');f=event('f','FORECAST',a);r=score([R,f,O]);self.assertEqual(r['groups'],[]);self.assertEqual(len(r['benchmark_groups']),1)
 def test_actual_requires_thesis(self):
  a=dict(A);a.pop('central_thesis')
  with self.assertRaises(ValueError):validate_event(event('f','FORECAST',a),[R])
 def test_directional_forecast_scoring(self):
  a=dict(A,predictions={},event_prediction={'metric':'close_debit_inr','operator':'LT','threshold':120,'predicted':True});f=event('f','FORECAST',a);validate_event(f,[R]);self.assertEqual(score([R,f,O])['groups'][0]['metrics_cluster_weighted']['event_prediction']['correct'],1)
 def test_empty_score(self):self.assertEqual(score([R])['legacy_unscored_reviews'],1)
 def test_trade_cycle_weighting(self):
  a=dict(A,model_version='test',predictions={'close_debit_inr':{'point':90}});f=event('f2','FORECAST',a);o=json.loads(O['analytics_json']);o['forecast_id']='f2';o=event('o2','OUTCOME',o,'2026-09-01T15:01:00+05:30');g=score([R,F,O,f,o])['groups'][0];self.assertEqual(g['n_trade_cycle_clusters'],1);self.assertEqual(g['metrics_cluster_weighted']['close_debit_inr']['absolute_error'],10)

class DecisionTests(unittest.TestCase):
 def test_payoff_cap(self):self.assertEqual(payoff_cap(LEGS),10)
 def test_unbounded(self):
  with self.assertRaises(ValueError):payoff_cap([{'qty':-1,'strike':100,'type':'CE'}])
 def test_hold_formula(self):
  r=compare(decision())['table'][1];self.assertAlmostEqual(r['scenarios'][0]['incremental_net_pnl_inr'],1.9);self.assertAlmostEqual(r['max_additional_loss_inr'],6.3)
 def test_unknown_budget(self):
  x=decision();x.pop('max_additional_loss_inr');self.assertEqual(compare(x)['table'][1]['risk_limit_status'],'UNKNOWN')
 def test_stale_quote_blocks(self):
  x=decision();x['close_now']['as_of']='2026-09-01T09:58:00+05:30';self.assertEqual(compare(x)['table'][1]['status'],'BLOCKED')
 def test_missing_cost_keeps_gross(self):
  x=decision();x['close_now'].pop('costs_inr');r=compare(x)['table'][1];self.assertEqual(r['scenarios'][0]['incremental_gross_pnl_inr'],2);self.assertEqual(r['max_additional_loss_gross_inr'],6)
 def test_missing_cost_blocks(self):
  x=decision();x['close_now'].pop('costs_inr');self.assertIsNone(compare(x)['table'][1]['scenario_weighted_incremental_inr'])
 def test_recenter_sunk_exit_cancels(self):
  x=decision();x['recenter']=copy.deepcopy(x['hold']);x['recenter'].update(legs=LEGS,entry={'credit_inr':5,'costs_inr':0.4,'status':'EXECUTABLE','depth_verified':True,'as_of':x['as_of']},legging_plan='Synthetic only');r=compare(x)['table'][2];self.assertAlmostEqual(r['scenarios'][0]['incremental_net_pnl_inr'],2.3)

 def test_portfolio_missing_limit(self):
  r=compare_portfolio({'positions':[decision()],'all_account_exposures_included':True});self.assertEqual(r['portfolio_risk_limit_status'],'UNKNOWN')
 def test_portfolio_combined_risk(self):
  r=compare_portfolio({'positions':[decision(),decision()],'all_account_exposures_included':True,'portfolio_max_additional_loss_inr':10});self.assertEqual(r['portfolio_risk_limit_status'],'FAIL');self.assertAlmostEqual(r['combined_hold_max_additional_loss_inr'],12.6)

class ForecastTests(unittest.TestCase):
 def test_put_call_parity(self):
  c=black76(100,105,0.2,0.5,0.05,'CE');p=black76(100,105,0.2,0.5,0.05,'PE');self.assertAlmostEqual(c-p,math.exp(-0.025)*-5)
 def test_known_atm(self):self.assertAlmostEqual(black76(100,100,0.2,1,0,'CE'),7.9655674554,places=8)
 def test_expiry_payoff(self):
  x=state();x['target_at']=x['expiry_at'];v=reprice(x,{'log_forward_return':math.log(1.2),'iv_changes':[0]*4,'spread_multiplier':1});self.assertAlmostEqual(v['close_debit_inr'],10)
 def test_insufficient_history_no_probability(self):
  r=forecast(state(),[]);self.assertEqual(r['status'],'BASELINE_ONLY_INSUFFICIENT_MATCHED_HISTORY');self.assertNotIn('coverage',r['predictions']['close_debit_inr']);self.assertNotIn('p_hold_beats_close',r)
 def test_target_after_expiry(self):
  x=state();x['target_at']='2026-09-03T15:00:00+05:30'
  with self.assertRaises(ValueError):forecast(x,[])
 def test_negative_iv_not_clipped(self):
  with self.assertRaises(ValueError):reprice(state(),{'log_forward_return':0,'iv_changes':[-1]*4,'spread_multiplier':1})
 def test_explicit_reference_mode(self):
  x=state();x.update(quote_status='HISTORICAL',reference_only=True,reference_at='2026-08-31T15:40:00+05:30',reference_assumptions='Synthetic retained-book test');self.assertEqual(forecast(x,[])['mode'],'HISTORICAL_CONDITIONAL_ONLY')
 def test_stale_initial_state_rejected(self):
  x=state();x['quote_status']='HISTORICAL'
  with self.assertRaises(ValueError):forecast(x,[])
 def test_matching_analog_and_cycle_exclusion(self):
  x=state();x['as_of']='2026-09-02T10:00:00+05:30';x['target_at']='2026-09-02T15:00:00+05:30'
  start=forecast(state(),[])['state'];end=copy.deepcopy(start);end['forward']=102
  a=dict(A,state=start);o=json.loads(O['analytics_json']);o['state']=end
  rows=[R,event('f','FORECAST',a),event('o','OUTCOME',o,'2026-09-01T15:01:00+05:30')]
  matches=select_analogs(rows,x);self.assertEqual(len(matches),1);self.assertAlmostEqual(matches[0]['shock']['log_forward_return'],math.log(1.02))
  x['cluster_id']='cycle1';self.assertEqual(select_analogs(rows,x),[])
 def test_late_available_training_excluded(self):
  x=state();x['as_of']='2026-09-02T10:00:00+05:30';x['target_at']='2026-09-02T15:00:00+05:30';s=forecast(state(),[])['state'];a=dict(A,state=s);o=json.loads(O['analytics_json']);o['state']=s;r=event('o','OUTCOME',o,'2026-09-03T10:00:00+05:30');self.assertEqual(select_analogs([R,event('f','FORECAST',a),r],x),[])

if __name__=='__main__':unittest.main()
