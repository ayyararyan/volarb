#!/usr/bin/env python3
"""HF intraday physical-RV forecaster for 15-30 minute option decisions.

The script intentionally avoids prior-day calibration. It estimates the current
local variance state from a fresh HF observation block, separates recent jump
pressure, diagnoses drift, and only then compares with current option IV.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

ANNUAL_TRADING_MINUTES = 252.0 * 375.0
EPS = 1e-18
MAD_NORMAL = 0.6744897501960817
MEDIAN_CHI2_1 = 0.4549364231195727


def load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finite(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def parse_ts(x: Any) -> Optional[datetime]:
    if not x:
        return None
    return datetime.fromisoformat(str(x).replace("Z", "+00:00"))


def to_vol_decimal(x: Any) -> Optional[float]:
    v = finite(x)
    if v is None or v <= 0:
        return None
    if v > 3.0:
        v /= 100.0
    return v if v > 0 else None


def percentile(xs: List[float], q: float) -> Optional[float]:
    if not xs:
        return None
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    p = (len(ys) - 1) * q
    lo = int(math.floor(p))
    hi = int(math.ceil(p))
    if lo == hi:
        return ys[lo]
    w = p - lo
    return ys[lo] * (1 - w) + ys[hi] * w


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def downgrade(c: str) -> str:
    return {"high": "medium", "medium": "low", "low": "low"}.get(c, "low")


def quote_price(q: Dict[str, Any]) -> Optional[float]:
    bid = finite(q.get("bid"))
    ask = finite(q.get("ask"))
    if bid is not None and ask is not None and bid > 0 and ask >= bid:
        return 0.5 * (bid + ask)
    p = finite(q.get("price"))
    return p if p is not None and p > 0 else None


def clean_raw_quotes(quotes: Iterable[Dict[str, Any]]) -> List[Tuple[datetime, float]]:
    out: List[Tuple[datetime, float]] = []
    for q in quotes or []:
        ts = parse_ts(q.get("timestamp"))
        p = quote_price(q)
        if ts is not None and p is not None:
            out.append((ts, p))
    out.sort(key=lambda z: z[0])
    # Collapse exact duplicate timestamps robustly.
    dedup: List[Tuple[datetime, float]] = []
    for ts, p in out:
        if dedup and ts == dedup[-1][0]:
            dedup[-1] = (ts, median([dedup[-1][1], p]))
        else:
            dedup.append((ts, p))
    return dedup


def aggregate_quotes(raw: List[Tuple[datetime, float]], bucket_seconds: int) -> List[Tuple[datetime, float]]:
    if not raw:
        return []
    buckets: Dict[int, List[float]] = {}
    tz = raw[-1][0].tzinfo
    for ts, p in raw:
        key = int(ts.timestamp()) // bucket_seconds
        buckets.setdefault(key, []).append(p)
    agg: List[Tuple[datetime, float]] = []
    for key in sorted(buckets):
        sec = key * bucket_seconds + bucket_seconds / 2.0
        ts = datetime.fromtimestamp(sec, tz=tz)
        agg.append((ts, median(buckets[key])))
    return agg


def restrict_window(points: List[Tuple[datetime, float]], observation_minutes: float) -> List[Tuple[datetime, float]]:
    if not points:
        return []
    end = points[-1][0]
    max_age = observation_minutes * 60.0
    return [(t, p) for t, p in points if (end - t).total_seconds() <= max_age + 1e-9]


def path_returns(points: List[Tuple[datetime, float]]) -> Tuple[List[float], List[float], List[float]]:
    rs: List[float] = []
    dts: List[float] = []
    end_ages: List[float] = []
    if len(points) < 2:
        return rs, dts, end_ages
    end = points[-1][0]
    for (ta, pa), (tb, pb) in zip(points[:-1], points[1:]):
        dt = (tb - ta).total_seconds() / 60.0
        if dt <= 0 or pa <= 0 or pb <= 0:
            continue
        rs.append(math.log(pb / pa))
        dts.append(dt)
        end_ages.append((end - tb).total_seconds() / 60.0)
    return rs, dts, end_ages


def hf_quality(points: List[Tuple[datetime, float]]) -> Tuple[str, Dict[str, Any]]:
    if len(points) < 2:
        return "FAIL", {"aggregated_points": len(points), "span_seconds": 0.0}
    span = (points[-1][0] - points[0][0]).total_seconds()
    gaps = [(b[0] - a[0]).total_seconds() for a, b in zip(points[:-1], points[1:])]
    med_gap = median(gaps) if gaps else None
    p90 = percentile(gaps, 0.90)
    max_gap = max(gaps) if gaps else None
    n = len(points)
    if span >= 270 and n >= 40 and med_gap is not None and med_gap <= 7.5 and p90 is not None and p90 <= 12 and max_gap is not None and max_gap <= 20:
        q = "PASS"
    elif span >= 240 and n >= 30 and max_gap is not None and max_gap <= 30:
        q = "DEGRADED"
    else:
        q = "FAIL"
    return q, {
        "aggregated_points": n,
        "span_seconds": span,
        "median_gap_seconds": med_gap,
        "p90_gap_seconds": p90,
        "max_gap_seconds": max_gap,
    }


def robust_scale_u(u: List[float]) -> Tuple[Optional[float], float]:
    if not u:
        return None, 0.0
    m = median(u)
    mad = median([abs(x - m) for x in u])
    scale = mad / MAD_NORMAL if mad > EPS else None
    if scale is None or scale <= EPS:
        sq = [x * x for x in u]
        med_sq = median(sq) if sq else 0.0
        scale = math.sqrt(max(med_sq / MEDIAN_CHI2_1, 0.0)) if med_sq > EPS else None
    return scale, m


def classify_jumps(rs: List[float], dts: List[float], end_ages: List[float], threshold_sigma: float) -> Dict[str, Any]:
    if not rs:
        return {"continuous_mask": [], "jump_indices": [], "jump_events": [], "threshold_sigma": threshold_sigma}
    u = [r / math.sqrt(dt) for r, dt in zip(rs, dts)]
    scale, center = robust_scale_u(u)
    if scale is None or scale <= EPS:
        mask = [True] * len(rs)
        return {
            "continuous_mask": mask,
            "jump_indices": [],
            "jump_events": [],
            "threshold_sigma": threshold_sigma,
            "robust_scale_per_sqrt_min": scale,
        }
    jumps: List[int] = []
    for i, x in enumerate(u):
        if abs(x - center) > threshold_sigma * scale:
            jumps.append(i)
    mask = [i not in set(jumps) for i in range(len(rs))]
    events = [
        {
            "index": i,
            "squared_return": rs[i] * rs[i],
            "return": rs[i],
            "age_minutes": end_ages[i],
            "standardized_abs": abs(u[i] - center) / scale,
        }
        for i in jumps
    ]
    return {
        "continuous_mask": mask,
        "jump_indices": jumps,
        "jump_events": events,
        "threshold_sigma": threshold_sigma,
        "robust_scale_per_sqrt_min": scale,
    }


def continuous_estimators(rs: List[float], dts: List[float], mask: List[bool]) -> Dict[str, Optional[float]]:
    if not rs:
        return {}
    valid_idx = [i for i, keep in enumerate(mask) if keep]
    if len(valid_idx) < 3:
        return {}
    total_dt = sum(dts[i] for i in valid_idx)
    if total_dt <= 0:
        return {}
    rv = sum(rs[i] * rs[i] for i in valid_idx) / total_dt
    u = [rs[i] / math.sqrt(dts[i]) for i in valid_idx]
    med_rate = median([x * x for x in u]) / MEDIAN_CHI2_1 if u else None

    # Thresholded bipower: use only adjacent original returns that are both non-jumps.
    bp_terms: List[float] = []
    for i in range(1, len(rs)):
        if mask[i] and mask[i - 1]:
            ui = rs[i] / math.sqrt(dts[i])
            uj = rs[i - 1] / math.sqrt(dts[i - 1])
            bp_terms.append(abs(ui) * abs(uj))
    bpv = (math.pi / 2.0) * (sum(bp_terms) / len(bp_terms)) if bp_terms else None
    vals = [x for x in (rv, med_rate, bpv) if x is not None and x > EPS]
    return {
        "threshold_rv_rate": rv,
        "robust_median_rate": med_rate,
        "threshold_bpv_rate": bpv,
        "central_rate": median(vals) if vals else None,
        "low_rate": min(vals) if vals else None,
        "high_rate": max(vals) if vals else None,
        "continuous_return_count": len(valid_idx),
    }


def fast_window(rs: List[float], dts: List[float], end_ages: List[float], mask: List[bool], seconds: float) -> Dict[str, Optional[float]]:
    max_age_min = seconds / 60.0
    idx = [i for i, age in enumerate(end_ages) if age <= max_age_min]
    if len(idx) < 4:
        return {}
    rs2 = [rs[i] for i in idx]
    dt2 = [dts[i] for i in idx]
    mask2 = [mask[i] for i in idx]
    return continuous_estimators(rs2, dt2, mask2)


def integrated_persistent_variance(v_slow: float, v_fast: float, horizon: float, tau: float) -> float:
    return max(0.0, v_slow * horizon + (v_fast - v_slow) * tau * (1.0 - math.exp(-horizon / tau)))


def annualized_from_horizon_variance(vh: Optional[float], horizon: float) -> Optional[float]:
    if vh is None or vh <= 0 or horizon <= 0:
        return None
    return math.sqrt((vh / horizon) * ANNUAL_TRADING_MINUTES)


def ohlc_diagnostic(ohlc: Dict[str, Any]) -> Optional[float]:
    if not ohlc:
        return None
    h = finite(ohlc.get("high"))
    l = finite(ohlc.get("low"))
    elapsed = finite(ohlc.get("elapsed_minutes"))
    if h is None or l is None or elapsed is None or h <= 0 or l <= 0 or h < l or elapsed <= 0:
        return None
    rate = (math.log(h / l) ** 2) / (4.0 * math.log(2.0)) / elapsed
    return math.sqrt(rate * ANNUAL_TRADING_MINUTES) if rate > EPS else None


def surface_migration(
    snaps: Iterable[Dict[str, Any]], current_straddle: Optional[float]
) -> Tuple[Optional[float], Optional[float], Dict[str, float]]:
    """Measure centre migration without letting the bucketed RND mode hard-trigger drift.

    Primary centre evidence is parity forward, RND median, and timestamp-aligned
    futures. RND mode is deliberately reported separately because an argmax over a
    discrete strike grid can jump one strike after a very small density change.
    """
    clean = []
    for s in snaps or []:
        ts = parse_ts(s.get("timestamp"))
        if ts is not None:
            clean.append((ts, s))
    clean.sort(key=lambda z: z[0])
    if len(clean) < 2 or current_straddle is None or current_straddle <= 0:
        return None, None, {}
    first = clean[0][1]
    last = clean[-1][1]
    details: Dict[str, float] = {}
    primary_vals: List[float] = []
    for k in ("forward", "rnd_median", "futures", "rnd_mode"):
        a = finite(first.get(k))
        b = finite(last.get(k))
        if a is not None and b is not None:
            x = abs(b - a) / current_straddle
            details[k] = x
            if k != "rnd_mode":
                primary_vals.append(x)
    primary = max(primary_vals) if primary_vals else None
    mode = details.get("rnd_mode")
    return primary, mode, details


def drift_diagnostics(points: List[Tuple[datetime, float]], rs: List[float], v_slow: Optional[float], current_straddle: Optional[float], surface_snaps: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    de = None
    z = None
    pdisp = None
    if rs:
        denom = sum(abs(r) for r in rs)
        de = abs(sum(rs)) / denom if denom > EPS else 0.0
    if len(points) >= 2:
        span_min = (points[-1][0] - points[0][0]).total_seconds() / 60.0
        if v_slow is not None and v_slow > EPS and span_min > 0:
            z = abs(math.log(points[-1][1] / points[0][1])) / math.sqrt(v_slow * span_min)
        if current_straddle is not None and current_straddle > 0:
            pdisp = abs(points[-1][1] - points[0][1]) / current_straddle
    cmig, mode_mig, cdetails = surface_migration(surface_snaps, current_straddle)
    known = [x for x in (de, z, pdisp, cmig) if x is not None]
    if len(known) < 2:
        risk = "UNKNOWN"
    else:
        high = (
            (z is not None and z >= 1.5)
            or (de is not None and de >= 0.80)
            or (pdisp is not None and pdisp >= 0.50)
            or (cmig is not None and cmig >= 0.50)
        )
        low = (
            (z is None or z <= 1.0)
            and (de is None or de <= 0.60)
            and (pdisp is None or pdisp <= 0.25)
            and (cmig is None or cmig <= 0.25)
        )
        risk = "HIGH" if high else "LOW" if low else "MEDIUM"
    mode_warning = bool(mode_mig is not None and mode_mig >= 0.50)
    return {
        "drift_risk": risk,
        "directional_efficiency": de,
        "net_displacement_sigma": z,
        "price_displacement_straddles": pdisp,
        "center_migration_straddles": cmig,
        "mode_migration_straddles": mode_mig,
        "mode_bucket_warning": mode_warning,
        "center_migration_details": cdetails,
    }


def news_state(news: Dict[str, Any]) -> Tuple[bool, bool, Dict[str, str]]:
    news = news or {}
    agg = str(news.get("aggregate_state", "UNKNOWN")).upper()
    rel = str(news.get("max_butterfly_relevance", "unknown")).lower()
    lat = str(news.get("max_latency_severity", "unknown")).lower()
    override = lat in {"high", "critical"} or rel == "critical" or agg == "TAIL_RISK_ACTIVE"
    developing = lat == "medium" or rel == "material" or agg in {"EVENTFUL", "HIGH_UNCERTAINTY"}
    return override, developing, {"aggregate_state": agg, "butterfly_relevance": rel, "latency": lat}


def evaluate(x: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(x.get("symbol", "UNKNOWN")).upper()
    horizon = finite(x.get("horizon_minutes"))
    if horizon is None or horizon <= 0:
        raise ValueError("horizon_minutes must be positive")

    cfg = x.get("config") or {}
    bucket_seconds = int(finite(cfg.get("bucket_seconds")) or 5)
    observation_minutes = finite(cfg.get("observation_minutes")) or 5.0
    fast_window_seconds = finite(cfg.get("fast_window_seconds")) or 90.0
    threshold_sigma = finite(cfg.get("jump_threshold_sigma")) or 4.0
    tau_v = finite(cfg.get("volatility_decay_minutes"))
    if tau_v is None:
        tau_v = clamp(horizon / 2.0, 5.0, 20.0)
    tau_j = finite(cfg.get("jump_decay_minutes")) or 30.0

    current = x.get("current") or {}
    spot = finite(current.get("spot"))
    if spot is None or spot <= 0:
        raise ValueError("current.spot must be positive")
    straddle = finite(current.get("atm_straddle"))

    raw = clean_raw_quotes(x.get("hf_quotes") or [])
    agg = restrict_window(aggregate_quotes(raw, bucket_seconds), observation_minutes)
    quality, qdiag = hf_quality(agg)
    rs, dts, ages = path_returns(agg)

    if quality == "FAIL":
        return {
            "status": "INSUFFICIENT_HF_DATA",
            "symbol": symbol,
            "horizon_minutes": horizon,
            "hf_quality": quality,
            "hf_regime_state": "INSUFFICIENT_HF_DATA",
            "short_gamma_state": "INSUFFICIENT_DATA",
            "confidence": "low",
            "ohlc_diagnostic_rv_ann": ohlc_diagnostic(x.get("session_ohlc") or {}),
            "why": "A genuine approximately five-minute high-frequency block is required for an actionable short-horizon RV forecast.",
            "diagnostics": qdiag,
        }

    jumps = classify_jumps(rs, dts, ages, threshold_sigma)
    cont = continuous_estimators(rs, dts, jumps["continuous_mask"])
    if cont.get("central_rate") is None:
        return {
            "status": "INSUFFICIENT_HF_DATA",
            "symbol": symbol,
            "horizon_minutes": horizon,
            "hf_quality": quality,
            "hf_regime_state": "INSUFFICIENT_HF_DATA",
            "short_gamma_state": "INSUFFICIENT_DATA",
            "confidence": "low",
            "why": "The HF block contains too little usable continuous variation after cleaning/jump separation.",
            "diagnostics": qdiag,
        }

    fast = fast_window(rs, dts, ages, jumps["continuous_mask"], fast_window_seconds)
    v_slow = float(cont["central_rate"])
    v_fast = float(fast.get("central_rate") or v_slow)
    continuous_ivar = integrated_persistent_variance(v_slow, v_fast, horizon, tau_v)
    low_ivar = max(EPS, float(cont.get("low_rate") or v_slow) * horizon)
    high_local = max(float(cont.get("high_rate") or v_slow), v_fast)
    high_cont_ivar = high_local * horizon

    events = jumps.get("jump_events") or []
    observed_minutes = qdiag.get("span_seconds", 0.0) / 60.0
    if observed_minutes <= 0:
        observed_minutes = observation_minutes
    jp0 = sum(e["squared_return"] * math.exp(-e["age_minutes"] / tau_j) for e in events) / max(observed_minutes, EPS)
    jp_h = jp0 * tau_j * (1.0 - math.exp(-horizon / tau_j)) if events else 0.0
    jump_count = len(events)
    jump_state = "QUIET" if jump_count == 0 else "RECENT_JUMP" if jump_count == 1 else "SELF_EXCITING"
    central_jump_fraction = 0.0 if jump_state == "QUIET" else 0.5 if jump_state == "RECENT_JUMP" else 1.0
    total_ivar = continuous_ivar + central_jump_fraction * jp_h
    upper_ivar = high_cont_ivar + jp_h

    total_raw_rv = sum(r * r for r in rs)
    jump_var_obs = sum(e["squared_return"] for e in events)
    jump_share = jump_var_obs / total_raw_rv if total_raw_rv > EPS else 0.0

    cont_ann = annualized_from_horizon_variance(continuous_ivar, horizon)
    total_ann = annualized_from_horizon_variance(total_ivar, horizon)
    upper_ann = annualized_from_horizon_variance(upper_ivar, horizon)
    lower_ann = annualized_from_horizon_variance(low_ivar, horizon)

    implied = to_vol_decimal(current.get("model_free_implied_vol")) or to_vol_decimal(current.get("atm_iv"))
    implied_type = "MODEL_FREE_VARIANCE" if to_vol_decimal(current.get("model_free_implied_vol")) is not None else "ATM_IV" if implied is not None else None
    implied_ivar = implied * implied * horizon / ANNUAL_TRADING_MINUTES if implied is not None else None
    robust_edge = bool(implied_ivar is not None and upper_ivar < implied_ivar)
    central_edge = bool(implied_ivar is not None and total_ivar < implied_ivar)

    drift = drift_diagnostics(agg, rs, v_slow, straddle, x.get("surface_snapshots") or [])
    override, developing, ndiag = news_state(x.get("news_filter") or {})

    if quality == "PASS" and len(rs) >= 50:
        confidence = "high"
    else:
        confidence = "medium"
    if drift["drift_risk"] == "UNKNOWN":
        confidence = downgrade(confidence)

    ratio = total_ann / implied if total_ann is not None and implied is not None and implied > 0 else None
    variance_edge_ann2 = implied * implied - total_ann * total_ann if total_ann is not None and implied is not None else None

    if implied is None:
        short = "INSUFFICIENT_DATA"
        hf_state = "INSUFFICIENT_HF_DATA"
        status = "LOW_CONFIDENCE"
        why = "HF physical RV was estimated, but no current implied-volatility anchor was available."
    elif override:
        short = "UNFAVOURABLE"
        hf_state = "EVENT_RISK"
        status = "CURRENT"
        why = "A near-horizon exogenous event/jump override dominates the live diffusion forecast."
    elif drift["drift_risk"] == "HIGH":
        short = "UNFAVOURABLE"
        hf_state = "DRIFTING"
        status = "CURRENT"
        why = "The local price/forward/RND centre is migrating too directionally for a stationary short-gamma trade."
    elif not central_edge:
        short = "UNFAVOURABLE"
        hf_state = "RV_TOO_HIGH"
        status = "CURRENT"
        why = "Jump-adjusted physical RV is at or above same-horizon option-implied variance."
    elif robust_edge and drift["drift_risk"] == "LOW" and confidence in {"medium", "high"} and jump_state != "SELF_EXCITING" and not developing:
        short = "FAVOURABLE"
        hf_state = "QUIET_EDGE" if jump_state == "QUIET" else "VOL_EDGE_WITH_JUMP_RISK"
        status = "CURRENT"
        why = "Even the upper jump-adjusted RV forecast remains below implied variance, with low drift and no event override."
    else:
        short = "MARGINAL"
        hf_state = "VOL_EDGE_WITH_JUMP_RISK" if jump_state != "QUIET" else "QUIET_EDGE"
        if drift["drift_risk"] == "MEDIUM":
            hf_state = "DRIFTING"
        status = "CURRENT" if confidence != "low" else "LOW_CONFIDENCE"
        why = "The central RV-IV edge is positive, but jump pressure, drift, events, or forecast uncertainty prevents a robust short-gamma signal."

    sigma_move = spot * math.sqrt(total_ivar) if total_ivar > 0 else None
    upper_sigma_move = spot * math.sqrt(upper_ivar) if upper_ivar > 0 else None

    return {
        "status": status,
        "symbol": symbol,
        "horizon_minutes": horizon,
        "hf_quality": quality,
        "hf_regime_state": hf_state,
        "short_gamma_state": short,
        "confidence": confidence,
        "continuous_rv_forecast_ann": cont_ann,
        "jump_adjusted_rv_forecast_ann": total_ann,
        "physical_rv_band_ann": [lower_ann, upper_ann],
        "upper_rv_forecast_ann": upper_ann,
        "implied_vol_anchor_ann": implied,
        "implied_anchor_type": implied_type,
        "forecast_horizon_variance": total_ivar,
        "continuous_forecast_horizon_variance": continuous_ivar,
        "upper_forecast_horizon_variance": upper_ivar,
        "implied_horizon_variance": implied_ivar,
        "rv_iv_ratio": ratio,
        "variance_edge_ann2": variance_edge_ann2,
        "robust_iv_over_rv": robust_edge,
        "forecast_sigma_move_points": sigma_move,
        "upper_forecast_sigma_move_points": upper_sigma_move,
        "fast_variance_rate": v_fast,
        "slow_variance_rate": v_slow,
        "fast_slow_variance_ratio": v_fast / v_slow if v_slow > EPS else None,
        "jump_state": jump_state,
        "jump_count": jump_count,
        "jump_share_observed_rv": jump_share,
        "jump_pressure_variance": jp_h,
        "jump_event_override": override,
        "developing_event_state": developing,
        **drift,
        "why": why,
        "diagnostics": {
            **qdiag,
            "bucket_seconds": bucket_seconds,
            "observation_minutes_target": observation_minutes,
            "fast_window_seconds": fast_window_seconds,
            "volatility_decay_minutes": tau_v,
            "jump_decay_minutes": tau_j,
            "jump_threshold_sigma": threshold_sigma,
            "continuous_estimators": cont,
            "fast_estimators": fast,
            "jump_events": events,
            "news": ndiag,
            "ohlc_diagnostic_rv_ann": ohlc_diagnostic(x.get("session_ohlc") or {}),
            "annual_trading_minutes": ANNUAL_TRADING_MINUTES,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Forecast 15-30 minute physical RV from a fresh HF observation block")
    ap.add_argument("--input", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    print(json.dumps(evaluate(load_json(args.input)), indent=2 if args.pretty else None, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
