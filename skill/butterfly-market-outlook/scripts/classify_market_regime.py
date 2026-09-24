#!/usr/bin/env python3
"""Classify the market regime for butterfly carry decisions.

Engine v2.4 separates realized/path stress, option-implied stress, and calibrated
news/event hazard. Current raw-news interpretation belongs to the child
``market-news-signal-filter`` skill; this script consumes only its normalized packet.
The output is a deterministic risk state, not a forecast probability.
"""

import argparse
import json
import math
from pathlib import Path

STATES = {"CALM_CARRY", "TRANSITION", "LATENT_JUMP_RISK", "ACTIVE_STRESS", "UNKNOWN"}

PARAMS = {
    "CALM_CARRY": {
        "new_expiry_eve_allowed": True,
        "min_ocr_1_5": 0.50,
        "max_q90_break_even_buffer_ratio": 1.00,
        "tail_penalty": 0.00,
        "overnight_posture": "NORMAL",
    },
    "TRANSITION": {
        "new_expiry_eve_allowed": True,
        "min_ocr_1_5": 1.00,
        "max_q90_break_even_buffer_ratio": 0.80,
        "tail_penalty": 0.35,
        "overnight_posture": "CAUTIOUS",
    },
    "LATENT_JUMP_RISK": {
        "new_expiry_eve_allowed": False,
        "min_ocr_1_5": 1.25,
        "max_q90_break_even_buffer_ratio": 0.65,
        "tail_penalty": 0.85,
        "overnight_posture": "INTRADAY_PREFERRED",
    },
    "ACTIVE_STRESS": {
        "new_expiry_eve_allowed": False,
        "min_ocr_1_5": 1.50,
        "max_q90_break_even_buffer_ratio": 0.50,
        "tail_penalty": 1.00,
        "overnight_posture": "INTRADAY_ONLY_UNLESS_EXCEPTIONAL",
    },
    "UNKNOWN": {
        "new_expiry_eve_allowed": False,
        "min_ocr_1_5": 1.25,
        "max_q90_break_even_buffer_ratio": 0.65,
        "tail_penalty": 0.75,
        "overnight_posture": "DO_NOT_INITIATE_EXPIRY_EVE_CARRY",
    },
}

NEWS_STATE_PCT = {
    "CALM": 0.0,
    "NOISY_BUT_BENIGN": 20.0,
    "EVENTFUL": 50.0,
    "HIGH_UNCERTAINTY": 80.0,
    "TAIL_RISK_ACTIVE": 100.0,
    "UNKNOWN": None,
}
GAP_RISK_PCT = {"none": 0.0, "low": 20.0, "moderate": 45.0, "high": 75.0, "extreme": 100.0, "unknown": None}
RELEVANCE_PCT = {"ignore": 0.0, "watch": 25.0, "material": 70.0, "critical": 100.0, "unknown": None}
OVERNIGHT_PCT = {"none": 0.0, "low": 20.0, "moderate": 45.0, "high": 75.0, "extreme": 100.0, "unknown": None}


def load_json(path):
    return json.loads(Path(path).read_text())


def finite(x):
    try:
        y = float(x)
    except (TypeError, ValueError):
        return None
    return y if math.isfinite(y) else None


def pct(x):
    y = finite(x)
    if y is None:
        return None
    return min(max(y, 0.0), 100.0)


def hazard_pct(x):
    y = finite(x)
    if y is None:
        return None
    return min(max(y, 0.0), 3.0) / 3.0 * 100.0


def weighted_mean(items):
    vals = [(v, w) for v, w in items if v is not None and w > 0]
    if not vals:
        return None
    sw = sum(w for _, w in vals)
    return sum(v * w for v, w in vals) / sw


def max_available(values):
    vals = [v for v in values if v is not None]
    return max(vals) if vals else None


def _mapped(mapping, value):
    if value is None:
        return None
    return mapping.get(str(value).strip().lower() if all(k.islower() for k in mapping) else str(value).strip().upper())


