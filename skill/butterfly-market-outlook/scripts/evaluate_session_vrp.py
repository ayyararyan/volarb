#!/usr/bin/env python3
"""Session-level variance-risk-premium gate.

Consumes the local eSSVI/HAR dashboard state (``GET /api/state``) or an
equivalent hand-built snapshot and returns one deterministic state:

    FAVOURABLE   front-expiry ATM implied vol exceeds the HAR next-session
                 realized-vol forecast by at least the required margin, the
                 surface fit is live and arbitrage-clean, and the forecast is
                 current.
    UNFAVOURABLE the premium is absent or below the margin.
    UNKNOWN      the dashboard is stale, unfitted, arbitrage-violating, or the
                 forecast is missing/old. Unknown is never benign.

This gate answers "is there a variance risk premium to harvest this session"
before any intraday HF gate is even attempted. It is a precondition for a NEW
intraday butterfly; it never forces an exit of an existing position by itself.

Usage:
    python scripts/evaluate_session_vrp.py --input essvi_state.json --pretty
    python scripts/evaluate_session_vrp.py --url http://127.0.0.1:8770/api/state --pretty
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_MIN_MARGIN_VOL_POINTS = 1.0     # IV - RV, in annualized vol points
DEFAULT_MIN_RATIO = 1.05                # IV / RV
DEFAULT_MAX_FIT_AGE_SECONDS = 120.0
DEFAULT_MAX_FORECAST_AGE_DAYS = 1       # forecast as-of session must be the prior session


def _finite(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _parse_ts(x: Any) -> Optional[datetime]:
    if not x:
        return None
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except ValueError:
        return None


def evaluate(state: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = config or {}
    min_margin = _finite(cfg.get("min_margin_vol_points"))
    min_margin = DEFAULT_MIN_MARGIN_VOL_POINTS if min_margin is None else min_margin
    min_ratio = _finite(cfg.get("min_ratio"))
    min_ratio = DEFAULT_MIN_RATIO if min_ratio is None else min_ratio
    max_fit_age = _finite(cfg.get("max_fit_age_seconds")) or DEFAULT_MAX_FIT_AGE_SECONDS
    max_forecast_age_days = int(_finite(cfg.get("max_forecast_age_days")) or DEFAULT_MAX_FORECAST_AGE_DAYS)

    reasons = []
    warnings = []

    def object_field(value: Any, name: str) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        reasons.append(f"{name} must be an object")
        return {}

    state = object_field(state, "state")
    verdict = object_field(state.get("verdict", {}), "verdict")
    health = object_field(state.get("health", {}), "health")
    forecast = object_field(state.get("forecast", {}), "forecast")
    atm = object_field(state.get("atm", {}), "atm")
    front = object_field(atm.get("front", {}), "atm.front")
    arbitrage = object_field(state.get("arbitrage", {}), "arbitrage")

    if str(verdict.get("status", health.get("status", ""))).lower() != "live":
        reasons.append("surface feed is not live")
    if verdict.get("surface_is_stale") or state.get("surface_is_stale"):
        reasons.append("surface flagged stale")
    if state.get("fit_ok") is not True:
        reasons.append("surface fit failed or is unverified")
    fit_age = _finite(state.get("fit_age_seconds"))
    if fit_age is None or fit_age > max_fit_age:
        reasons.append(f"fit age unavailable or above {max_fit_age:.0f}s")
    if arbitrage.get("checked") is not True:
        reasons.append("surface arbitrage checks are unverified")
    elif arbitrage.get("passed") is not True:
        reasons.append("surface fails butterfly/calendar arbitrage checks")
    if str(front.get("status", "")).lower() != "fitted":
        reasons.append("front-expiry ATM IV is not fitted")
    if str(forecast.get("status", "")).lower() != "ok":
        reasons.append("HAR forecast unavailable")
    age_days = _finite(forecast.get("age_calendar_days"))
    if age_days is None or age_days > max_forecast_age_days:
        reasons.append(f"HAR forecast older than {max_forecast_age_days} calendar day(s) or age unknown")

    iv = _finite(front.get("implied_volatility"))
    rv = _finite(forecast.get("annualized_volatility"))
    if iv is None or iv <= 0:
        reasons.append("front ATM IV missing")
    if rv is None or rv <= 0:
        reasons.append("HAR RV forecast missing")

    result: Dict[str, Any] = {
        "front_expiry": front.get("expiry"),
        "front_atm_iv_ann": iv,
        "har_rv_forecast_ann": rv,
        "iv_minus_rv_vol_points": None,
        "iv_over_rv_ratio": None,
        "min_margin_vol_points": min_margin,
        "min_ratio": min_ratio,
        "forecast_asof_session": forecast.get("asof_session"),
        "observation_timestamp": state.get("now") or health.get("observation_timestamp"),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_note": (
            "IV covers the front option expiry; HAR forecasts one full session including its overnight gap. "
            "These are different horizons; the gate uses the difference only as a session-level premium screen, not a tradable spread."
        ),
    }

    if reasons:
        result.update(session_vrp_state="UNKNOWN", reasons=reasons, warnings=warnings,
                      why="Session VRP cannot be established: " + "; ".join(reasons) + ".")
        return result

    margin = (iv - rv) * 100.0
    ratio = iv / rv
    result["iv_minus_rv_vol_points"] = margin
    result["iv_over_rv_ratio"] = ratio

    maturity = _finite(front.get("maturity_days"))
    if maturity is not None and maturity < 2:
        warnings.append("front expiry under two days: IV anchor is gamma-dominated; prefer the next expiry's ATM reading")

    if margin >= min_margin and ratio >= min_ratio:
        result.update(session_vrp_state="FAVOURABLE", reasons=[], warnings=warnings,
                      why=f"Front ATM IV {iv*100:.1f}% exceeds HAR RV forecast {rv*100:.1f}% by {margin:.1f} vol points (ratio {ratio:.2f}).")
    else:
        result.update(session_vrp_state="UNFAVOURABLE", reasons=[], warnings=warnings,
                      why=f"No harvestable premium: front ATM IV {iv*100:.1f}% versus HAR RV forecast {rv*100:.1f}% (margin {margin:+.1f} vol points, ratio {ratio:.2f}).")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Path to a saved dashboard /api/state JSON")
    source.add_argument("--url", help="Live dashboard state URL, e.g. http://127.0.0.1:8770/api/state")
    parser.add_argument("--min-margin-vol-points", type=float, default=DEFAULT_MIN_MARGIN_VOL_POINTS)
    parser.add_argument("--min-ratio", type=float, default=DEFAULT_MIN_RATIO)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    if args.input:
        state = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        from urllib.request import urlopen  # local loopback only; no credentials
        with urlopen(args.url, timeout=10) as response:  # noqa: S310 - operator-supplied loopback URL
            state = json.loads(response.read().decode("utf-8"))

    result = evaluate(state, {"min_margin_vol_points": args.min_margin_vol_points, "min_ratio": args.min_ratio})
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
