#!/usr/bin/env python3
"""Summarize closed butterfly episodes for calibration review.

Accepts JSONL or a JSON array. It measures outcomes; it never changes live thresholds.
"""
import argparse
import json
import math
from pathlib import Path


def f(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def avg(xs):
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    return sum(xs) / len(xs) if xs else None


def load(path):
    text = Path(path).read_text().strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def summarize(rows):
    pnl = [f(r.get("realized_pnl_points")) for r in rows]
    pnl2 = [x for x in pnl if x is not None]
    center_err = []
    rnd_brier = []
    physical_brier = []
    slippage_err = []
    giveback = []
    recenter_inc = []
    outside_rate = []
    for r in rows:
        actual = r.get("actual_expiry_or_exit_spot")
        pred_center = r.get("path_expected_center")
        if f(actual) is not None and f(pred_center) is not None:
            center_err.append(abs(f(actual) - f(pred_center)))
        outside = r.get("actual_outside_wings")
        if isinstance(outside, bool):
            y = 1.0 if outside else 0.0
            outside_rate.append(y)
            pr = f(r.get("entry_rnd_p_outside_wings"))
            if pr is not None:
                rnd_brier.append((pr - y) ** 2)
            pin = f(r.get("path_prob_inside_wings"))
            if pin is not None:
                pout = 1.0 - pin
                physical_brier.append((pout - y) ** 2)
        ae, ee = f(r.get("actual_slippage_points")), f(r.get("estimated_slippage_points"))
        if ae is not None and ee is not None:
            slippage_err.append(ae - ee)
        gb = f(r.get("max_profit_giveback_points"))
        if gb is not None:
            giveback.append(gb)
        ri = f(r.get("recenter_incremental_pnl_points"))
        if ri is not None:
            recenter_inc.append(ri)

    return {
        "episodes": len(rows),
        "average_realized_pnl_points": avg(pnl2),
        "win_rate": (sum(1 for x in pnl2 if x > 0) / len(pnl2)) if pnl2 else None,
        "average_path_center_absolute_error_points": avg(center_err),
        "actual_outside_wings_frequency": avg(outside_rate),
        "rnd_wing_mass_brier_descriptive_only": avg(rnd_brier),
        "real_world_path_probability_brier": avg(physical_brier),
        "average_slippage_estimation_error_points": avg(slippage_err),
        "average_profit_giveback_points": avg(giveback),
        "average_recenter_incremental_pnl_points_where_available": avg(recenter_inc),
        "note": "Do not auto-change live thresholds from this summary; require human review and a meaningful sample.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    rows = load(args.input)
    print(json.dumps(summarize(rows), indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
