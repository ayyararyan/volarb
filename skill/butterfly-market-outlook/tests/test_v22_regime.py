#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from classify_market_regime import classify
from evaluate_overnight_carry import evaluate
from optimize_butterflies import overnight_stress_metrics

def stress(same,p15,p20=-600.0):
    return {'same_state_open_pnl_points':same,'full_reprice':True,'stress_scenarios':[
        {'straddle_multiple':1.0,'direction':'down','pnl_points':-100.0},
        {'straddle_multiple':1.0,'direction':'up','pnl_points':-90.0},
        {'straddle_multiple':1.5,'direction':'down','pnl_points':p15},
        {'straddle_multiple':1.5,'direction':'up','pnl_points':p15+20.0},
        {'straddle_multiple':2.0,'direction':'down','pnl_points':p20},
        {'straddle_multiple':2.0,'direction':'up','pnl_points':p20+30.0}]}

def benign_gap_gate():
    return {'required':True,'reference_spot':23000.0,'net_gamma':-0.0003,'nearest_break_even_buffer_points':500.0,'gap_pct':[-0.12,0.08,-0.18,0.15,-0.05,0.20,-0.10,0.16,-0.07,0.11,-0.14,0.09,-0.22,0.17,-0.06,0.13,-0.19,0.04,0.10,-0.15]}

def base(regime):
    return {'mode':'rotation_entry','crosses_market_close':True,'expiry_sessions_remaining':1,'market_actionable':True,'broker':{'status':'PASS'},'events':[{'severity':'low','inside_untradeable_window':True}],'market_regime':regime,'empirical_gap_gate':benign_gap_gate()}

def test_classifier_marks_true_boring_period_calm_carry():
    out=classify({'realized_vol_percentile':18,'gap_tail_percentile':15,'tail_gap_frequency_percentile':12,'intraday_range_percentile':20,'implied_vol_percentile':28,'skew_stress_percentile':25,'term_structure_stress_percentile':20,'event_hazard_score':0.3,'geopolitical_hazard_score':0.2,'macro_policy_hazard_score':0.4,'oil_fx_rates_hazard_score':0.2})
    assert out['state']=='CALM_CARRY'

def test_classifier_marks_low_vix_high_hazard_latent_jump_risk():
    out=classify({'realized_vol_percentile':42,'gap_tail_percentile':82,'tail_gap_frequency_percentile':78,'intraday_range_percentile':45,'implied_vol_percentile':25,'skew_stress_percentile':40,'term_structure_stress_percentile':35,'event_hazard_score':2.6,'geopolitical_hazard_score':2.8,'macro_policy_hazard_score':1.8,'oil_fx_rates_hazard_score':2.5})
    assert out['state']=='LATENT_JUMP_RISK' and out['complacency_gap']>30

def test_classifier_marks_obvious_turbulence_active_stress():
    assert classify({'realized_vol_percentile':91,'gap_tail_percentile':88,'tail_gap_frequency_percentile':85,'intraday_range_percentile':90,'implied_vol_percentile':86,'event_hazard_score':2.0})['state']=='ACTIVE_STRESS'

def test_latent_jump_regime_blocks_expiry_eve_even_if_old_gates_pass():
    out=evaluate(base({'state':'LATENT_JUMP_RISK'})|stress(300.0,-250.0))
    assert out['operational_state']=='BLOCK' and 'market_regime_blocks_new_expiry_eve_carry' in out['hard_failures']

def test_transition_regime_requires_stronger_ocr_than_calm():
    out=evaluate(base({'state':'TRANSITION'})|stress(240.0,-300.0))
    assert out['operational_state']=='BLOCK' and 'regime_adjusted_stress_efficiency_fail' in out['hard_failures']

def test_calm_regime_keeps_same_trade_eligible():
    assert evaluate(base({'state':'CALM_CARRY'})|stress(240.0,-300.0))['operational_state']=='CARRY_ELIGIBLE'

def test_missing_regime_blocks_new_expiry_eve_trade():
    out=evaluate(base({})|stress(300.0,-250.0))
    assert out['operational_state']=='BLOCK' and 'new_expiry_eve_requires_market_regime' in out['hard_failures']

def test_optimizer_applies_regime_gate_before_ranking():
    def side(bid,ask,iv=0.20): return {'bid':bid,'ask':ask,'iv':iv,'greeks':{'gamma':0.0004}}
    rows=[{'strike':22500.0,'put':side(45,47),'call':side(545,547),'call_mark':546.0,'iv':0.20},{'strike':23000.0,'put':side(120,122),'call':side(120,122),'call_mark':121.0,'iv':0.20},{'strike':23500.0,'put':side(542,544),'call':side(42,44),'call_mark':43.0,'iv':0.20}]
    meta={'spot':23000.0,'forward':23000.0,'t':2.0/365.0,'df':0.9997,'r':0.06}
    cfg={'overnight_carry':{'active':True,'mode':'candidate_entry','expiry_sessions_remaining':1,'broker_feasibility_status':'PASS','market_regime':{'state':'LATENT_JUMP_RISK'},'empirical_gap_gate':benign_gap_gate(),'events':[{'severity':'low','inside_untradeable_window':True}],'hours_to_next_actionable_exit':18.5}}
    out=overnight_stress_metrics(rows,cfg,rows,meta,153.0,347.0,1.0,net_gamma=-0.0004)
    assert out['status']=='BLOCK' and out['market_regime']['state']=='LATENT_JUMP_RISK'

def run():
    tests=[v for k,v in globals().items() if k.startswith('test_') and callable(v)]
    for t in tests: t(); print('PASS',t.__name__)
    print(f'{len(tests)} tests passed')

if __name__=='__main__': run()
