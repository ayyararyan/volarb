#!/usr/bin/env python3
"""Engine v2.1 overnight-carry gate for short-gamma butterflies.

Evaluates the intended next-actionable-exit horizon rather than expiry payoff alone.
Uses full four-leg repricing when normalized chain data are supplied; otherwise it can
consume prepared same-state/stress P&Ls from the orchestrator.
"""

import argparse
import json
import math
from pathlib import Path

import optimize_butterflies as ob

EPS = 1e-12
SEV_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def load_json(path):
    return json.loads(Path(path).read_text())


def norm_status(x):
    s = str(x or "UNKNOWN").upper()
    return s if s in {"PASS", "UNKNOWN", "WARN", "FAIL"} else "UNKNOWN"


def max_latency_severity(events):
    best = "low"
    for e in events or []:
        if not e.get("inside_untradeable_window", e.get("latency_critical", False)):
            continue
        sev = str(e.get("severity", "low")).lower()
        if SEV_ORDER.get(sev, 0) > SEV_ORDER.get(best, 0):
            best = sev
    return best


def halfspread_sum(rows):
    r1, r2, r3 = rows
    sides = [r1.get("put", {}), r2.get("put", {}), r2.get("call", {}), r3.get("call", {})]
    vals = [ob.half_spread(s) for s in sides]
    if not all(v is not None for v in vals):
        return 0.0
    return sum(vals)


def derive_credit(rows):
    r1, r2, r3 = rows
    p1, _ = ob.pick_mark(r1.get("put", {}))
    p2, _ = ob.pick_mark(r2.get("put", {}))
    c2, _ = ob.pick_mark(r2.get("call", {}))
    c3, _ = ob.pick_mark(r3.get("call", {}))
    if any(v is None for v in (p1, p2, c2, c3)):
        return None
    return c2 + p2 - p1 - c3


def prepared_scenarios(x):
    same = x.get("same_state_open_pnl_points")
    stress = x.get("stress_scenarios") or []
    if same is None or not stress:
        return None
    out = []
    for s in stress:
        m = float(s["straddle_multiple"])
        pnl = float(s["pnl_points"])
        direction = str(s.get("direction", "unknown"))
        out.append({
            "label": s.get("label", f"prepared_{direction}_{m:g}S"),
            "straddle_multiple": m,
            "direction": direction,
            "pnl_points": pnl,
            "iv_multiplier": s.get("iv_multiplier"),
        })
    return {
        "source": "prepared",
        "full_reprice": bool(x.get("full_reprice", False)),
        "same_state_open_pnl_points": float(same),
        "stress_scenarios": out,
    }


def reprice_scenarios(x):
    if not x.get("chain"):
        return None
    required = ["lower", "center", "upper"]
    if any(k not in x for k in required):
        return None

    surface, meta = ob.build_surface(x)
    byk = ob.row_by_strike(surface)
    k1, k2, k3 = float(x["lower"]), float(x["center"]), float(x["upper"])
    if any(k not in byk for k in (k1, k2, k3)):
        return None
    rows = [byk[k1], byk[k2], byk[k3]]

    entry_credit = x.get("entry_credit")
    if entry_credit is None:
        entry_credit = derive_credit(rows)
    if entry_credit is None:
        return None
    entry_credit = float(entry_credit)

    strikes = sorted(r["strike"] for r in surface if r.get("call_mark") is not None)
    if not strikes:
        return None
    atm = min(strikes, key=lambda k: abs(k - meta["forward"]))
    atmr = byk[atm]
    c_atm, _ = ob.pick_mark(atmr.get("call", {}))
    p_atm, _ = ob.pick_mark(atmr.get("put", {}))
    if c_atm is None or p_atm is None:
        return None
    atm_straddle = float(x.get("atm_straddle", c_atm + p_atm))
    atm_iv = x.get("atm_iv")
    if atm_iv is None:
        atm_iv = atmr.get("iv")
    atm_iv = ob.normalize_iv(atm_iv)
    if atm_iv is None:
        return None

    hours = float(x.get("hours_to_next_actionable_exit", 18.5))
    days_ahead = max(hours, 0.0) / 24.0
    spread_mult = float(x.get("opening_spread_multiplier", 1.5))
    friction = spread_mult * halfspread_sum(rows)

    same_close = ob.iron_close_cost(rows, meta, meta["spot"], days_ahead, 0.0)
    if same_close is None:
        return None
    same_pnl = entry_credit - same_close - friction

    mults = x.get("stress_straddle_multiples", [1.0, 1.5, 2.0])
    iv_mult_map = {1.0: 1.20, 1.5: 1.40, 2.0: 1.60}
    custom_ivs = x.get("stress_iv_multipliers") or {}
    scenarios = []
    for raw_m in mults:
        m = float(raw_m)
        iv_mult = float(custom_ivs.get(str(m), custom_ivs.get(m, iv_mult_map.get(m, 1.0 + 0.4 * max(m - 0.5, 0.0)))))
        iv_shift_vp = atm_iv * 100.0 * (iv_mult - 1.0)
        for direction in (-1.0, 1.0):
            future_spot = meta["spot"] + direction * m * atm_straddle
            close = ob.iron_close_cost(rows, meta, future_spot, days_ahead, iv_shift_vp)
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

    if len(scenarios) < 6:
        return None
    return {
        "source": "full_four_leg_reprice",
        "full_reprice": True,
        "reference_spot": meta["spot"],
        "reference_forward": meta["forward"],
        "atm_straddle": atm_straddle,
        "atm_iv": atm_iv,
        "hours_to_next_actionable_exit": hours,
        "same_state_open_pnl_points": same_pnl,
        "stress_scenarios": scenarios,
        "opening_friction_points": friction,
    }