def normalize_news_filter(nf):
    """Convert the child-skill packet to a single calibrated event-hazard contribution."""
    if not isinstance(nf, dict) or not nf:
        return {
            "status": "UNAVAILABLE",
            "calibration_asof": None,
            "aggregate_state": "UNKNOWN",
            "hazard_pct": None,
            "dominant_channels": [],
            "reasons": ["news_filter_unavailable"],
        }

    status = str(nf.get("status", nf.get("calibration_status", "CURRENT"))).upper()
    if status not in {"CURRENT", "STALE_CALIBRATION", "UNAVAILABLE", "INVALID"}:
        status = "INVALID"

    agg = str(nf.get("aggregate_state", "UNKNOWN")).upper()
    state_h = NEWS_STATE_PCT.get(agg)
    gap_h = GAP_RISK_PCT.get(str(nf.get("max_gap_risk", "unknown")).lower())
    rel_h = RELEVANCE_PCT.get(str(nf.get("max_butterfly_relevance", "unknown")).lower())
    overnight_h = OVERNIGHT_PCT.get(str(nf.get("max_overnight_relevance", "unknown")).lower())
    explicit = pct(nf.get("calibrated_hazard_pct"))
    explicit_score = hazard_pct(nf.get("hazard_score"))

    event_hazards = []
    for e in nf.get("events", []) or []:
        if not isinstance(e, dict):
            continue
        h = []
        for key in ("fundamental_information", "attention_hazard", "uncertainty_hazard", "uncertainty_volatility_hazard"):
            v = finite(e.get(key))
            if v is not None:
                h.append(min(max(v, 0.0), 4.0) / 4.0 * 100.0)
        h.append(GAP_RISK_PCT.get(str(e.get("gap_risk", "unknown")).lower()))
        h.append(RELEVANCE_PCT.get(str(e.get("butterfly_relevance", "unknown")).lower()))
        h.append(OVERNIGHT_PCT.get(str(e.get("overnight_relevance", "unknown")).lower()))
        eh = max_available(h)
        if eh is not None:
            event_hazards.append(eh)

    hz = max_available([state_h, gap_h, rel_h, overnight_h, explicit, explicit_score] + event_hazards)
    reasons = []
    if status in {"UNAVAILABLE", "INVALID"}:
        hz = None
        reasons.append("news_filter_unavailable_or_invalid")
    elif status == "STALE_CALIBRATION":
        reasons.append("news_filter_calibration_stale")
    if agg == "TAIL_RISK_ACTIVE":
        reasons.append("news_filter_tail_risk_active")
    elif agg == "HIGH_UNCERTAINTY":
        reasons.append("news_filter_high_uncertainty")

    return {
        "status": status,
        "calibration_asof": nf.get("calibration_asof"),
        "aggregate_state": agg,
        "hazard_pct": hz,
        "max_gap_risk": str(nf.get("max_gap_risk", "unknown")).lower(),
        "max_butterfly_relevance": str(nf.get("max_butterfly_relevance", "unknown")).lower(),
        "max_overnight_relevance": str(nf.get("max_overnight_relevance", "unknown")).lower(),
        "dominant_channels": list(nf.get("dominant_channels", []) or []),
        "reasons": reasons,
    }


