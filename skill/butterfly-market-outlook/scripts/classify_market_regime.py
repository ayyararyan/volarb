#!/usr/bin/env python3
"""Classify the market regime for butterfly carry decisions.

The classifier separates observed market/path stress from external event hazard and
option-implied stress. It can therefore identify a dangerous latent-jump state in
which implied volatility looks calm while event/tail risk is high.
"""

import argparse
import json
import math
from pathlib import Path

STATES = {"CALM_CARRY", "TRANSITION", "LATENT_JUMP_RISK", "ACTIVE_STRESS", "UNKNOWN"}

PARAMS = {
    "CALM_CARRY": {"new_expiry_eve_allowed": True, "min_ocr_1_5": 0.50, "max_q90_break_even_buffer_ratio": 1.00, "tail_penalty": 0.00, "overnight_posture": "NORMAL"},
    "TRANSITION": {"new_expiry_eve_allowed": True, "min_ocr_1_5": 1.00, "max_q90_break_even_buffer_ratio": 0.80, "tail_penalty": 0.35, "overnight_posture": "CAUTIOUS"},
    "LATENT_JUMP_RISK": {"new_expiry_eve_allowed": False, "min_ocr_1_5": 1.25, "max_q90_break_even_buffer_ratio": 0.65, "tail_penalty": 0.85, "overnight_posture": "INTRADAY_PREFERRED"},
    "ACTIVE_STRESS": {"new_expiry_eve_allowed": False, "min_ocr_1_5": 1.50, "max_q90_break_even_buffer_ratio": 0.50, "tail_penalty": 1.00, "overnight_posture": "INTRADAY_ONLY_UNLESS_EXCEPTIONAL"},
    "UNKNOWN": {"new_expiry_eve_allowed": False, "min_ocr_1_5": 1.25, "max_q90_break_even_buffer_ratio": 0.65, "tail_penalty": 0.75, "overnight_posture": "DO_NOT_INITIATE_EXPIRY_EVE_CARRY"},
}

def load_json(path):
    return json.loads(Path(path).read_text())

def finite(x):
    try:
        y=float(x)
    except (TypeError, ValueError):
        return None
    return y if math.isfinite(y) else None

def pct(x):
    y=finite(x)
    return None if y is None else min(max(y,0.0),100.0)

def hazard_pct(x):
    y=finite(x)
    return None if y is None else min(max(y,0.0),3.0)/3.0*100.0

def weighted_mean(items):
    vals=[(v,w) for v,w in items if v is not None and w>0]
    if not vals:
        return None
    sw=sum(w for _,w in vals)
    return sum(v*w for v,w in vals)/sw

def max_available(values):
    vals=[v for v in values if v is not None]
    return max(vals) if vals else None

def classify(x):
    x=x or {}
    provided=str(x.get("state","")).upper()
    if provided in STATES and provided!="UNKNOWN" and not x.get("recompute",False):
        return {"engine":"v2.2-regime","state":provided,"source":"provided_state","confidence":str(x.get("confidence","provided")),"path_stress":pct(x.get("path_stress")),"event_hazard":pct(x.get("event_hazard")),"implied_stress":pct(x.get("implied_stress")),"complacency_gap":finite(x.get("complacency_gap")),"parameters":PARAMS[provided],"reasons":list(x.get("reasons",[]))}
    realized=pct(x.get("realized_vol_percentile"))
    gap=pct(x.get("gap_tail_percentile",x.get("gap_p90_percentile")))
    tail_freq=pct(x.get("tail_gap_frequency_percentile"))
    intraday_range=pct(x.get("intraday_range_percentile"))
    implied=pct(x.get("implied_vol_percentile",x.get("vix_percentile")))
    skew=pct(x.get("skew_stress_percentile"))
    term=pct(x.get("term_structure_stress_percentile"))
    event=hazard_pct(x.get("event_hazard_score"))
    geopolitical=hazard_pct(x.get("geopolitical_hazard_score"))
    macro=hazard_pct(x.get("macro_policy_hazard_score"))
    oil=hazard_pct(x.get("oil_fx_rates_hazard_score"))
    news=hazard_pct(x.get("news_uncertainty_score"))
    path_stress=weighted_mean([(realized,.35),(gap,.35),(tail_freq,.20),(intraday_range,.10)])
    implied_stress=weighted_mean([(implied,.55),(skew,.25),(term,.20)])
    event_hazard=max_available([event,geopolitical,macro,oil,news])
    core_coverage=sum(v is not None for v in (realized,gap,tail_freq,implied,event_hazard))
    reasons=[]
    if core_coverage<3 or implied_stress is None or event_hazard is None:
        state="UNKNOWN"; reasons.append("insufficient_regime_inputs")
    else:
        p=path_stress if path_stress is not None else 50.0
        i=implied_stress; e=event_hazard
        g=gap if gap is not None else p
        tf=tail_freq if tail_freq is not None else p
        complacency=max(e,p,g,tf)-i
        if p>=75.0 or (i>=75.0 and p>=55.0) or (g>=85.0 and tf>=70.0):
            state="ACTIVE_STRESS"; reasons.append("realized_or_tail_stress_is_high")
        elif (e>=65.0 and i<=45.0) or (g>=70.0 and i<=45.0) or (tf>=70.0 and i<=45.0):
            state="LATENT_JUMP_RISK"; reasons.append("event_or_tail_hazard_exceeds_implied_stress")
        elif p<=35.0 and e<=25.0 and g<=35.0 and tf<=35.0 and i<=55.0:
            state="CALM_CARRY"; reasons.append("realized_gap_and_event_risk_are_jointly_quiet")
        else:
            state="TRANSITION"; reasons.append("mixed_or_shifting_regime")
        if complacency>=30.0:
            reasons.append("large_complacency_gap")
    complacency_gap=None
    if implied_stress is not None:
        hazard_side=max_available([event_hazard,path_stress,gap,tail_freq])
        if hazard_side is not None:
            complacency_gap=hazard_side-implied_stress
    confidence="high" if core_coverage>=5 else "medium" if core_coverage>=4 else "low"
    return {"engine":"v2.2-regime","state":state,"source":"computed","confidence":confidence,"path_stress":path_stress,"event_hazard":event_hazard,"implied_stress":implied_stress,"complacency_gap":complacency_gap,"components":{"realized_vol_percentile":realized,"gap_tail_percentile":gap,"tail_gap_frequency_percentile":tail_freq,"intraday_range_percentile":intraday_range,"implied_vol_percentile":implied,"skew_stress_percentile":skew,"term_structure_stress_percentile":term},"parameters":PARAMS[state],"reasons":reasons,"note":"Regime labels are deterministic risk states, not forecasts. CALM_CARRY is necessary but not sufficient for an overnight butterfly; carry economics and all other hard gates must still pass."}

def main():
    ap=argparse.ArgumentParser(description="Classify butterfly market regime")
    ap.add_argument("--input",required=True)
    ap.add_argument("--pretty",action="store_true")
    args=ap.parse_args()
    print(json.dumps(classify(load_json(args.input)),indent=2 if args.pretty else None,sort_keys=True,allow_nan=False))

if __name__=="__main__":
    main()
