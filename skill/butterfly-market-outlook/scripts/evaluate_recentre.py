#!/usr/bin/env python3
"""Risk/carry diagnostic for deciding whether recentering is economically justified.

This helper deliberately does not infer real-world EV from an option-implied RND.
If both current and candidate contain scenario_expected_pnl_points, those values are
assumed to come from an explicitly supplied real-world scenario distribution.
"""
import argparse
import json
from pathlib import Path


def f(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def evaluate(x):
    cur = x.get("current", {}) or {}
    cand = x.get("candidate", {}) or {}
    s = f(x.get("atm_straddle")) or 0.0
    path_center = f(x.get("path_expected_center"))
    if path_center is None:
        path_center = f(cur.get("path_expected_center"))
    cost = f(x.get("transaction_cost_points")) or 0.0
    hours = f(x.get("time_to_expiry_hours"))
    regime = str(x.get("regime", "uncertain")).lower()
    health = str(x.get("data_health", "DEGRADED")).upper()

    c0, c1 = f(cur.get("center")), f(cand.get("center"))
    alignment_gain = None
    if path_center is not None and c0 is not None and c1 is not None and s > 0:
        alignment_gain = (abs(c0 - path_center) - abs(c1 - path_center)) / s

    t0 = f(cur.get("combined_tail_risk_score"))
    t1 = f(cand.get("combined_tail_risk_score"))
    tail_reduction = None
    if t0 is not None and t1 is not None and abs(t0) > 1e-12:
        tail_reduction = (t0 - t1) / abs(t0)

    carry = f(cand.get("same_state_carry_points"))
    carry_after = None if carry is None else carry - cost
    friction_share = None if carry is None or carry <= 0 else cost / carry

    ev0 = f(cur.get("scenario_expected_pnl_points"))
    ev1 = f(cand.get("scenario_expected_pnl_points"))
    scenario_edge = None if ev0 is None or ev1 is None else ev1 - ev0 - cost
    scenario_material = (
        scenario_edge is not None
        and scenario_edge >= max(2.0, 0.10 * max(cost, 0.0))
    )

    fail, warn = [], []
    if health in {"INVALID", "STALE"}:
        fail.append("data_health_not_sufficient_for_recenter")
    if regime in {"directional_up", "directional_down", "event_jump"}:
        fail.append("range_thesis_not_intact")
    if hours is not None and hours < 6:
        fail.append("too_little_time_to_reharvest_after_friction")
    if tail_reduction is not None and tail_reduction < -0.05:
        fail.append("new_fly_worsens_tail_risk")
    if friction_share is not None:
        if friction_share > 0.50:
            fail.append("friction_consumes_too_much_new_carry")
        elif friction_share > 0.35:
            warn.append("high_friction_share")
    if carry_after is not None and carry_after <= 0:
        fail.append("no_positive_same_state_carry_after_friction")
    if scenario_edge is not None and scenario_edge <= 0:
        fail.append("no_real_world_scenario_edge_after_friction")

    material_alignment = alignment_gain is not None and alignment_gain >= 0.25
    material_tail = tail_reduction is not None and tail_reduction >= 0.15
    if not material_alignment and not material_tail and not scenario_material:
        warn.append("improvement_not_material")

    if fail:
        gate = "FAIL"
    elif "improvement_not_material" in warn:
        gate = "WEAK"
    elif "high_friction_share" in warn and not scenario_material:
        gate = "WEAK"
    else:
        gate = "PASS"

    return {
        "gate": gate,
        "alignment_gain_straddles": alignment_gain,
        "tail_risk_reduction_fraction": tail_reduction,
        "candidate_gross_same_state_carry_points": carry,
        "transaction_cost_points": cost,
        "carry_after_friction_points": carry_after,
        "friction_share_of_gross_carry": friction_share,
        "scenario_edge_after_friction_points": scenario_edge,
        "scenario_edge_material": scenario_material,
        "scenario_edge_is_real_world_only_if_supplied": scenario_edge is not None,
        "fail_reasons": fail,
        "warnings": warn,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    x = json.loads(Path(args.input).read_text())
    print(json.dumps(evaluate(x), indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