def classify(x):
    x = x or {}
    news_required = bool(x.get("news_filter_required", False))
    news_filter = normalize_news_filter(x.get("news_filter"))
    news_unusable = news_filter["status"] in {"UNAVAILABLE", "INVALID"}

    provided = str(x.get("state", "")).upper()
    if provided in STATES and provided != "UNKNOWN" and not x.get("recompute", False):
        if news_required and news_unusable:
            return {
                "engine": "v2.4-regime",
                "state": "UNKNOWN",
                "source": "provided_state_overridden_by_missing_news_filter",
                "confidence": "low",
                "path_stress": pct(x.get("path_stress")),
                "event_hazard": None,
                "implied_stress": pct(x.get("implied_stress")),
                "complacency_gap": None,
                "news_filter": news_filter,
                "parameters": PARAMS["UNKNOWN"],
                "reasons": ["required_news_filter_unavailable"],
            }
        confidence = str(x.get("confidence", "provided"))
        if news_filter["status"] == "STALE_CALIBRATION":
            confidence = "low"
        return {
            "engine": "v2.4-regime",
            "state": provided,
            "source": "provided_state",
            "confidence": confidence,
            "path_stress": pct(x.get("path_stress")),
            "event_hazard": max_available([pct(x.get("event_hazard")), news_filter.get("hazard_pct")]),
            "implied_stress": pct(x.get("implied_stress")),
            "complacency_gap": finite(x.get("complacency_gap")),
            "news_filter": news_filter,
            "parameters": PARAMS[provided],
            "reasons": list(x.get("reasons", [])) + news_filter.get("reasons", []),
        }

    realized = pct(x.get("realized_vol_percentile"))
    gap = pct(x.get("gap_tail_percentile", x.get("gap_p90_percentile")))
    tail_freq = pct(x.get("tail_gap_frequency_percentile"))
    intraday_range = pct(x.get("intraday_range_percentile"))

    implied = pct(x.get("implied_vol_percentile", x.get("vix_percentile")))
    skew = pct(x.get("skew_stress_percentile"))
    term = pct(x.get("term_structure_stress_percentile"))

    event = hazard_pct(x.get("event_hazard_score"))
    geopolitical = hazard_pct(x.get("geopolitical_hazard_score"))
    macro = hazard_pct(x.get("macro_policy_hazard_score"))
    oil = hazard_pct(x.get("oil_fx_rates_hazard_score"))
    legacy_news = hazard_pct(x.get("news_uncertainty_score"))
    calibrated_news = news_filter.get("hazard_pct")

    path_stress = weighted_mean([
        (realized, 0.35),
        (gap, 0.35),
        (tail_freq, 0.20),
        (intraday_range, 0.10),
    ])
    implied_stress = weighted_mean([
        (implied, 0.55),
        (skew, 0.25),
        (term, 0.20),
    ])
    event_hazard = max_available([event, geopolitical, macro, oil, legacy_news, calibrated_news])

    core_coverage = sum(v is not None for v in (realized, gap, tail_freq, implied, event_hazard))
    reasons = list(news_filter.get("reasons", []))

    if news_required and news_unusable:
        state = "UNKNOWN"
        reasons.append("required_news_filter_unavailable")
    elif core_coverage < 3 or implied_stress is None or event_hazard is None:
        state = "UNKNOWN"
        reasons.append("insufficient_regime_inputs")
    else:
        p = path_stress if path_stress is not None else 50.0
        i = implied_stress
        e = event_hazard
        g = gap if gap is not None else p
        tf = tail_freq if tail_freq is not None else p
        complacency_gap = max(e, p, g, tf) - i

        if p >= 75.0 or (i >= 75.0 and p >= 55.0) or (g >= 85.0 and tf >= 70.0):
            state = "ACTIVE_STRESS"
            reasons.append("realized_or_tail_stress_is_high")
        elif (e >= 65.0 and i <= 45.0) or (g >= 70.0 and i <= 45.0) or (tf >= 70.0 and i <= 45.0):
            state = "LATENT_JUMP_RISK"
            reasons.append("event_or_tail_hazard_exceeds_implied_stress")
        elif p <= 35.0 and e <= 25.0 and g <= 35.0 and tf <= 35.0 and i <= 55.0:
            state = "CALM_CARRY"
            reasons.append("realized_gap_and_event_risk_are_jointly_quiet")
        else:
            state = "TRANSITION"
            reasons.append("mixed_or_shifting_regime")

        if complacency_gap >= 30.0:
            reasons.append("large_complacency_gap")

    complacency_gap = None
    if implied_stress is not None:
        hazard_side = max_available([event_hazard, path_stress, gap, tail_freq])
        if hazard_side is not None:
            complacency_gap = hazard_side - implied_stress

    confidence = "high" if core_coverage >= 5 else "medium" if core_coverage >= 4 else "low"
    if news_filter["status"] == "STALE_CALIBRATION":
        confidence = "low" if confidence == "medium" else "medium" if confidence == "high" else confidence
    if state == "UNKNOWN":
        confidence = "low"

    return {
        "engine": "v2.4-regime",
        "state": state,
        "source": "computed",
        "confidence": confidence,
        "path_stress": path_stress,
        "event_hazard": event_hazard,
        "implied_stress": implied_stress,
        "complacency_gap": complacency_gap,
        "news_filter": news_filter,
        "components": {
            "realized_vol_percentile": realized,
            "gap_tail_percentile": gap,
            "tail_gap_frequency_percentile": tail_freq,
            "intraday_range_percentile": intraday_range,
            "implied_vol_percentile": implied,
            "skew_stress_percentile": skew,
            "term_structure_stress_percentile": term,
            "calibrated_news_hazard_percentile": calibrated_news,
        },
        "parameters": PARAMS[state],
        "reasons": list(dict.fromkeys(reasons)),
        "note": "Regime labels are deterministic risk states, not forecasts. Current raw-news interpretation comes from market-news-signal-filter. Price reactions may update market sensitivity but never the truth/evidence score of a news claim.",
    }


def main():
    ap = argparse.ArgumentParser(description="Classify butterfly market regime")
    ap.add_argument("--input", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    out = classify(load_json(args.input))
    print(json.dumps(out, indent=2 if args.pretty else None, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
