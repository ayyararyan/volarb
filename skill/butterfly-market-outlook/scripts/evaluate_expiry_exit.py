#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_json(path):
    return json.loads(Path(path).read_text())


def worst_local_pnl(delta, gamma, move):
    vals = []
    for ds in (-move, move):
        vals.append(delta * ds + 0.5 * gamma * ds * ds)
    worst = min(vals)
    return {
        "minus_move_pnl": vals[0],
        "plus_move_pnl": vals[1],
        "worst_pnl": worst,
        "worst_loss": max(0.0, -worst),
    }


def ratio_or_none(num, den):
    if den is None or den <= 0:
        return None
    return num / den


def evaluate(x):
    required = [
        "center", "wing_width", "entry_credit", "close_cost", "spot",
        "atm_straddle", "net_delta", "net_gamma", "net_theta_per_day",
        "hours_to_expiry", "hours_to_next_review"
    ]
    missing = [k for k in required if k not in x]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))

    center = float(x["center"])
    wing_width = float(x["wing_width"])
    credit = float(x["entry_credit"])
    close_cost = float(x["close_cost"])
    spot = float(x["spot"])
    forward = float(x.get("forward", spot))
    straddle = float(x["atm_straddle"])
    delta = float(x["net_delta"])
    gamma = float(x["net_gamma"])
    theta_day = float(x["net_theta_per_day"])
    hours_to_expiry = float(x["hours_to_expiry"])
    hours_to_review = max(0.0, float(x["hours_to_next_review"]))

    if credit <= 0 or wing_width <= 0 or straddle <= 0:
        raise ValueError("entry_credit, wing_width and atm_straddle must be positive")

    lower_be = center - credit
    upper_be = center + credit
    nearest_be = min(abs(forward - lower_be), abs(upper_be - forward))
    be_buffer_ratio = nearest_be / straddle

    current_profit = credit - close_cost
    structural_max_profit = credit
    original_max_capture = current_profit / structural_max_profit
    max_loss = wing_width - credit

    # State-conditioned / no-move expiry economics.
    # For a symmetric short iron butterfly, expiry liability at an underlying
    # level x is min(|x-center|, wing_width). This is NOT the true maximum
    # profit still possible; it is the expiry result if the current forward
    # remains at approximately the same level through settlement.
    expiry_intrinsic_liability_at_forward = min(abs(forward - center), wing_width)
    no_move_expiry_profit = credit - expiry_intrinsic_liability_at_forward
    remaining_static_harvest = max(0.0, close_cost - expiry_intrinsic_liability_at_forward)
    dynamic_harvest_saturation = ratio_or_none(current_profit, no_move_expiry_profit)

    stress_half = worst_local_pnl(delta, gamma, 0.5 * straddle)
    stress_full = worst_local_pnl(delta, gamma, 1.0 * straddle)

    theta_to_review = max(0.0, theta_day) * min(hours_to_review, hours_to_expiry) / 24.0

    half_stress = stress_half["worst_loss"]
    full_stress = stress_full["worst_loss"]
    harvest_to_half_stress = ratio_or_none(remaining_static_harvest, half_stress)
    harvest_to_full_stress = ratio_or_none(remaining_static_harvest, full_stress)

    recent_straddle = x.get("reference_atm_straddle")
    straddle_expansion = None
    if recent_straddle is not None and float(recent_straddle) > 0:
        straddle_expansion = straddle / float(recent_straddle) - 1.0

    dynamic_defined = dynamic_harvest_saturation is not None
    flags = {
        "state_conditioned_profit_nonpositive": no_move_expiry_profit <= 0,
        "dynamic_monitor_zone": dynamic_defined and dynamic_harvest_saturation >= 0.70,
        "dynamic_strong_exit_zone": dynamic_defined and dynamic_harvest_saturation >= 0.80,
        "dynamic_default_exit": dynamic_defined and dynamic_harvest_saturation >= 0.85,
        "tight_be_buffer": be_buffer_ratio < 0.75,
        "hard_be_warning": be_buffer_ratio < 0.50,
        "half_straddle_stress_exceeds_theta_to_review": half_stress >= theta_to_review if theta_to_review > 0 else half_stress > 0,
        "half_straddle_stress_exceeds_remaining_static_harvest": half_stress >= remaining_static_harvest if remaining_static_harvest > 0 else half_stress > 0,
        "full_straddle_stress_exceeds_remaining_static_harvest": full_stress >= remaining_static_harvest if remaining_static_harvest > 0 else full_stress > 0,
        "full_straddle_stress_exceeds_current_profit": full_stress >= max(0.0, current_profit),
        "material_straddle_expansion": (straddle_expansion is not None and straddle_expansion >= 0.20),
        "expiry_day_like": hours_to_expiry <= 8.0,
    }

    if flags["state_conditioned_profit_nonpositive"]:
        mechanical_state = "EXIT_BIAS"
        mechanical_reason = "At the current forward, a no-move expiry would not be profitable."
    elif flags["dynamic_default_exit"]:
        mechanical_state = "EXIT_BIAS"
        mechanical_reason = "At least 85% of the current state-conditioned no-move expiry profit has already been captured."
    elif flags["hard_be_warning"]:
        mechanical_state = "EXIT_BIAS"
        mechanical_reason = "Nearest break-even is inside half of the current ATM straddle."
    elif flags["dynamic_strong_exit_zone"] and (harvest_to_half_stress is None or harvest_to_half_stress <= 1.5):
        mechanical_state = "EXIT_BIAS"
        mechanical_reason = "Dynamic harvest saturation is at least 80% and the remaining static harvest is small relative to local gamma stress."
    elif flags["dynamic_monitor_zone"] and flags["half_straddle_stress_exceeds_remaining_static_harvest"]:
        mechanical_state = "EXIT_BIAS"
        mechanical_reason = "At least 70% of the state-conditioned profit is captured and half-straddle gamma stress exceeds the remaining static harvest."
    elif flags["tight_be_buffer"] or flags["dynamic_strong_exit_zone"] or flags["dynamic_monitor_zone"]:
        mechanical_state = "TIGHT_MONITOR"
        mechanical_reason = "Near-expiry dynamic harvest saturation or break-even geometry requires a short review interval."
    else:
        mechanical_state = "HOLD_ELIGIBLE"
        mechanical_reason = "No mechanical dynamic-harvest expiry-exit threshold is breached."

    return {
        "profit": {
            "structural_max_profit_points": structural_max_profit,
            "current_profit_points": current_profit,
            "original_max_capture_fraction": original_max_capture,
            "max_loss_points": max_loss,
        },
        "state_conditioned_harvest": {
            "reference_forward": forward,
            "expiry_intrinsic_liability_at_forward_points": expiry_intrinsic_liability_at_forward,
            "no_move_expiry_profit_points": no_move_expiry_profit,
            "dynamic_harvest_saturation_fraction": dynamic_harvest_saturation,
            "remaining_static_harvest_points": remaining_static_harvest,
            "note": "The no-move expiry profit is a state-conditioned reference, not the true maximum profit still possible if the underlying later returns to the body."
        },
        "geometry": {
            "lower_break_even": lower_be,
            "upper_break_even": upper_be,
            "nearest_break_even_distance_from_forward": nearest_be,
            "be_buffer_to_straddle": be_buffer_ratio,
        },
        "carry_vs_gamma": {
            "theta_to_next_review_points_approx": theta_to_review,
            "half_straddle_stress": stress_half,
            "full_straddle_stress": stress_full,
            "remaining_harvest_to_half_straddle_stress": harvest_to_half_stress,
            "remaining_harvest_to_full_straddle_stress": harvest_to_full_stress,
        },
        "volatility": {
            "atm_straddle": straddle,
            "reference_atm_straddle": recent_straddle,
            "straddle_expansion_fraction": straddle_expansion,
        },
        "flags": flags,
        "mechanical_state": mechanical_state,
        "mechanical_reason": mechanical_reason,
        "note": "Combine these diagnostics with live surface alignment, skew, directional follow-through, news and liquidity before choosing HOLD/RECENTRE/SQUARE OFF."
    }


def main():
    ap = argparse.ArgumentParser(description="Evaluate dynamic near-expiry butterfly exit diagnostics")
    ap.add_argument("--input", required=True, help="Path to JSON snapshot")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    result = evaluate(load_json(args.input))
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
