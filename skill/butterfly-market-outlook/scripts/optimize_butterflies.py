#!/usr/bin/env python3
"""Butterfly Engine v2.1 candidate wide-iron-fly optimizer.

Dependency-free deterministic backend for:
- quote/data sanity checks and parity-implied forward estimation;
- parity-consistent option-price surface construction;
- arbitrage-repaired risk-neutral terminal distribution;
- actual four-leg iron-butterfly execution economics;
- theta/carry, liquidity, RND tail risk and optional real-world path scenarios;
- Pareto screening across theta efficiency, carry burden and combined tail risk;
- mandatory next-open stress and broker/event-latency gates for expiry-eve overnight carry.

The risk-neutral distribution is a pricing-measure object. Optional path scenarios are
kept separate and may contain judgmental/real-world probabilities supplied by the
orchestrating agent.
"""

import argparse
import datetime as dt
import json
import math
from pathlib import Path

SQRT2 = math.sqrt(2.0)
EPS = 1e-12


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def bsm_forward_price(kind, forward, strike, vol, t, df=1.0):
    """Black price using forward F and discount factor df."""
    if t <= 0 or vol <= 0:
        intrinsic = max(forward - strike, 0.0) if kind == "call" else max(strike - forward, 0.0)
        return df * intrinsic
    sig = vol * math.sqrt(t)
    if sig <= 0:
        return 0.0
    d1 = (math.log(max(forward, EPS) / max(strike, EPS)) + 0.5 * vol * vol * t) / sig
    d2 = d1 - sig
    if kind == "call":
        return df * (forward * norm_cdf(d1) - strike * norm_cdf(d2))
    return df * (strike * norm_cdf(-d2) - forward * norm_cdf(-d1))


def implied_vol(kind, price, forward, strike, t, df=1.0):
    if price is None or price <= 0 or t <= 0 or forward <= 0 or strike <= 0:
        return None
    intrinsic = df * (max(forward - strike, 0.0) if kind == "call" else max(strike - forward, 0.0))
    if price < intrinsic - 1e-8:
        return None
    lo, hi = 1e-4, 5.0
    for _ in range(90):
        mid = 0.5 * (lo + hi)
        p = bsm_forward_price(kind, forward, strike, mid, t, df)
        if p > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def as_float(x):
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def normalize_iv(x):
    x = as_float(x)
    if x is None or x <= 0:
        return None
    return x / 100.0 if x > 2.0 else x


def pick_mark(side):
    if not side:
        return None, None
    bid = as_float(side.get("bid"))
    ask = as_float(side.get("ask"))
    ltp = as_float(side.get("ltp", side.get("mark")))
    if bid is not None and ask is not None and bid > 0 and ask >= bid:
        return 0.5 * (bid + ask), "mid"
    if ltp is not None and ltp > 0:
        return ltp, "ltp"
    return None, None


def half_spread(side):
    if not side:
        return None
    bid = as_float(side.get("bid"))
    ask = as_float(side.get("ask"))
    if bid is None or ask is None or bid <= 0 or ask < bid:
        return None
    return 0.5 * (ask - bid)


def parse_date(value):
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    text = str(value).strip()
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%d-%b-%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unsupported date format: {value!r}")


def days_between(asof, expiry):
    a = parse_date(asof)
    e = parse_date(expiry)
    return max((e - a).days, 0)


