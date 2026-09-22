#!/usr/bin/env python3
"""Analyze an exchange option-chain snapshot as a volatility/distribution surface.

The input is the normalized JSON emitted by fetch_nse_option_chain.py or a
BSE-normalized snapshot with the same schema. Multiple --input files may be
supplied to add expiry term-structure context.

This script is intentionally backend-facing: it summarizes the full surface so
the skill can make a better butterfly decision without dumping the chain to the
user.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from optimize_butterflies import build_surface, risk_neutral_distribution, loss_stats, classify_data_health


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def pick_mid(side: Dict[str, Any]) -> Optional[float]:
    bid = side.get("bid")
    ask = side.get("ask")
    try:
        if bid is not None and ask is not None and float(bid) > 0 and float(ask) >= float(bid):
            return 0.5 * (float(bid) + float(ask))
    except (TypeError, ValueError):
        pass
    ltp = side.get("ltp")
    try:
        if ltp is not None and float(ltp) > 0:
            return float(ltp)
    except (TypeError, ValueError):
        pass
    return None


def solve_3x3(a: List[List[float]], b: List[float]) -> Optional[List[float]]:
    m = [row[:] + [rhs] for row, rhs in zip(a, b)]
    n = 3
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-14:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        div = m[col][col]
        m[col] = [x / div for x in m[col]]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col]
            m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][-1] for i in range(n)]


def quadratic_fit(points: Sequence[Tuple[float, float, float]]) -> Optional[Tuple[float, float, float]]:
    """Weighted least-squares fit y = a + b*x + c*x^2."""
    if len(points) < 3:
        return None
    s0 = sx = sx2 = sx3 = sx4 = 0.0
    sy = sxy = sx2y = 0.0
    for x, y, w in points:
        w = max(float(w), 1e-6)
        x2 = x * x
        s0 += w
        sx += w * x
        sx2 += w * x2
        sx3 += w * x2 * x
        sx4 += w * x2 * x2
        sy += w * y
        sxy += w * x * y
        sx2y += w * x2 * y
    mat = [[s0, sx, sx2], [sx, sx2, sx3], [sx2, sx3, sx4]]
    rhs = [sy, sxy, sx2y]
    sol = solve_3x3(mat, rhs)
    return tuple(sol) if sol else None


def side_liquidity_weight(row: Dict[str, Any], forward: float) -> float:
    side = row.get("put", {}) if float(row["strike"]) < forward else row.get("call", {})
    oi = float(side.get("oi") or 0.0)
    volume = float(side.get("volume") or 0.0)
    bid = side.get("bid")
    ask = side.get("ask")
    spread_penalty = 1.0
    try:
        bidf, askf = float(bid), float(ask)
        if bidf > 0 and askf >= bidf:
            mid = 0.5 * (bidf + askf)
            if mid > 0:
                spread_penalty = 1.0 / (1.0 + 10.0 * (askf - bidf) / mid)
    except (TypeError, ValueError):
        pass
    return max(1.0, math.log1p(oi) + math.log1p(volume)) * spread_penalty


def iv_at_x(fit: Optional[Tuple[float, float, float]], x: float) -> Optional[float]:
    if fit is None:
        return None
    a, b, c = fit
    v = a + b * x + c * x * x
    return v if v > 0 else None


def nearest_quantile(dist: Sequence[Tuple[float, float]], q: float) -> Optional[float]:
    c = 0.0
    for s, p in sorted(dist):
        c += p
        if c >= q:
            return s
    return dist[-1][0] if dist else None


def prob_le(dist: Sequence[Tuple[float, float]], level: float) -> float:
    return sum(p for s, p in dist if s <= level)


def prob_ge(dist: Sequence[Tuple[float, float]], level: float) -> float:
    return sum(p for s, p in dist if s >= level)


def delta25_metrics(surface: Sequence[Dict[str, Any]], meta: Dict[str, float]) -> Dict[str, Optional[float]]:
    t = float(meta["t"])
    f = float(meta["forward"])
    if t <= 0:
        return {"put25_strike": None, "call25_strike": None, "rr25_vp": None, "bf25_vp": None}
    puts = []
    calls = []
    for row in surface:
        iv = row.get("iv")
        k = float(row["strike"])
        if iv is None or float(iv) <= 0:
            continue
        iv = float(iv)
        d1 = (math.log(f / k) + 0.5 * iv * iv * t) / (iv * math.sqrt(t))
        call_delta = norm_cdf(d1)
        put_abs_delta = 1.0 - call_delta
        if k < f:
            puts.append((abs(put_abs_delta - 0.25), k, iv))
        elif k > f:
            calls.append((abs(call_delta - 0.25), k, iv))
    if not puts or not calls:
        return {"put25_strike": None, "call25_strike": None, "rr25_vp": None, "bf25_vp": None}
    _, kp, ivp = min(puts)
    _, kc, ivc = min(calls)
    return {
        "put25_strike": kp,
        "call25_strike": kc,
        "put25_iv": ivp,
        "call25_iv": ivc,
        "rr25_vp": (ivc - ivp) * 100.0,
    }


def analyze_one(data: Dict[str, Any], lower: Optional[float], center: Optional[float], upper: Optional[float], debit: Optional[float]) -> Dict[str, Any]:
    surface, meta = build_surface(data)
    dist, dist_diag = risk_neutral_distribution(surface, meta)
    data_health = classify_data_health(meta, dist_diag)
    spot = float(meta["spot"])
    fwd = float(meta["forward"])

    usable = []
    for r in surface:
        iv = r.get("iv")
        if iv is None or float(iv) <= 0:
            continue
        x = math.log(float(r["strike"]) / fwd)
        if abs(x) > 0.08:
            continue
        usable.append((x, float(iv), side_liquidity_weight(r, fwd)))
    fit = quadratic_fit(usable)

    atm = min(surface, key=lambda r: abs(float(r["strike"]) - fwd))
    atm_iv = atm.get("iv")
    atm_k = float(atm["strike"])
    if atm_iv is None and fit is not None:
        atm_iv = iv_at_x(fit, 0.0)

    d25 = delta25_metrics(surface, meta)
    if d25.get("put25_iv") is not None and d25.get("call25_iv") is not None and atm_iv is not None:
        d25["bf25_vp"] = (0.5 * (d25["put25_iv"] + d25["call25_iv"]) - float(atm_iv)) * 100.0
    else:
        d25["bf25_vp"] = None

    call_mid = pick_mid(atm.get("call", {}) or {})
    put_mid = pick_mid(atm.get("put", {}) or {})
    straddle = (call_mid + put_mid) if call_mid is not None and put_mid is not None else None

    iv_dn2 = iv_at_x(fit, -0.02)
    iv_up2 = iv_at_x(fit, 0.02)
    iv_0 = iv_at_x(fit, 0.0)
    skew_2 = None if iv_dn2 is None or iv_up2 is None else (iv_dn2 - iv_up2) * 100.0
    curvature_2 = None if iv_dn2 is None or iv_up2 is None or iv_0 is None else (0.5 * (iv_dn2 + iv_up2) - iv_0) * 100.0

    q10 = nearest_quantile(dist, 0.10)
    q50 = nearest_quantile(dist, 0.50)
    q90 = nearest_quantile(dist, 0.90)
    mode_s, mode_p = max(dist, key=lambda z: z[1])

    result: Dict[str, Any] = {
        "provider": data.get("provider"),
        "symbol": data.get("symbol", data.get("underlying")),
        "expiry": data.get("expiry"),
        "asof": data.get("nse_timestamp", data.get("retrieved_at_utc", data.get("asof"))),
        "spot": spot,
        "forward": fwd,
        "forward_source": meta.get("forward_source"),
        "parity_dispersion_points": meta.get("parity_dispersion_points"),
        "data_health": data_health,
        "dte_calendar": meta["dte"],
        "surface_points": len(usable),
        "atm_strike": atm_k,
        "atm_iv": atm_iv,
        "atm_straddle": straddle,
        "smile": {
            "quadratic_a": fit[0] if fit else None,
            "skew_slope": fit[1] if fit else None,
            "curvature_coeff": fit[2] if fit else None,
            "downside_minus_upside_iv_2pct_vp": skew_2,
            "symmetric_wing_richness_2pct_vp": curvature_2,
            **d25,
        },
        "risk_neutral_distribution": {
            "q10": q10,
            "median": q50,
            "q90": q90,
            "mode_bucket": mode_s,
            "mode_bucket_probability": mode_p,
            "p_down_1pct": prob_le(dist, spot * 0.99),
            "p_up_1pct": prob_ge(dist, spot * 1.01),
            "p_down_1_5pct": prob_le(dist, spot * 0.985),
            "p_up_1_5pct": prob_ge(dist, spot * 1.015),
        },
    }

    if lower is not None and center is not None and upper is not None:
        fly = {
            "lower": lower,
            "center": center,
            "upper": upper,
            "center_minus_rnd_median": center - q50 if q50 is not None else None,
            "p_below_lower": prob_le(dist, lower),
            "p_above_upper": prob_ge(dist, upper),
            "p_outside_wings": prob_le(dist, lower) + prob_ge(dist, upper),
            "p_inside_wings": max(0.0, 1.0 - prob_le(dist, lower) - prob_ge(dist, upper)),
        }
        if debit is not None:
            stats = loss_stats(dist, lower, center, upper, debit)
            fly.update({
                "debit": debit,
                "p_loss": stats.get("prob_loss"),
                "expected_loss_points": stats.get("expected_loss_points"),
                "p_outside_wings_loss_stats": stats.get("prob_outside_wings"),
                "cvar95_points": stats.get("cvar95_loss_points"),
            })
        result["butterfly_mapping"] = fly

    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze full exchange option surface for butterfly decisions")
    ap.add_argument("--input", action="append", required=True, help="Normalized chain JSON; repeat for multiple expiries")
    ap.add_argument("--lower", type=float)
    ap.add_argument("--center", type=float)
    ap.add_argument("--upper", type=float)
    ap.add_argument("--debit", type=float)
    ap.add_argument("--output")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    if any(x is not None for x in (args.lower, args.center, args.upper)) and not all(x is not None for x in (args.lower, args.center, args.upper)):
        raise SystemExit("--lower, --center and --upper must be supplied together")

    analyses = []
    for path in args.input:
        data = json.loads(Path(path).read_text())
        analyses.append(analyze_one(data, args.lower, args.center, args.upper, args.debit))

    analyses.sort(key=lambda x: float(x.get("dte_calendar") or 0.0))
    term = []
    for a in analyses:
        term.append({"expiry": a.get("expiry"), "dte_calendar": a.get("dte_calendar"), "atm_iv": a.get("atm_iv")})
    front_next = None
    if len(term) >= 2 and term[0].get("atm_iv") is not None and term[1].get("atm_iv") is not None:
        front_next = (float(term[0]["atm_iv"]) - float(term[1]["atm_iv"])) * 100.0

    out = {
        "surface_analysis": analyses,
        "term_structure": {
            "expiries": term,
            "front_minus_next_atm_iv_vp": front_next,
        },
    }
    text = json.dumps(out, indent=2 if args.pretty else None, sort_keys=False)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
