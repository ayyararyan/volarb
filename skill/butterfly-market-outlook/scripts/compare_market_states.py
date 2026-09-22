#!/usr/bin/env python3
"""Compare two Butterfly Engine v2 MarketState snapshots.

Outputs deterministic deltas and a review-urgency classification. This does not
choose HOLD/RECENTRE/SQUARE OFF; it tells the decision layer what materially changed.
"""
import argparse
import json
import math
from pathlib import Path


def get(d, path, default=None):
    cur = d
    for p in path.split('.'):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def num(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def health_rank(x):
    return {"HEALTHY": 0, "DEGRADED": 1, "STALE": 2, "INVALID": 3}.get(str(x).upper(), 1)


def event_rank(state):
    ranks = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    best = 0
    for e in state.get("event_clock", []) or []:
        if e.get("priced_by_surface") is False:
            best = max(best, ranks.get(str(e.get("severity", "low")).lower(), 0))
    return best


def compare(prev, cur):
    out = {"deltas": {}, "flags": []}
    score = 0
    straddle = num(get(cur, "surface.atm_straddle")) or num(get(prev, "surface.atm_straddle")) or 1.0

    def delta(name, path):
        a, b = num(get(prev, path)), num(get(cur, path))
        if a is None or b is None:
            out["deltas"][name] = None
            return None
        d = b - a
        out["deltas"][name] = d
        return d

    dspot = delta("spot_points", "price.spot")
    dfwd = delta("forward_points", "price.forward")
    div = delta("atm_iv", "surface.atm_iv")
    dstr = delta("atm_straddle_points", "surface.atm_straddle")
    dmed = delta("rnd_median_points", "surface.rnd_median")
    dskew = delta("local_skew_vp", "surface.local_skew_vp")

    for label, d in (("spot", dspot), ("forward", dfwd), ("rnd_median", dmed)):
        if d is None:
            continue
        z = abs(d) / max(straddle, 1e-9)
        out["deltas"][f"{label}_in_straddles"] = z
        if z >= 0.50:
            score += 2
            out["flags"].append(f"large_{label}_shift")
        elif z >= 0.25:
            score += 1
            out["flags"].append(f"meaningful_{label}_shift")

    old_str = num(get(prev, "surface.atm_straddle"))
    if old_str and dstr is not None:
        pct = dstr / old_str
        out["deltas"]["atm_straddle_pct"] = pct
        if pct >= 0.20:
            score += 2
            out["flags"].append("material_vol_expansion")
        elif pct >= 0.10:
            score += 1
            out["flags"].append("vol_expansion")
        elif pct <= -0.15:
            out["flags"].append("vol_compression")

    if div is not None:
        # IV may be stored decimal or vol points; normalize to vol points for the threshold.
        div_vp = div * 100.0 if abs(div) < 1.0 else div
        out["deltas"]["atm_iv_change_vp"] = div_vp
        if abs(div_vp) >= 3.0:
            score += 2
        elif abs(div_vp) >= 1.5:
            score += 1

    hp = health_rank(get(prev, "data_health.status"))
    hc = health_rank(get(cur, "data_health.status"))
    if hc > hp:
        score += 2
        out["flags"].append("data_health_deteriorated")
    if hc >= 2:
        score += 2
        out["flags"].append("surface_not_live_reliable")

    ep, ec = event_rank(prev), event_rank(cur)
    out["deltas"]["unpriced_event_severity_change"] = ec - ep
    if ec > ep:
        # Unpriced event severity should materially shorten review cadence.
        # low/medium/high/critical changes add 1/2/3/4 points respectively.
        score += 1 + ec
        out["flags"].append("event_risk_increased")

    rp, rc = get(prev, "path.regime"), get(cur, "path.regime")
    if rc != rp and rc in {"directional_up", "directional_down", "event_jump"}:
        score += 2
        out["flags"].append("regime_shift")

    if dskew is not None:
        dskew_vp = dskew * 100.0 if abs(dskew) < 1.0 else dskew
        out["deltas"]["local_skew_change_vp"] = dskew_vp
        if abs(dskew_vp) >= 2.0:
            score += 1
            out["flags"].append("skew_shift")

    if score >= 8:
        level, mins = "ACUTE", 15
    elif score >= 5:
        level, mins = "ELEVATED", 30
    elif score >= 2:
        level, mins = "MODERATE", 60
    else:
        level, mins = "LOW", 120
    out["change_score"] = score
    out["change_level"] = level
    out["suggested_review_interval_minutes"] = mins
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--previous", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    prev = json.loads(Path(args.previous).read_text())
    cur = json.loads(Path(args.current).read_text())
    print(json.dumps(compare(prev, cur), indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