def median(values):
    vals = sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
    if not vals:
        return None
    n = len(vals)
    if n % 2:
        return vals[n // 2]
    return 0.5 * (vals[n // 2 - 1] + vals[n // 2])


def weighted_isotonic_decreasing(values, weights=None):
    """Pool-adjacent-violators for a non-increasing sequence."""
    if not values:
        return []
    if weights is None:
        weights = [1.0] * len(values)
    blocks = []
    for i, (v, w) in enumerate(zip(values, weights)):
        blocks.append([i, i, -float(v), max(float(w), EPS)])
        while len(blocks) >= 2 and blocks[-2][2] > blocks[-1][2]:
            b2 = blocks.pop()
            b1 = blocks.pop()
            wt = b1[3] + b2[3]
            mean = (b1[2] * b1[3] + b2[2] * b2[3]) / wt
            blocks.append([b1[0], b2[1], mean, wt])
    out = [0.0] * len(values)
    for start, end, mean, _ in blocks:
        for i in range(start, end + 1):
            out[i] = -mean
    return out


def side_spread_pct(side):
    mark, _ = pick_mark(side)
    hs = half_spread(side)
    if mark is None or hs is None or mark <= 0:
        return None
    return 2.0 * hs / mark


def side_quality(side):
    """Loose 0..1 quote-quality weight used only for robust forward extraction."""
    mark, source = pick_mark(side)
    if mark is None:
        return 0.0
    q = 1.0 if source == "mid" else 0.35
    sp = side_spread_pct(side)
    if sp is not None:
        q *= 1.0 / (1.0 + 8.0 * sp)
    oi = max(as_float(side.get("oi")) or 0.0, 0.0)
    vol = max(as_float(side.get("volume")) or 0.0, 0.0)
    q *= min(1.0, 0.35 + 0.08 * math.log1p(oi) + 0.06 * math.log1p(vol))
    return max(q, 0.0)


def estimate_parity_forward(rows, spot, df):
    estimates = []
    for row in rows:
        k = as_float(row.get("strike"))
        if k is None or k <= 0 or abs(k / spot - 1.0) > 0.06:
            continue
        c = row.get("call", {}) or {}
        p = row.get("put", {}) or {}
        cm, _ = pick_mark(c)
        pm, _ = pick_mark(p)
        if cm is None or pm is None:
            continue
        f = k + (cm - pm) / max(df, EPS)
        if not (0.90 * spot <= f <= 1.10 * spot):
            continue
        q = min(side_quality(c), side_quality(p))
        if q <= 0:
            continue
        estimates.append((f, q, k))

    if not estimates:
        return None, {"parity_points": 0, "parity_dispersion_points": None, "parity_estimates": []}

    # Keep the most reliable half (at least 3) before taking a robust median.
    estimates.sort(key=lambda z: z[1], reverse=True)
    keep_n = min(len(estimates), max(3, int(math.ceil(len(estimates) * 0.6))))
    kept = estimates[:keep_n]
    fwd = median([x[0] for x in kept])
    abs_dev = [abs(x[0] - fwd) for x in kept]
    mad = median(abs_dev) or 0.0
    diag = {
        "parity_points": len(kept),
        "parity_dispersion_points": mad,
        "parity_estimates": [{"strike": k, "forward": f, "quality": q} for f, q, k in kept[:20]],
    }
    return fwd, diag


def build_surface(data):
    spot_raw = data.get("spot", data.get("underlying_value"))
    if spot_raw is None:
        raise ValueError("Input needs spot or underlying_value")
    spot = float(spot_raw)
    r = float(data.get("risk_free_rate", 0.06))
    asof = data.get("asof", data.get("retrieved_at_utc"))
    if asof is None and "days_to_expiry" not in data:
        raise ValueError("Input needs asof/retrieved_at_utc or days_to_expiry")
    if data.get("days_to_expiry") is not None:
        dte = float(data["days_to_expiry"])
    else:
        dte = float(days_between(asof, data["expiry"]))
    t = max(dte, 0.0) / 365.0
    df = math.exp(-r * t)
    rows = sorted(data["chain"], key=lambda x: float(x["strike"]))

    parity_fwd, pdiag = estimate_parity_forward(rows, spot, df)
    input_fwd = as_float(data.get("forward"))
    parity_good = (
        parity_fwd is not None
        and pdiag["parity_points"] >= 3
        and (pdiag["parity_dispersion_points"] or 0.0) <= max(0.004 * spot, 25.0)
    )
    if parity_good:
        forward = parity_fwd
        forward_source = "parity"
    elif input_fwd is not None and input_fwd > 0:
        forward = input_fwd
        forward_source = "input"
    else:
        forward = spot
        forward_source = "spot_fallback"

    surface = []
    invalid_quotes = 0
    two_sided = 0
    for row in rows:
        k = float(row["strike"])
        c = row.get("call", {}) or {}
        p = row.get("put", {}) or {}
        for s in (c, p):
            bid, ask = as_float(s.get("bid")), as_float(s.get("ask"))
            if bid is not None and ask is not None:
                if bid > 0 and ask >= bid:
                    two_sided += 1
                elif ask < bid:
                    invalid_quotes += 1

        cm, csrc = pick_mark(c)
        pm, psrc = pick_mark(p)
        if k < forward and pm is not None:
            call_mark = pm + df * (forward - k)
            mark_source = f"put-{psrc}-parity"
        elif k >= forward and cm is not None:
            call_mark = cm
            mark_source = f"call-{csrc}"
        elif cm is not None:
            call_mark = cm
            mark_source = f"call-{csrc}"
        elif pm is not None:
            call_mark = pm + df * (forward - k)
            mark_source = f"put-{psrc}-parity"
        else:
            call_mark = None
            mark_source = None

        call_iv = normalize_iv(c.get("iv"))
        put_iv = normalize_iv(p.get("iv"))
        if k < forward and put_iv is not None:
            iv = put_iv
        elif k >= forward and call_iv is not None:
            iv = call_iv
        else:
            iv = implied_vol("call", call_mark, forward, k, t, df) if call_mark is not None else None
        if call_mark is None and iv is not None:
            call_mark = bsm_forward_price("call", forward, k, iv, t, df)
            mark_source = "model-from-iv"

        surface.append({
            "strike": k,
            "call_mark": call_mark,
            "iv": iv,
            "source": mark_source,
            "call": c,
            "put": p,
        })

    usable_local = [r0 for r0 in surface if r0.get("call_mark") is not None and abs(r0["strike"] / forward - 1.0) <= 0.08]
    health_issues = []
    if len(usable_local) < 12:
        health_issues.append("sparse_local_surface")
    if invalid_quotes > 0:
        health_issues.append("crossed_quotes_present")
    if forward_source == "spot_fallback":
        health_issues.append("no_reliable_parity_forward")
    if pdiag["parity_dispersion_points"] is not None and pdiag["parity_dispersion_points"] > max(0.004 * spot, 25.0):
        health_issues.append("high_parity_dispersion")

    meta = {
        "spot": spot,
        "forward": forward,
        "forward_input": input_fwd,
        "forward_parity": parity_fwd,
        "forward_source": forward_source,
        "parity_points": pdiag["parity_points"],
        "parity_dispersion_points": pdiag["parity_dispersion_points"],
        "r": r,
        "t": t,
        "df": df,
        "dte": dte,
        "two_sided_quote_count": two_sided,
        "invalid_quote_count": invalid_quotes,
        "health_issues": health_issues,
    }
    return surface, meta


def interpolate_surface(surface, strike, key):
    rows = [r for r in surface if r.get(key) is not None]
    if not rows:
        return None
    rows.sort(key=lambda r: r["strike"])
    if strike <= rows[0]["strike"]:
        return rows[0][key]
    if strike >= rows[-1]["strike"]:
        return rows[-1][key]
    for a, b in zip(rows[:-1], rows[1:]):
        if a["strike"] <= strike <= b["strike"]:
            if strike == a["strike"]:
                return a[key]
            if strike == b["strike"]:
                return b[key]
            w = (strike - a["strike"]) / (b["strike"] - a["strike"])
            return a[key] * (1 - w) + b[key] * w
    return None


def row_by_strike(surface):
    return {r["strike"]: r for r in surface}


def risk_neutral_distribution(surface, meta):
    # Focus on a broad but not absurd range around forward; deep stale ITM quotes are often unusable.
    fwd = meta["forward"]
    rows = [r for r in surface if r.get("call_mark") is not None and 0.85 * fwd <= r["strike"] <= 1.15 * fwd]
    rows.sort(key=lambda r: r["strike"])
    if len(rows) < 6:
        raise ValueError("Need at least six usable strikes to estimate distribution")

    strikes = [r["strike"] for r in rows]
    calls = [r["call_mark"] for r in rows]
    df = meta["df"]

    monotonic_violations = sum(1 for a, b in zip(calls[:-1], calls[1:]) if b > a + 1e-8)
    raw_slopes = []
    mids = []
    raw_surv = []
    for i in range(len(strikes) - 1):
        dk = strikes[i + 1] - strikes[i]
        if dk <= 0:
            continue
        slope = (calls[i + 1] - calls[i]) / dk
        raw_slopes.append(slope)
        mids.append(0.5 * (strikes[i] + strikes[i + 1]))
        raw_surv.append(min(1.0, max(0.0, -slope / max(df, EPS))))

    convexity_violations = sum(1 for a, b in zip(raw_slopes[:-1], raw_slopes[1:]) if b < a - 1e-8)
    surv = weighted_isotonic_decreasing(raw_surv)
    surv = [min(1.0, max(0.0, x)) for x in surv]
    changed = sum(1 for a, b in zip(raw_surv, surv) if abs(a - b) > 0.02)
    repair_fraction = changed / max(len(surv), 1)

    masses = []
    step_lo = strikes[1] - strikes[0]
    step_hi = strikes[-1] - strikes[-2]
    masses.append((max(0.0, mids[0] - 0.5 * step_lo), max(0.0, 1.0 - surv[0])))
    for i in range(len(mids) - 1):
        p = max(0.0, surv[i] - surv[i + 1])
        srep = 0.5 * (mids[i] + mids[i + 1])
        masses.append((srep, p))
    masses.append((mids[-1] + 0.5 * step_hi, max(0.0, surv[-1])))

    total = sum(p for _, p in masses)
    if total <= 0:
        raise ValueError("Could not construct non-zero distribution")
    masses = [(s, p / total) for s, p in masses]
    diag = {
        "mid_strikes": mids,
        "raw_survival": raw_surv,
        "survival": surv,
        "monotonicity_violations": monotonic_violations,
        "convexity_violations": convexity_violations,
        "repair_fraction": repair_fraction,
        "used_strike_count": len(rows),
    }
    return masses, diag


def nearest_quantile(dist, q):
    c = 0.0
    for s, p in sorted(dist):
        c += p
        if c >= q:
            return s
    return dist[-1][0] if dist else None


def fly_payoff_points(s, k1, k2, k3, debit):
    intrinsic = max(s - k1, 0.0) - 2.0 * max(s - k2, 0.0) + max(s - k3, 0.0)
    return intrinsic - debit


def loss_stats(dist, k1, k2, k3, debit):
    outcomes = []
    p_loss = p_wing = exp_loss = p50 = p80 = 0.0
    for s, p in dist:
        pnl = fly_payoff_points(s, k1, k2, k3, debit)
        loss = max(-pnl, 0.0)
        outcomes.append((loss, p, s, pnl))
        if pnl < 0:
            p_loss += p
            exp_loss += p * loss
        if s <= k1 or s >= k3:
            p_wing += p
        if debit > 0 and loss >= 0.5 * debit:
            p50 += p
        if debit > 0 and loss >= 0.8 * debit:
            p80 += p

    outcomes.sort(reverse=True, key=lambda x: x[0])
    tail_needed = 0.05
    used = 0.0
    tail_loss = 0.0
    var95 = 0.0
    for loss, p, _, _ in outcomes:
        if used >= tail_needed - 1e-12:
            break
        take = min(p, tail_needed - used)
        if take > 0:
            tail_loss += loss * take
            used += take
            var95 = loss
    cvar95 = tail_loss / used if used > 0 else 0.0
    return {
        "prob_loss": p_loss,
        "prob_outside_wings": p_wing,
        "expected_loss_points": exp_loss,
        "var95_loss_points": var95,
        "cvar95_loss_points": cvar95,
        "prob_loss_ge_50pct_max": p50,
        "prob_loss_ge_80pct_max": p80,
    }


def leg_liquidity(row, side_name):
    side = row.get(side_name, {}) or {}
    mark, src = pick_mark(side)
    hs = half_spread(side)
    oi = as_float(side.get("oi"))
    vol = as_float(side.get("volume"))
    spread_pct = None
    if mark and hs is not None and mark > 0:
        spread_pct = 2.0 * hs / mark
    return {
        "mark": mark,
        "source": src,
        "oi": oi,
        "volume": vol,
        "half_spread": hs,
        "spread_pct": spread_pct,
    }


def side_greek(side, name):
    g = side.get("greeks", {}) if side else {}
    if isinstance(g, dict) and name in g:
        return as_float(g.get(name))
    return as_float(side.get(name)) if side else None


def side_iv_or_solve(side, kind, mark, meta, strike):
    iv = normalize_iv((side or {}).get("iv"))
    if iv is not None:
        return iv
    return implied_vol(kind, mark, meta["forward"], strike, meta["t"], meta["df"]) if mark is not None else None


def future_option_value(kind, strike, side, current_mark, meta, future_spot, days_ahead, iv_shift_vp=0.0):
    t1 = max(meta["t"] - max(days_ahead, 0.0) / 365.0, 0.0)
    if t1 <= 0:
        return max(future_spot - strike, 0.0) if kind == "call" else max(strike - future_spot, 0.0)
    iv = side_iv_or_solve(side, kind, current_mark, meta, strike)
    if iv is None:
        return None
    iv = max(iv + iv_shift_vp / 100.0, 1e-4)
    carry_rate = math.log(max(meta["forward"], EPS) / max(meta["spot"], EPS)) / max(meta["t"], EPS)
    f1 = future_spot * math.exp(carry_rate * t1)
    df1 = math.exp(-meta["r"] * t1)
    return bsm_forward_price(kind, f1, strike, iv, t1, df1)


def iron_close_cost(rows, meta, future_spot, days_ahead, iv_shift_vp=0.0):
    r1, r2, r3 = rows
    p1, _ = pick_mark(r1.get("put", {}))
    c2, _ = pick_mark(r2.get("call", {}))
    p2, _ = pick_mark(r2.get("put", {}))
    c3, _ = pick_mark(r3.get("call", {}))
    if any(x is None for x in (p1, c2, p2, c3)):
        return None
    fv_p1 = future_option_value("put", r1["strike"], r1.get("put", {}), p1, meta, future_spot, days_ahead, iv_shift_vp)
    fv_c2 = future_option_value("call", r2["strike"], r2.get("call", {}), c2, meta, future_spot, days_ahead, iv_shift_vp)
    fv_p2 = future_option_value("put", r2["strike"], r2.get("put", {}), p2, meta, future_spot, days_ahead, iv_shift_vp)
    fv_c3 = future_option_value("call", r3["strike"], r3.get("call", {}), c3, meta, future_spot, days_ahead, iv_shift_vp)
    if any(x is None for x in (fv_p1, fv_c2, fv_p2, fv_c3)):
        return None
    return fv_c2 + fv_p2 - fv_p1 - fv_c3


def scenario_metrics(data, rows, meta, entry_credit, debit, carry_days):
    scenarios = data.get("path_scenarios", data.get("scenario_overlay")) or []
    out = []
    probs_complete = bool(scenarios)
    prob_sum = 0.0
    exp_pnl = 0.0
    exp_loss = 0.0
    worst = None
    for s in scenarios:
        prob = as_float(s.get("probability"))
        if prob is None:
            probs_complete = False
        else:
            prob_sum += max(prob, 0.0)
        spot = as_float(s.get("spot"))
        if spot is None:
            ret = as_float(s.get("spot_return_pct"))
            if ret is not None:
                spot = meta["spot"] * (1.0 + ret / 100.0)
        if spot is None:
            continue
        iv_shift = as_float(s.get("iv_shift_vp")) or 0.0
        days_ahead = as_float(s.get("days_ahead"))
        if days_ahead is None:
            days_ahead = carry_days
        cc = iron_close_cost(rows, meta, spot, days_ahead, iv_shift)
        if cc is None:
            continue
        pnl = entry_credit - cc
        worst = pnl if worst is None else min(worst, pnl)
        out.append({
            "label": s.get("label"),
            "spot": spot,
            "probability": prob,
            "iv_shift_vp": iv_shift,
            "days_ahead": days_ahead,
            "pnl_points": pnl,
        })

    if probs_complete and out and prob_sum > 0 and len(out) == len(scenarios):
        for z in out:
            w = max(z["probability"], 0.0) / prob_sum
            exp_pnl += w * z["pnl_points"]
            exp_loss += w * max(-z["pnl_points"], 0.0)
    else:
        exp_pnl = None
        exp_loss = None

    path_tail_loss_ratio = max(0.0, -(worst or 0.0)) / max(debit, EPS) if worst is not None else 0.0
    path_expected_loss_ratio = (exp_loss / max(debit, EPS)) if exp_loss is not None else 0.0
    return {
        "scenarios": out,
        "scenario_expected_pnl_points": exp_pnl,
        "scenario_expected_loss_points": exp_loss,
        "worst_scenario_pnl_points": worst,
        "path_tail_loss_ratio": path_tail_loss_ratio,
        "path_expected_loss_ratio": path_expected_loss_ratio,
    }



def _latency_severity(cfg):
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    best = "low"
    for e in cfg.get("events", []) or []:
        if not e.get("inside_untradeable_window", e.get("latency_critical", False)):
            continue
        sev = str(e.get("severity", "low")).lower()
        if order.get(sev, 0) > order.get(best, 0):
            best = sev
    fallback = str(cfg.get("event_latency_severity", "low")).lower()
    if order.get(fallback, 0) > order.get(best, 0):
        best = fallback
    return best



def _gap_quantile(values, q):
    vals = sorted(float(v) for v in values)
    if not vals:
        return None
    h = (len(vals) - 1) * float(q)
    lo = int(math.floor(h))
    hi = int(math.ceil(h))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (h - lo)


def _empirical_gap_metrics(cfg, meta, center, entry_credit, same_pnl, net_gamma):
    ecfg = cfg.get("empirical_gap_gate") or {}
    mode = str(cfg.get("mode", "candidate_entry"))
    entry_modes = {"candidate_entry", "recenter_entry", "rotation_entry"}
    required = bool(ecfg.get("required", mode in entry_modes))
    raw = ecfg.get("gap_pct", ecfg.get("recent_gap_pct", [])) or []
    vals = []
    for v in raw:
        try:
            z = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(z):
            vals.append(z)
    min_obs = max(int(ecfg.get("min_observations", 15)), 1)
    out = {
        "required": required,
        "source": ecfg.get("source"),
        "sample_size": len(vals),
        "min_observations": min_obs,
        "sufficient_history": len(vals) >= min_obs,
        "median_abs_gap_pct": None,
        "p80_abs_gap_pct": None,
        "p90_abs_gap_pct": None,
        "large_gap_threshold_pct": float(ecfg.get("large_gap_threshold_pct", 0.50)),
        "large_gap_rate": None,
        "p90_gap_points": None,
        "expected_local_gamma_drag_points": None,
        "gap_gamma_burden": None,
        "nearest_break_even_buffer_points": None,
        "q90_break_even_buffer_ratio": None,
        "spot_outside_break_even": False,
    }
    if not out["sufficient_history"]:
        return out

    av = [abs(v) for v in vals]
    out["median_abs_gap_pct"] = _gap_quantile(av, 0.50)
    out["p80_abs_gap_pct"] = _gap_quantile(av, 0.80)
    out["p90_abs_gap_pct"] = _gap_quantile(av, 0.90)
    thr = out["large_gap_threshold_pct"]
    out["large_gap_rate"] = sum(1 for v in av if v >= thr) / len(av)

    spot = float(meta["spot"])
    out["p90_gap_points"] = spot * out["p90_abs_gap_pct"] / 100.0
    if net_gamma is not None and same_pnl is not None and same_pnl > EPS:
        mean_sq_gap = sum((spot * v / 100.0) ** 2 for v in vals) / len(vals)
        drag = 0.5 * abs(float(net_gamma)) * mean_sq_gap
        out["expected_local_gamma_drag_points"] = drag
        out["gap_gamma_burden"] = drag / same_pnl

    lower_be = float(center) - float(entry_credit)
    upper_be = float(center) + float(entry_credit)
    buffer_points = min(spot - lower_be, upper_be - spot)
    out["nearest_break_even_buffer_points"] = buffer_points
    if buffer_points <= 0:
        out["spot_outside_break_even"] = True
    else:
        out["q90_break_even_buffer_ratio"] = out["p90_gap_points"] / buffer_points
    return out


def _apply_empirical_gap_gate(emp, hard, warnings):
    if emp.get("required") and not emp.get("sufficient_history"):
        hard.append("insufficient_recent_gap_history")
        return
    if not emp.get("sufficient_history"):
        return
    if emp.get("spot_outside_break_even"):
        hard.append("spot_outside_break_even_before_overnight")
    ratio = emp.get("q90_break_even_buffer_ratio")
    if ratio is not None:
        if ratio >= 1.0:
            hard.append("recent_q90_gap_exceeds_break_even_buffer")
        elif ratio >= 0.80:
            warnings.append("recent_q90_gap_near_break_even_buffer")
    burden = emp.get("gap_gamma_burden")
    if burden is not None:
        if burden >= 1.0:
            hard.append("empirical_gap_gamma_exceeds_same_state_harvest")
        elif burden >= 0.60:
            warnings.append("recent_gap_gamma_consumes_most_same_state_harvest")
    if (emp.get("large_gap_rate") or 0.0) >= 0.15:
        warnings.append("recent_large_gap_frequency_elevated")

def overnight_stress_metrics(surface, data, rows, meta, entry_credit, debit, carry_days, net_gamma=None):
    cfg = data.get("overnight_carry") or {}
    active = bool(cfg.get("active", cfg.get("enabled", False)))
    if not active:
        return {"active": False, "status": "NOT_APPLICABLE", "hard_failures": []}

    expiry_sessions = float(cfg.get("expiry_sessions_remaining", 999.0))
    mode = str(cfg.get("mode", "candidate_entry"))
    broker_status = str(cfg.get("broker_feasibility_status", "UNKNOWN")).upper()
    auto_warn = bool(cfg.get("broker_auto_squareoff_warning", False))
    if auto_warn and broker_status == "PASS":
        broker_status = "WARN"
    latency = _latency_severity(cfg)

    strikes = sorted(r["strike"] for r in surface if r.get("call_mark") is not None)
    byk = row_by_strike(surface)
    atm = min(strikes, key=lambda k: abs(k - meta["forward"]))
    atmr = byk[atm]
    c_atm, _ = pick_mark(atmr.get("call", {}))
    p_atm, _ = pick_mark(atmr.get("put", {}))
    atm_straddle = as_float(cfg.get("atm_straddle"))
    if atm_straddle is None and c_atm is not None and p_atm is not None:
        atm_straddle = c_atm + p_atm
    atm_iv = normalize_iv(cfg.get("atm_iv"))
    if atm_iv is None:
        atm_iv = atmr.get("iv")

    hard = []
    warnings = []
    entry_modes = {"candidate_entry", "recenter_entry", "rotation_entry"}
    if broker_status == "FAIL":
        hard.append("broker_feasibility_fail")
    if broker_status == "WARN" or auto_warn:
        hard.append("broker_rms_warning")
    if expiry_sessions <= 1.0 and mode in entry_modes and broker_status != "PASS":
        hard.append("new_expiry_eve_entry_requires_broker_pass")

    if atm_straddle is None or atm_straddle <= 0 or atm_iv is None or atm_iv <= 0:
        hard.append("missing_full_next_open_reprice_inputs")
        return {
            "active": True,
            "status": "BLOCK" if mode in entry_modes else "DEGRADED",
            "broker_status": broker_status,
            "latency_severity": latency,
            "hard_failures": sorted(set(hard)),
            "warnings": warnings,
            "same_state_open_pnl_points": None,
            "worst_1_5_straddle_pnl_points": None,
            "worst_2_0_straddle_pnl_points": None,
            "ocr_1_5": None,
            "scenarios": [],
        }

    hours = float(cfg.get("hours_to_next_actionable_exit", carry_days * 24.0))
    days_ahead = max(hours, 0.0) / 24.0
    spread_mult = float(cfg.get("opening_spread_multiplier", 1.5))
    hs = []
    r1, r2, r3 = rows
    for side in (r1.get("put", {}), r2.get("put", {}), r2.get("call", {}), r3.get("call", {})):
        v = half_spread(side)
        if v is not None:
            hs.append(v)
    friction = spread_mult * sum(hs) if len(hs) == 4 else 0.0

    same_close = iron_close_cost(rows, meta, meta["spot"], days_ahead, 0.0)
    same_pnl = entry_credit - same_close - friction if same_close is not None else None
    scenarios = []
    iv_defaults = {1.0: 1.20, 1.5: 1.40, 2.0: 1.60}
    custom = cfg.get("stress_iv_multipliers") or {}
    for m in (1.0, 1.5, 2.0):
        iv_mult = float(custom.get(str(m), custom.get(m, iv_defaults[m])))
        iv_shift_vp = atm_iv * 100.0 * (iv_mult - 1.0)
        for direction in (-1.0, 1.0):
            future_spot = meta["spot"] + direction * m * atm_straddle
            close = iron_close_cost(rows, meta, future_spot, days_ahead, iv_shift_vp)
            if close is None:
                continue
            pnl = entry_credit - close - friction
            scenarios.append({
                "label": f"v21_gap_{'down' if direction < 0 else 'up'}_{m:g}S",
                "straddle_multiple": m,
                "direction": "down" if direction < 0 else "up",
                "future_spot": future_spot,
                "iv_multiplier": iv_mult,
                "iv_shift_vp": iv_shift_vp,
                "pnl_points": pnl,
            })

    def worst(m):
        vals = [z["pnl_points"] for z in scenarios if abs(z["straddle_multiple"] - m) < 1e-9]
        return min(vals) if vals else None

    w15 = worst(1.5)
    w20 = worst(2.0)
    loss15 = max(0.0, -w15) if w15 is not None else None
    if same_pnl is not None and loss15 is not None:
        ocr15 = 999.0 if loss15 <= 0 else max(same_pnl, 0.0) / loss15
    else:
        ocr15 = None

    emp = _empirical_gap_metrics(cfg, meta, rows[1]["strike"], entry_credit, same_pnl, net_gamma)
    _apply_empirical_gap_gate(emp, hard, warnings)

    if len(scenarios) < 6 or same_pnl is None:
        hard.append("incomplete_next_open_full_reprice")
    if latency in {"high", "critical"}:
        if ocr15 is None or ocr15 < 1.0:
            hard.append("high_latency_event_stress_efficiency_fail")
    elif latency == "medium" and ocr15 is not None and ocr15 < 0.5:
        hard.append("medium_latency_event_stress_efficiency_fail")
    if ocr15 is not None and ocr15 < 0.5:
        hard.append("overnight_stress_efficiency_fail")
    elif ocr15 is not None and ocr15 < 1.0:
        warnings.append("moderate_overnight_stress_efficiency")

    status = "BLOCK" if hard else "PASS"
    return {
        "active": True,
        "status": status,
        "broker_status": broker_status,
        "latency_severity": latency,
        "hours_to_next_actionable_exit": hours,
        "same_state_open_pnl_points": same_pnl,
        "worst_1_5_straddle_pnl_points": w15,
        "worst_2_0_straddle_pnl_points": w20,
        "ocr_1_5": ocr15,
        "opening_friction_points": friction,
        "empirical_gap": emp,
        "hard_failures": sorted(set(hard)),
        "warnings": list(dict.fromkeys(warnings)),
        "scenarios": scenarios,
    }


def candidate_metrics(surface, meta, dist, data, k1, k2, k3, carry_days, lot_size):
    byk = row_by_strike(surface)
    if k1 not in byk or k2 not in byk or k3 not in byk:
        return None
    r1, r2, r3 = byk[k1], byk[k2], byk[k3]
    width = k2 - k1
    if abs((k3 - k2) - width) > 1e-9:
        return None

    # Actual symmetric iron-fly execution legs: +lower put, -body put, -body call, +upper call.
    lp = leg_liquidity(r1, "put")
    bc = leg_liquidity(r2, "call")
    bp = leg_liquidity(r2, "put")
    uc = leg_liquidity(r3, "call")
    legs = [lp, bc, bp, uc]
    if any(x["mark"] is None for x in legs):
        return None
    credit = bc["mark"] + bp["mark"] - lp["mark"] - uc["mark"]
    debit = width - credit
    if credit <= 0 or debit <= 0 or debit >= width:
        return None

    stats = loss_stats(dist, k1, k2, k3, debit)
    future_close = iron_close_cost([r1, r2, r3], meta, meta["spot"], carry_days, 0.0)
    theta_capture = (credit - future_close) if future_close is not None else None

    # Live net Greeks from the actual legs where available.
    greek_values = {}
    for g in ("delta", "gamma", "theta", "vega"):
        vals = [
            side_greek(r1.get("put", {}), g),
            side_greek(r2.get("call", {}), g),
            side_greek(r2.get("put", {}), g),
            side_greek(r3.get("call", {}), g),
        ]
        if all(v is not None for v in vals):
            # long lower put - short body call - short body put + long upper call
            greek_values[f"net_{g}"] = vals[0] - vals[1] - vals[2] + vals[3]
        else:
            greek_values[f"net_{g}"] = None

    hs = [x["half_spread"] for x in legs if x["half_spread"] is not None]
    est_oneway_slippage = sum(hs) if len(hs) == 4 else None
    est_roundtrip_slippage = 2.0 * est_oneway_slippage if est_oneway_slippage is not None else None
    ois = [x["oi"] for x in legs if x["oi"] is not None]
    vols = [x["volume"] for x in legs if x["volume"] is not None]
    spreads = [x["spread_pct"] for x in legs if x["spread_pct"] is not None]

    rnd_tail_score = (
        0.40 * stats["prob_loss"]
        + 0.25 * stats["prob_outside_wings"]
        + 0.20 * min(stats["expected_loss_points"] / debit, 1.5)
        + 0.15 * min(stats["cvar95_loss_points"] / debit, 1.5)
    )
    scen = scenario_metrics(data, [r1, r2, r3], meta, credit, debit, carry_days)
    overnight = overnight_stress_metrics(surface, data, [r1, r2, r3], meta, credit, debit, carry_days, greek_values.get("net_gamma"))
    path_component = 0.5 * min(scen["path_tail_loss_ratio"], 2.0) + 0.5 * min(scen["path_expected_loss_ratio"], 2.0)
    overnight_loss_ratio = 0.0
    if overnight.get("active") and overnight.get("worst_1_5_straddle_pnl_points") is not None:
        overnight_loss_ratio = max(0.0, -overnight["worst_1_5_straddle_pnl_points"]) / max(debit, EPS)
    emp = overnight.get("empirical_gap") or {}
    empirical_parts = []
    if emp.get("gap_gamma_burden") is not None:
        empirical_parts.append(min(emp["gap_gamma_burden"], 2.0))
    if emp.get("q90_break_even_buffer_ratio") is not None:
        empirical_parts.append(min(emp["q90_break_even_buffer_ratio"], 2.0))
    empirical_component = sum(empirical_parts) / len(empirical_parts) if empirical_parts else 0.0
    combined_tail = rnd_tail_score + path_component + 0.5 * min(overnight_loss_ratio, 2.0) + 0.5 * empirical_component

    friction_ratio = (est_roundtrip_slippage / debit) if est_roundtrip_slippage is not None else 0.0
    carry_burden = debit / width + friction_ratio
    theta_eff = (theta_capture / debit) if theta_capture is not None else None

    return {
        "lower": k1,
        "center": k2,
        "upper": k3,
        "half_width": width,
        "entry_credit_points": credit,
        "equivalent_long_fly_debit_points": debit,
        "debit_per_lot": debit * lot_size,
        "max_profit_points": credit,
        "max_loss_points": debit,
        "break_even_lower": k2 - credit,
        "break_even_upper": k2 + credit,
        "same_state_carry_points": theta_capture,
        "same_state_carry_per_lot": theta_capture * lot_size if theta_capture is not None else None,
        "theta_capture_pct_debit": theta_eff,
        "carry_ratio_debit_to_width": debit / width,
        "carry_burden_score": carry_burden,
        "est_oneway_slippage_points": est_oneway_slippage,
        "est_roundtrip_slippage_points": est_roundtrip_slippage,
        "min_leg_oi": min(ois) if len(ois) == 4 else None,
        "min_leg_volume": min(vols) if len(vols) == 4 else None,
        "worst_leg_spread_pct": max(spreads) if len(spreads) == 4 else None,
        "rnd_tail_risk_score": rnd_tail_score,
        "combined_tail_risk_score": combined_tail,
        **stats,
        **greek_values,
        **scen,
        "overnight_gate": overnight,
    }


def normalize(values, reverse=False):
    finite = [v for v in values if v is not None and math.isfinite(v)]
    if not finite:
        return [0.5] * len(values)
    lo, hi = min(finite), max(finite)
    if hi - lo < 1e-12:
        return [0.5 if v is not None else 0.0 for v in values]
    out = []
    for v in values:
        if v is None or not math.isfinite(v):
            out.append(0.0)
        else:
            z = (v - lo) / (hi - lo)
            out.append(1.0 - z if reverse else z)
    return out


def dominates(a, b):
    ta, tb = a.get("theta_capture_pct_debit"), b.get("theta_capture_pct_debit")
    if ta is None or tb is None:
        return False
    comps = [
        (ta, tb, ">="),
        (a["carry_burden_score"], b["carry_burden_score"], "<="),
        (a["combined_tail_risk_score"], b["combined_tail_risk_score"], "<="),
    ]
    strict = False
    for x, y, op in comps:
        if op == ">=":
            if x < y - 1e-12:
                return False
            strict = strict or x > y + 1e-12
        else:
            if x > y + 1e-12:
                return False
            strict = strict or x < y - 1e-12
    return strict


def classify_data_health(meta, dist_diag):
    issues = list(meta.get("health_issues") or [])
    repair = dist_diag.get("repair_fraction")
    if repair is not None and repair > 0.25:
        issues.append("heavy_rnd_repair")
    if dist_diag.get("used_strike_count", 0) < 12:
        issues.append("sparse_rnd_grid")
    if repair is not None and repair > 0.55:
        status = "INVALID"
    elif "sparse_local_surface" in issues and meta.get("forward_source") == "spot_fallback":
        status = "INVALID"
    elif issues:
        status = "DEGRADED"
    else:
        status = "HEALTHY"
    return {"status": status, "issues": sorted(set(issues)), "rnd_repair_fraction": repair}


def optimize(data):
    surface, meta = build_surface(data)
    dist, dist_diag = risk_neutral_distribution(surface, meta)
    health = classify_data_health(meta, dist_diag)

    strikes = sorted(r["strike"] for r in surface if r.get("call_mark") is not None)
    byk = set(strikes)
    atm = min(strikes, key=lambda k: abs(k - meta["forward"]))
    atmr = row_by_strike(surface)[atm]
    c_atm, _ = pick_mark(atmr.get("call", {}))
    p_atm, _ = pick_mark(atmr.get("put", {}))
    atm_straddle = (c_atm + p_atm) if c_atm is not None and p_atm is not None else 0.0
    iv_atm = atmr.get("iv") or 0.0
    sigma = meta["spot"] * iv_atm * math.sqrt(meta["t"]) if iv_atm and meta["t"] > 0 else 0.0
    user_min = float(data.get("wide_min_half_width", 0.0))
    horizon_move = float(data.get("horizon_expected_move_points", 0.0) or 0.0)
    raw_min = max(user_min, 1.25 * atm_straddle, 0.015 * meta["spot"], 0.90 * sigma, 1.25 * horizon_move)

    diffs = [b - a for a, b in zip(strikes[:-1], strikes[1:]) if b > a]
    step = min(diffs) if diffs else 1.0
    wide_min = math.ceil(raw_min / step) * step

    q50 = nearest_quantile(dist, 0.50)
    mode = max(dist, key=lambda z: z[1])[0]
    path_center = as_float((data.get("path") or {}).get("expected_center"))
    if path_center is None:
        path_center = as_float(data.get("path_expected_center"))
    target_centers = [meta["forward"], q50, mode]
    if path_center is not None:
        target_centers.append(path_center)

    max_center_distance = float(data.get("max_center_distance", max(0.50 * atm_straddle, 2.0 * step)))
    centers = data.get("centers")
    if centers is None:
        centers = []
        for target in target_centers:
            if target is None:
                continue
            k = min(strikes, key=lambda x: abs(x - target))
            if abs(k - meta["forward"]) <= max_center_distance and k not in centers:
                centers.append(k)
        # Add nearby liquid round strikes for competition.
        for k in strikes:
            if abs(k - meta["forward"]) <= max_center_distance and k not in centers:
                centers.append(k)
    else:
        centers = [float(x) for x in centers]

    widths = data.get("widths")
    if widths is None:
        widths = sorted({abs(k - c) for c in centers for k in strikes if abs(k - c) >= wide_min})
    else:
        widths = sorted(float(x) for x in widths if float(x) >= wide_min)

    lot_size = float(data.get("lot_size", 1.0))
    carry_days = float(data.get("carry_days", 1.0))
    min_oi = data.get("min_oi")
    min_volume = data.get("min_volume")
    max_spread_pct = data.get("max_spread_pct")
    max_slippage_pct_debit = float(data.get("max_slippage_pct_debit", 0.12))

    candidates = []
    overnight_rejected = 0
    for c in centers:
        for w in widths:
            k1, k3 = c - w, c + w
            if k1 not in byk or c not in byk or k3 not in byk:
                continue
            m = candidate_metrics(surface, meta, dist, data, k1, c, k3, carry_days, lot_size)
            if not m:
                continue
            if min_oi is not None and m["min_leg_oi"] is not None and m["min_leg_oi"] < float(min_oi):
                continue
            if min_volume is not None and m["min_leg_volume"] is not None and m["min_leg_volume"] < float(min_volume):
                continue
            if max_spread_pct is not None and m["worst_leg_spread_pct"] is not None and m["worst_leg_spread_pct"] > float(max_spread_pct):
                continue
            if m["est_roundtrip_slippage_points"] is not None and m["est_roundtrip_slippage_points"] / max(m["equivalent_long_fly_debit_points"], EPS) > max_slippage_pct_debit:
                continue
            if m.get("overnight_gate", {}).get("status") == "BLOCK":
                overnight_rejected += 1
                continue
            candidates.append(m)

    base = {
        "engine_version": "v2.1-candidate",
        "underlying": data.get("underlying", data.get("symbol")),
        "asof": data.get("asof"),
        "expiry": data.get("expiry"),
        "meta": meta,
        "data_health": health,
        "atm_strike_used": atm,
        "atm_straddle_points": atm_straddle,
        "expiry_sigma_points": sigma,
        "wide_min_half_width": wide_min,
        "rnd_q10": nearest_quantile(dist, 0.10),
        "rnd_median": q50,
        "rnd_q90": nearest_quantile(dist, 0.90),
        "rnd_mode": mode,
        "distribution_diagnostics": dist_diag,
        "overnight_rejected_count": overnight_rejected,
    }
    if health["status"] == "INVALID":
        return {**base, "candidates": [], "message": "Option surface failed the v2 data-health gate."}
    if not candidates:
        msg = "No candidates survived width/data/liquidity constraints."
        if overnight_rejected > 0:
            msg = "No candidates survived the v2.1 overnight empirical-gap/event/broker/next-open stress gate."
        return {**base, "candidates": [], "message": msg}

    pareto = []
    for i, a in enumerate(candidates):
        if not any(i != j and dominates(b, a) for j, b in enumerate(candidates)):
            pareto.append(a)

    theta_n = normalize([x.get("theta_capture_pct_debit") for x in pareto])
    carry_n = normalize([x["carry_burden_score"] for x in pareto], reverse=True)
    tail_n = normalize([x["combined_tail_risk_score"] for x in pareto], reverse=True)
    liq_raw = []
    for x in pareto:
        oi = math.log1p(max(x.get("min_leg_oi") or 0.0, 0.0))
        vol = math.log1p(max(x.get("min_leg_volume") or 0.0, 0.0))
        sp = x.get("worst_leg_spread_pct")
        penalty = 0.0 if sp is None else 10.0 * sp
        liq_raw.append(oi + vol - penalty)
    liq_n = normalize(liq_raw)

    for x, tn, cn, rn, ln in zip(pareto, theta_n, carry_n, tail_n, liq_n):
        x["optimizer_score"] = (tn + cn + rn) / 3.0
        x["liquidity_tiebreak"] = ln

    pareto.sort(key=lambda x: (x["optimizer_score"], x["liquidity_tiebreak"]), reverse=True)
    candidates.sort(key=lambda x: (x["combined_tail_risk_score"], -(x.get("theta_capture_pct_debit") or -999)))

    return {
        **base,
        "candidate_count": len(candidates),
        "pareto_count": len(pareto),
        "pareto_ranked": pareto,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    data = json.loads(Path(args.input).read_text())
    out = optimize(data)
    print(json.dumps(out, indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