def worst_for_multiple(scenarios, multiple):
    vals = [s["pnl_points"] for s in scenarios if abs(float(s["straddle_multiple"]) - multiple) < 1e-9]
    return min(vals) if vals else None



def _quantile(values, q):
    vals = sorted(float(v) for v in values)
    if not vals:
        return None
    h = (len(vals) - 1) * float(q)
    lo = int(math.floor(h))
    hi = int(math.ceil(h))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (h - lo)


def empirical_gap_metrics(x, same_state_open, scen):
    """Summarize the recent close-to-next-open gap regime.

    gap_pct values are percentage points, e.g. -0.96 means a -0.96% opening gap.
    This is an empirical risk screen, not a probability forecast.
    """
    cfg = x.get("empirical_gap_gate") or {}
    mode = str(x.get("mode", "open_position"))
    entry_modes = {"candidate_entry", "recenter_entry", "rotation_entry"}
    required = bool(cfg.get("required", mode in entry_modes))
    raw = cfg.get("gap_pct", cfg.get("recent_gap_pct", [])) or []
    vals = []
    for v in raw:
        try:
            z = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(z):
            vals.append(z)

    min_obs = max(int(cfg.get("min_observations", 15)), 1)
    out = {
        "required": required,
        "source": cfg.get("source"),
        "sample_size": len(vals),
        "min_observations": min_obs,
        "sufficient_history": len(vals) >= min_obs,
        "median_abs_gap_pct": None,
        "p80_abs_gap_pct": None,
        "p90_abs_gap_pct": None,
        "large_gap_threshold_pct": float(cfg.get("large_gap_threshold_pct", 0.50)),
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
    out["median_abs_gap_pct"] = _quantile(av, 0.50)
    out["p80_abs_gap_pct"] = _quantile(av, 0.80)
    out["p90_abs_gap_pct"] = _quantile(av, 0.90)
    thr = out["large_gap_threshold_pct"]
    out["large_gap_rate"] = sum(1 for v in av if v >= thr) / len(av)

    spot = cfg.get("reference_spot", x.get("spot"))
    if spot is None and scen:
        spot = scen.get("reference_spot")
    spot = float(spot) if spot is not None else None

    gamma = cfg.get("net_gamma", x.get("net_gamma"))
    gamma = float(gamma) if gamma is not None else None
    if spot is not None:
        out["p90_gap_points"] = spot * out["p90_abs_gap_pct"] / 100.0
        if gamma is not None:
            gap_points_sq = [(spot * v / 100.0) ** 2 for v in vals]
            drag = 0.5 * abs(gamma) * (sum(gap_points_sq) / len(gap_points_sq))
            out["expected_local_gamma_drag_points"] = drag
            if same_state_open is not None and float(same_state_open) > EPS:
                out["gap_gamma_burden"] = drag / float(same_state_open)

    buffer_points = cfg.get("nearest_break_even_buffer_points")
    if buffer_points is None:
        lower_be = cfg.get("break_even_lower", x.get("break_even_lower"))
        upper_be = cfg.get("break_even_upper", x.get("break_even_upper"))
        if (lower_be is None or upper_be is None) and x.get("center") is not None:
            credit = x.get("entry_credit")
            if credit is not None:
                lower_be = float(x["center"]) - float(credit)
                upper_be = float(x["center"]) + float(credit)
        if spot is not None and lower_be is not None and upper_be is not None:
            buffer_points = min(spot - float(lower_be), float(upper_be) - spot)

    if buffer_points is not None:
        buffer_points = float(buffer_points)
        out["nearest_break_even_buffer_points"] = buffer_points
        if buffer_points <= 0:
            out["spot_outside_break_even"] = True
        elif out["p90_gap_points"] is not None:
            out["q90_break_even_buffer_ratio"] = out["p90_gap_points"] / buffer_points

    return out


def apply_empirical_gap_gate(emp, hard, warnings):
    if emp.get("required") and not emp.get("sufficient_history"):
        hard.append("insufficient_recent_gap_history")
        return

    if not emp.get("sufficient_history"):
        return

    if emp.get("spot_outside_break_even"):
        hard.append("spot_outside_break_even_before_overnight")

    buffer_ratio = emp.get("q90_break_even_buffer_ratio")
    if buffer_ratio is not None:
        if buffer_ratio >= 1.0:
            hard.append("recent_q90_gap_exceeds_break_even_buffer")
        elif buffer_ratio >= 0.80:
            warnings.append("recent_q90_gap_near_break_even_buffer")

    burden = emp.get("gap_gamma_burden")
    if burden is not None:
        if burden >= 1.0:
            hard.append("empirical_gap_gamma_exceeds_same_state_harvest")
        elif burden >= 0.60:
            warnings.append("recent_gap_gamma_consumes_most_same_state_harvest")

    if (emp.get("large_gap_rate") or 0.0) >= 0.15:
        warnings.append("recent_large_gap_frequency_elevated")

def evaluate(x):
    mode = str(x.get("mode", "open_position"))
    crosses = bool(x.get("crosses_market_close", x.get("holding_crosses_market_close", False)))
    expiry_sessions = float(x.get("expiry_sessions_remaining", 999))
    mandatory = crosses and expiry_sessions <= 2
    after_1430_new = bool(x.get("new_entry_after_1430", False)) and mode in {"candidate_entry", "recenter_entry", "rotation_entry"}
    active = mandatory or after_1430_new or bool(x.get("force_overnight_gate", False))

    market_actionable = bool(x.get("market_actionable", True))
    broker = x.get("broker", {}) or {}
    broker_status = norm_status(broker.get("status", x.get("broker_feasibility_status")))
    auto_warn = bool(broker.get("auto_squareoff_warning", x.get("broker_auto_squareoff_warning", False)))
    if auto_warn and broker_status == "PASS":
        broker_status = "WARN"

    events = x.get("events", x.get("event_clock", [])) or []
    latency_sev = max_latency_severity(events)

    scen = reprice_scenarios(x) or prepared_scenarios(x)
    full_reprice = bool(scen and scen.get("full_reprice"))
    same = scen.get("same_state_open_pnl_points") if scen else None
    stress = scen.get("stress_scenarios", []) if scen else []
    worst_10 = worst_for_multiple(stress, 1.0)
    worst_15 = worst_for_multiple(stress, 1.5)
    worst_20 = worst_for_multiple(stress, 2.0)
    loss_15 = max(0.0, -(worst_15 or 0.0)) if worst_15 is not None else None
    ocr_15 = None
    if same is not None and loss_15 is not None and loss_15 > 0:
        ocr_15 = max(float(same), 0.0) / loss_15
    elif same is not None and loss_15 == 0:
        ocr_15 = 999.0

    emp = empirical_gap_metrics(x, same, scen)

    hard = []
    warnings = []

    if not active:
        state = "NOT_APPLICABLE"
        reason = "The position does not trigger the v2.1 overnight-carry gate."
    elif not market_actionable:
        state = "LOCKED_OVERNIGHT"
        reason = "The home option market is closed; this is a monitoring/contingency state, not a fresh carry decision."
        if auto_warn or broker_status in {"WARN", "FAIL"}:
            warnings.append("Broker/RMS warning exists while the position is already locked overnight; prioritize exit at the next actionable window.")
    else:
        new_expiry_eve = mode in {"candidate_entry", "recenter_entry", "rotation_entry"} and expiry_sessions <= 1.0
        apply_empirical_gap_gate(emp, hard, warnings)
        if broker_status == "FAIL":
            hard.append("broker_feasibility_fail")
        if auto_warn or broker_status == "WARN":
            hard.append("broker_rms_warning")
        if new_expiry_eve and broker_status != "PASS":
            hard.append("new_expiry_eve_entry_requires_broker_pass")

        if mandatory and scen is None:
            hard.append("missing_next_open_stress")
        elif mandatory and not full_reprice and mode in {"candidate_entry", "recenter_entry", "rotation_entry"}:
            hard.append("new_expiry_eve_entry_requires_full_reprice")

        if latency_sev in {"high", "critical"}:
            if not full_reprice:
                hard.append("latency_event_without_full_reprice")
            elif ocr_15 is None or ocr_15 < 1.0:
                hard.append("high_latency_event_stress_efficiency_fail")
        elif latency_sev == "medium" and ocr_15 is not None and ocr_15 < 0.5:
            hard.append("medium_latency_event_stress_efficiency_fail")

        if ocr_15 is not None and ocr_15 < 0.5:
            hard.append("overnight_stress_efficiency_fail")
        elif ocr_15 is not None and ocr_15 < 1.0:
            warnings.append("Overnight stress efficiency is only moderate; carry is eligible only in a benign event regime with validated broker feasibility.")

        expected = x.get("explicit_real_world_expected_open_pnl_points")
        if expected is not None and float(expected) <= 0:
            hard.append("explicit_expected_open_pnl_nonpositive")

        if hard:
            state = "BLOCK"
            reason = "One or more v2.1 overnight hard gates failed."
        elif scen is None:
            state = "DEGRADED"
            reason = "Overnight carry lacks a complete next-open stress map."
        elif not full_reprice:
            state = "DEGRADED"
            reason = "Only prepared/local stress values are available; full four-leg repricing is preferred."
        else:
            state = "CARRY_ELIGIBLE"
            reason = "Broker feasibility, event latency and mandatory next-open stress gates passed."

    return {
        "engine": "v2.1-candidate",
        "active": active,
        "mandatory": mandatory,
        "operational_state": state,
        "mechanical_reason": reason,
        "broker": {
            "status": broker_status,
            "auto_squareoff_warning": auto_warn,
        },
        "event_latency": {
            "max_severity_inside_untradeable_window": latency_sev,
        },
        "empirical_gap": emp,
        "next_open_stress": {
            "source": scen.get("source") if scen else None,
            "full_reprice": full_reprice,
            "same_state_open_pnl_points": same,
            "worst_1_0_straddle_pnl_points": worst_10,
            "worst_1_5_straddle_pnl_points": worst_15,
            "worst_2_0_straddle_pnl_points": worst_20,
            "ocr_1_5": ocr_15,
            "scenarios": stress,
        },
        "hard_failures": sorted(set(hard)),
        "warnings": list(dict.fromkeys(warnings)),
        "note": "Recent realized gaps are an empirical risk screen, not a forecast. Mandatory stress scenarios remain deterministic diagnostics; full-reprice large moves rather than extrapolating only with local gamma."
    }


def main():
    ap = argparse.ArgumentParser(description="Evaluate Engine v2.1 overnight butterfly carry diagnostics")
    ap.add_argument("--input", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    out = evaluate(load_json(args.input))
    print(json.dumps(out, indent=2 if args.pretty else None, sort_keys=True, allow_nan=False, default=lambda _: None))


if __name__ == "__main__":
    main()
