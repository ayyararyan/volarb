#!/usr/bin/env python3
"""Analyze expiry payoff/P&L geometry for an option position.

Input is a JSON file containing spot, optional ATM IV/days_to_expiry, and option legs.
The script is intentionally dependency-free so it can be executed in a Skill runtime.
"""

import argparse
import json
import math
from pathlib import Path


def intrinsic(kind, strike, s):
    if kind == "call":
        return max(s - strike, 0.0)
    if kind == "put":
        return max(strike - s, 0.0)
    raise ValueError(f"Unknown option type: {kind}")


def payoff_per_unit(legs, s):
    total = 0.0
    for leg in legs:
        total += float(leg["qty"]) * intrinsic(leg["type"].lower(), float(leg["strike"]), s)
    return total


def pnl_currency(legs, s):
    if any("entry" not in leg for leg in legs):
        return None
    total = 0.0
    for leg in legs:
        qty = float(leg["qty"])
        strike = float(leg["strike"])
        entry = float(leg["entry"])
        mult = float(leg.get("multiplier", 1.0))
        total += qty * (intrinsic(leg["type"].lower(), strike, s) - entry) * mult
    return total


def net_entry_currency(legs):
    if any("entry" not in leg for leg in legs):
        return None
    return sum(float(x["qty"]) * float(x["entry"]) * float(x.get("multiplier", 1.0)) for x in legs)


def candidate_points(legs, spot):
    strikes = sorted({float(x["strike"]) for x in legs})
    hi_anchor = max(strikes + ([float(spot)] if spot is not None else []))
    hi = max(hi_anchor * 3.0, (strikes[-1] if strikes else 1.0) + 10000.0)
    return [0.0] + strikes + [hi]


def roots_piecewise(legs, points):
    if any("entry" not in leg for leg in legs):
        return []
    roots = []
    for a, b in zip(points[:-1], points[1:]):
        fa = pnl_currency(legs, a)
        fb = pnl_currency(legs, b)
        if fa is None or fb is None:
            continue
        if abs(fa) < 1e-9:
            roots.append(a)
        if abs(fb) < 1e-9:
            roots.append(b)
        if fa * fb < 0:
            # P&L is linear between adjacent strikes, so interpolation is exact.
            r = a + (0.0 - fa) * (b - a) / (fb - fa)
            roots.append(r)
    out = []
    for r in sorted(roots):
        if not out or abs(r - out[-1]) > 1e-6:
            out.append(r)
    return out


def describe_structure(legs):
    strikes = sorted({float(x["strike"]) for x in legs})
    by_strike = {}
    for leg in legs:
        k = float(leg["strike"])
        by_strike[k] = by_strike.get(k, 0.0) + float(leg["qty"])
    desc = {
        "strikes": strikes,
        "net_qty_by_strike": {str(k): by_strike[k] for k in strikes},
    }
    if len(strikes) == 3:
        desc["lower"] = strikes[0]
        desc["center"] = strikes[1]
        desc["upper"] = strikes[2]
        desc["lower_width"] = strikes[1] - strikes[0]
        desc["upper_width"] = strikes[2] - strikes[1]
        desc["symmetric_wings"] = abs(desc["lower_width"] - desc["upper_width"]) < 1e-9
    return desc


def analyze(data):
    legs = data.get("legs", [])
    if not legs:
        raise ValueError("Input must contain at least one option leg")

    for leg in legs:
        if "type" not in leg or "strike" not in leg or "qty" not in leg:
            raise ValueError("Each leg must include type, strike and qty")
        if leg["type"].lower() not in {"call", "put"}:
            raise ValueError("Option type must be call or put")

    spot = data.get("spot")
    spot = float(spot) if spot is not None else None
    points = candidate_points(legs, spot)
    structure = describe_structure(legs)

    result = {
        "underlying": data.get("underlying"),
        "spot": spot,
        "structure": structure,
        "net_entry_currency": net_entry_currency(legs),
    }

    if all("entry" in leg for leg in legs):
        vals = [(s, pnl_currency(legs, s)) for s in points]
        min_s, min_pnl = min(vals, key=lambda z: z[1])
        max_s, max_pnl = max(vals, key=lambda z: z[1])
        result.update({
            "expiry_break_evens": roots_piecewise(legs, points),
            "sampled_expiry_max_pnl_currency": max_pnl,
            "sampled_expiry_max_pnl_at": max_s,
            "sampled_expiry_min_pnl_currency": min_pnl,
            "sampled_expiry_min_pnl_at": min_s,
            "spot_expiry_pnl_if_expired_now_currency": pnl_currency(legs, spot) if spot is not None else None,
        })

    iv = data.get("atm_iv")
    dte = data.get("days_to_expiry")
    if spot is not None and iv is not None and dte is not None:
        iv = float(iv)
        dte = float(dte)
        em = spot * iv * math.sqrt(max(dte, 0.0) / 365.0)
        result["iv_expected_move_points_1sigma"] = em
        result["iv_expected_move_percent_1sigma"] = em / spot if spot else None
        for key in ("lower", "center", "upper"):
            if key in structure and em > 0:
                result[f"distance_spot_to_{key}_sigma"] = (structure[key] - spot) / em
        if result.get("expiry_break_evens") and em > 0:
            result["break_even_distances_sigma"] = [
                (x - spot) / em for x in result["expiry_break_evens"]
            ]

    if spot is not None:
        stress = {}
        for pct in (-0.015, -0.01, -0.005, 0.0, 0.005, 0.01, 0.015):
            s = spot * (1.0 + pct)
            row = {"underlying": s, "intrinsic_payoff_points": payoff_per_unit(legs, s)}
            p = pnl_currency(legs, s)
            if p is not None:
                row["expiry_pnl_currency"] = p
            stress[f"{pct:+.1%}"] = row
        result["spot_stress_grid"] = stress

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to JSON position file")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text())
    result = analyze(data)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
