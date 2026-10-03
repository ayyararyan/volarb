#!/usr/bin/env python3
"""Summarize closed butterfly episodes for calibration review.

Accepts an explicitly supplied private CSV, JSONL, or JSON-array input path.
Personal financial inputs must remain outside the public source checkout.
It measures outcomes; it never changes live thresholds.

CSV rows are mapped to episode fields: realized points are
``entry_credit_points - exit_cost_points`` when both are present, otherwise
``realized_pnl_inr / quantity``. Rows without a numeric realized P&L are
counted but excluded from averages.
"""
import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path


def f(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def avg(xs):
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    return sum(xs) / len(xs) if xs else None


def _minutes_between(opened, closed):
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        a = datetime.strptime(str(opened).replace(" IST", "").strip(), fmt)
        b = datetime.strptime(str(closed).replace(" IST", "").strip(), fmt)
    except ValueError:
        return None
    return (b - a).total_seconds() / 60.0


def csv_row_to_episode(row):
    credit, cost, qty, inr = (f(row.get(k)) for k in ("entry_credit_points", "exit_cost_points", "quantity", "realized_pnl_inr"))
    points = None
    if credit is not None and cost is not None:
        points = credit - cost
    elif inr is not None and qty:
        points = inr / qty
    return {
        "trade_id": row.get("trade_id"),
        "instrument": row.get("instrument"),
        "strategy": row.get("strategy"),
        "status": row.get("status"),
        "provenance": row.get("provenance"),
        "realized_pnl_points": points,
        "realized_pnl_inr": inr,
        "quantity": qty,
        "hold_minutes": _minutes_between(row.get("opened_at_ist"), row.get("closed_at_ist")),
        "broker_confirmed": str(row.get("provenance", "")).lower().startswith("dhan"),
    }


def load(path):
    p = Path(path)
    text = p.read_text().strip()
    if not text:
        return []
    if p.suffix.lower() == ".csv" or text.startswith("trade_id,"):
        return [csv_row_to_episode(r) for r in csv.DictReader(text.splitlines())]
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

    inr = [f(r.get("realized_pnl_inr")) for r in rows]
    inr2 = [x for x in inr if x is not None]
    wins_inr = [x for x in inr2 if x > 0]
    losses_inr = [x for x in inr2 if x < 0]
    confirmed = [r for r in rows if r.get("broker_confirmed")]
    confirmed_inr = [f(r.get("realized_pnl_inr")) for r in confirmed]
    confirmed_inr = [x for x in confirmed_inr if x is not None]
    by_instrument = {}
    for r in rows:
        key = r.get("instrument") or "UNKNOWN"
        v = f(r.get("realized_pnl_inr"))
        if v is not None:
            by_instrument.setdefault(key, []).append(v)
    hold = [f(r.get("hold_minutes")) for r in rows]

    return {
        "episodes": len(rows),
        "average_realized_pnl_points": avg(pnl2),
        "win_rate": (sum(1 for x in pnl2 if x > 0) / len(pnl2)) if pnl2 else None,
        "total_gross_realized_inr": sum(inr2) if inr2 else None,
        "total_gross_realized_inr_broker_confirmed_only": sum(confirmed_inr) if confirmed_inr else None,
        "average_win_inr": avg(wins_inr),
        "average_loss_inr": avg(losses_inr),
        "loss_to_win_ratio": (abs(avg(losses_inr)) / avg(wins_inr)) if wins_inr and losses_inr else None,
        "largest_loss_inr": min(losses_inr) if losses_inr else None,
        "gross_by_instrument_inr": {k: sum(v) for k, v in sorted(by_instrument.items())},
        "average_hold_minutes": avg(hold),
        "charges_note": "All INR figures are gross before brokerage, exchange charges, GST and STT; net is unknown until reconciled in the local ledger.",
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
