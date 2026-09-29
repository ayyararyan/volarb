"""Gamma-theta efficiency and distribution-robust tail selection for wide flies.

Reads the current-only selector packet (chain with per-leg calibrated IVs,
forward, year fraction, units) and the selector's reproduced rows CSV.
For every eligible candidate in a declared near-forward band it computes:

* gamma-theta efficiency: the one-day move that cancels one day of theta,
  ``sqrt(2*theta/|gamma|)``, divided by the one-day move the current ATM IV
  implies. Black76 makes this ratio 1 for a single ATM option, so the ratio
  isolates how the wing skew taxes carry; it is nearly width-invariant.
* terminal loss VaR/ES under an AMBIGUITY SET of distributions built only
  from current observations plus explicit stress families (flat ATM
  lognormal, chain-smile density via Breeden-Litzenberger, IV x1.5, IV x2,
  Student-t nu=3 with matched variance, Student-t with IV x1.5).
  The robust tail is the worst ES/VaR across the valid members.
* selection under a declared rule: maximise theta per rupee of robust ES99
  (carry per unit of worst-case tail) subject to the wide floor. Max loss is
  reported as the cap only; it is never the ranking denominator and it is
  never called an expected loss.

Nothing here is a physical forecast: every member of the ambiguity set is a
current-input model or a stress. Stdlib + numpy only; no broker calls; no
ledger writes.
"""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np

NORMAL = NormalDist()
ALPHAS = (0.95, 0.99)
VERSION = "robust-tail-selection/1.0"


# ---------------------------------------------------------------- pricing --
def black(forward, strike, sigma, years, kind):
    sign = 1.0 if kind == "CE" else -1.0
    sd = sigma * math.sqrt(years)
    d1 = math.log(forward / strike) / sd + sd / 2
    d2 = d1 - sd
    return sign * (forward * NORMAL.cdf(sign * d1) - strike * NORMAL.cdf(sign * d2))


def black_vec(forward, strikes, sigmas, years):
    """Vectorised Black76 call prices (DF=1)."""
    sd = sigmas * math.sqrt(years)
    d1 = np.log(forward / strikes) / sd + sd / 2
    d2 = d1 - sd
    cdf = np.vectorize(NORMAL.cdf)
    return forward * cdf(d1) - strikes * cdf(d2)


# ------------------------------------------------------------ tail measures --
def var_es(losses, weights, alpha):
    """Weighted VaR/ES of nonnegative losses with fractional boundary atom.

    losses: (n_candidates, n_nodes); weights: (n_nodes,) summing to one.
    """
    order = np.argsort(losses, axis=1)
    sorted_losses = np.take_along_axis(losses, order, axis=1)
    sorted_weights = weights[order]
    cum = np.cumsum(sorted_weights, axis=1)
    idx = np.argmax(cum >= alpha - 1e-12, axis=1)
    var = sorted_losses[np.arange(len(losses)), idx]
    tail_mass = 1.0 - alpha
    beyond = np.where(np.arange(losses.shape[1])[None, :] > idx[:, None], sorted_weights, 0.0)
    prev_cum = np.where(idx > 0, cum[np.arange(len(losses)), np.maximum(idx - 1, 0)], 0.0)
    atom = np.maximum(cum[np.arange(len(losses)), idx] - np.maximum(prev_cum, alpha), 0.0)
    es = (np.sum(beyond * sorted_losses, axis=1) + atom * var) / tail_mass
    return var, es


def terminal_pnl(units, credit_points, centre, put_width, call_width, spots):
    down = np.minimum(np.maximum(centre - spots, 0.0), put_width)
    up = np.minimum(np.maximum(spots - centre, 0.0), call_width)
    return units * (credit_points - down - up)


# ----------------------------------------------------------- distributions --
def quantile_grid(nodes):
    return (np.arange(nodes) + 0.5) / nodes


def lognormal_nodes(forward, sigma, years, nodes):
    z = np.array([NORMAL.inv_cdf(u) for u in quantile_grid(nodes)])
    sd = sigma * math.sqrt(years)
    spots = forward * np.exp(-0.5 * sd * sd + sd * z)
    return spots, np.full(nodes, 1.0 / nodes)


def t3_cdf(t):
    return 0.5 + (math.atan(t / math.sqrt(3)) + math.sqrt(3) * t / (3 + t * t)) / math.pi


def t3_inv_cdf(u):
    lo, hi = -1e6, 1e6
    for _ in range(200):
        mid = (lo + hi) / 2
        if t3_cdf(mid) < u:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def student_t3_nodes(forward, sigma, years, nodes):
    """Log-return with Student-t(3) shape, variance sigma^2*T, mean fixed so E[S]=F."""
    t = np.array([t3_inv_cdf(u) for u in quantile_grid(nodes)])
    scale = sigma * math.sqrt(years) / math.sqrt(3.0)  # Var(t3) = 3
    raw = np.exp(scale * t)
    weights = np.full(nodes, 1.0 / nodes)
    spots = forward * raw / np.sum(weights * raw)
    return spots, weights


def fit_smile(chain, forward, years, max_abs_x=0.12):
    """Weighted quadratic IV(x) in x=ln(K/F) on OTM legs, flat beyond band."""
    xs, ivs, ws = [], [], []
    for leg in chain:
        strike, kind, iv = float(leg["strike"]), leg["type"], float(leg["iv"])
        price = float(leg.get("valuation_price", 0.0))
        otm = (kind == "PE" and strike < forward) or (kind == "CE" and strike > forward)
        if not otm or iv <= 0 or price < 2.0:
            continue
        x = math.log(strike / forward)
        if abs(x) > max_abs_x:
            continue
        xs.append(x)
        ivs.append(iv)
        ws.append(math.sqrt(price))
    if len(xs) < 8:
        raise ValueError("SMILE_FIT_INSUFFICIENT_OTM_LEGS")
    x, y, w = np.array(xs), np.array(ivs), np.array(ws)
    a = np.vstack([np.ones_like(x), x, x * x]).T * w[:, None]
    coef, *_ = np.linalg.lstsq(a, y * w, rcond=None)
    fitted = coef[0] + coef[1] * x + coef[2] * x * x
    resid = y - fitted
    band = (float(min(x)), float(max(x)))

    def quad(xq):
        return coef[0] + coef[1] * xq + coef[2] * xq * xq

    def slope(xq):
        return coef[1] + 2.0 * coef[2] * xq

    def sigma_of(xq):
        """Quadratic inside the observed band, C1 tangent extrapolation outside.

        A flat clamp at the band edge creates a slope kink in total variance and
        hence a negative Breeden-Litzenberger density; the tangent keeps the
        first derivative continuous. The tangent slope is capped at the Lee
        moment bound for total variance so wings cannot explode.
        """
        xq = np.asarray(xq, dtype=float)
        out = quad(np.clip(xq, band[0], band[1]))
        for edge, side in ((band[0], xq < band[0]), (band[1], xq > band[1])):
            if np.any(side):
                s_edge, m = quad(edge), slope(edge)
                max_slope = math.sqrt(2.0 / max(years, 1e-9)) / 2.0  # d(sigma)/dx bound from w' <= 2
                m = float(np.clip(m, -max_slope, max_slope))
                out = np.where(side, s_edge + m * (xq - edge), out)
        return np.maximum(out, 0.02)

    return {"coef": coef.tolist(), "n": len(xs), "rmse": float(np.sqrt(np.mean(resid ** 2))),
            "max_abs_resid": float(np.max(np.abs(resid))), "x_band": [band[0], band[1]],
            "extrapolation": "C1 tangent beyond observed band, slope capped", "sigma_of": sigma_of}


def smile_density_nodes(forward, years, smile, grid_points=6001, span_sd=10.0):
    """Breeden-Litzenberger density from the fitted smile; DF=1."""
    sd_ref = smile["sigma_of"](np.array([0.0]))[0] * math.sqrt(years)
    x = np.linspace(-span_sd * sd_ref, span_sd * sd_ref, grid_points)
    strikes = forward * np.exp(x)
    calls = black_vec(forward, strikes, smile["sigma_of"](x), years)
    dk = np.diff(strikes)
    first = np.diff(calls) / dk
    second = np.diff(first) / (0.5 * (dk[1:] + dk[:-1]))
    mid_strikes = strikes[1:-1]
    density = second
    negative_mass = float(np.sum(np.minimum(density, 0.0) * 0.5 * (dk[1:] + dk[:-1])))
    density = np.maximum(density, 0.0)
    weights = density * 0.5 * (dk[1:] + dk[:-1])
    total = float(np.sum(weights))
    weights = weights / total
    mean = float(np.sum(weights * mid_strikes))
    diagnostics = {"total_mass_before_normalisation": total, "clipped_negative_mass": negative_mass,
                   "mean_over_forward_minus_one": mean / forward - 1.0, "grid_points": grid_points}
    valid = abs(total - 1.0) < 0.02 and abs(negative_mass) < 0.01 and abs(mean / forward - 1.0) < 0.005
    return mid_strikes, weights, diagnostics, valid


def build_ambiguity_set(forward, years, atm_iv, chain, nodes):
    members = []
    members.append({"id": "LN_ATM", "family": "lognormal", "sigma": atm_iv, "stress": None,
                    "nodes": lognormal_nodes(forward, atm_iv, years, nodes), "valid": True,
                    "note": "flat current ATM IV, pricing measure Q proxy"})
    try:
        smile = fit_smile(chain, forward, years)
        spots, weights, diag, valid = smile_density_nodes(forward, years, smile)
        members.append({"id": "SMILE_BL", "family": "breeden_litzenberger", "sigma": None, "stress": None,
                        "nodes": (spots, weights), "valid": valid,
                        "note": "current chain smile density; DF=1; clipped negatives disclosed",
                        "fit": {k: v for k, v in smile.items() if k != "sigma_of"}, "density": diag})
    except ValueError as exc:
        members.append({"id": "SMILE_BL", "family": "breeden_litzenberger", "valid": False, "nodes": None,
                        "note": str(exc)})
    for mult in (1.5, 2.0):
        members.append({"id": f"LN_x{mult}", "family": "lognormal", "sigma": atm_iv * mult, "stress": mult,
                        "nodes": lognormal_nodes(forward, atm_iv * mult, years, nodes), "valid": True,
                        "note": "IV-level stress, not a forecast"})
    members.append({"id": "T3_ATM", "family": "student_t3", "sigma": atm_iv, "stress": None,
                    "nodes": student_t3_nodes(forward, atm_iv, years, nodes), "valid": True,
                    "note": "fat-tail shape stress with matched variance and E[S]=F"})
    members.append({"id": "T3_x1.5", "family": "student_t3", "sigma": atm_iv * 1.5, "stress": 1.5,
                    "nodes": student_t3_nodes(forward, atm_iv * 1.5, years, nodes), "valid": True,
                    "note": "fat-tail shape plus IV-level stress"})
    return members


# ------------------------------------------------------------------ inputs --
def load_rows(path, forward, band, max_wing):
    rows = []
    with open(path) as handle:
        for row in csv.DictReader(handle):
            if row["eligible"] != "True":
                continue
            centre = float(row["centre"])
            put_width, call_width = float(row["put_width"]), float(row["call_width"])
            if abs(centre - forward) > band or max(put_width, call_width) > max_wing:
                continue
            rows.append({
                "id": row["id"], "centre": centre, "lower_put": float(row["lower_put"]),
                "upper_call": float(row["upper_call"]), "put_width": put_width, "call_width": call_width,
                "units": int(float(row["units"])), "credit_points": float(row["entry_credit_points"]),
                "credit_inr": float(row["entry_credit_inr"]), "max_loss_inr": float(row["max_loss_gross_inr"]),
                "theta_inr_per_day": float(row["theta"]), "adverse_gamma_lot": float(row["adverse_gamma"]),
                "delta_lot": float(row["delta"]), "wing_valuation_points": float(row["wing_valuation_points"]),
                "shape_flags": row.get("shape_flags", ""),
            })
    if not rows:
        raise ValueError("No eligible rows inside the declared band")
    return rows


def atm_iv_from_chain(chain, forward):
    by_strike = {}
    for leg in chain:
        by_strike.setdefault(float(leg["strike"]), {})[leg["type"]] = float(leg["iv"])
    strikes = sorted(by_strike)
    below = max((k for k in strikes if k <= forward), default=None)
    above = min((k for k in strikes if k >= forward), default=None)
    picks = []
    for k in {below, above} - {None}:
        picks.extend(v for v in by_strike[k].values() if v > 0)
    if not picks:
        raise ValueError("ATM IV unavailable from chain")
    return sum(picks) / len(picks), [below, above]


# ---------------------------------------------------------------- analysis --
def analyse(packet_path, rows_path, band, max_wing, nodes, min_wing_pct, strict_wing_pct):
    packet = json.loads(Path(packet_path).read_text())
    group = packet["groups"][0]
    dist = group["distribution"]
    forward, years, units = float(dist["forward"]), float(dist["years"]), int(group["units"])
    spot_ref = float(packet["policy"]["spot_reference"])
    chain = group["chain"]
    atm_iv, atm_strikes = atm_iv_from_chain(chain, forward)
    rows = load_rows(rows_path, forward, band, max_wing)
    members = build_ambiguity_set(forward, years, atm_iv, chain, nodes)
    implied_daily_move = forward * atm_iv / math.sqrt(365.0)

    n = len(rows)
    centre = np.array([r["centre"] for r in rows])
    put_w = np.array([r["put_width"] for r in rows])
    call_w = np.array([r["call_width"] for r in rows])
    credit = np.array([r["credit_points"] for r in rows])
    theta = np.array([r["theta_inr_per_day"] for r in rows])
    gamma = np.array([r["adverse_gamma_lot"] for r in rows])
    max_loss = np.array([r["max_loss_inr"] for r in rows])

    be_move = np.sqrt(np.where(gamma > 0, 2.0 * theta / np.where(gamma > 0, gamma, 1.0), np.nan))
    efficiency = be_move / implied_daily_move

    per_member = {}
    robust = {a: {"var": np.zeros(n), "es": np.zeros(n)} for a in ALPHAS}
    for member in members:
        if not member.get("valid") or member.get("nodes") is None:
            per_member[member["id"]] = {"valid": False, "note": member["note"],
                                        **{k: member[k] for k in ("fit", "density") if k in member}}
            continue
        spots, weights = member["nodes"]
        result = {"valid": True, "note": member["note"], "n_nodes": int(len(spots)),
                  "mean_spot_over_forward": float(np.sum(weights * spots) / forward)}
        for key in ("fit", "density", "sigma", "stress"):
            if key in member:
                result[key] = member[key]
        chunk = 512
        var_out = {a: np.zeros(n) for a in ALPHAS}
        es_out = {a: np.zeros(n) for a in ALPHAS}
        epnl = np.zeros(n)
        for start in range(0, n, chunk):
            sl = slice(start, start + chunk)
            pnl = terminal_pnl(units, credit[sl, None], centre[sl, None], put_w[sl, None], call_w[sl, None], spots[None, :])
            losses = np.maximum(-pnl, 0.0)
            epnl[sl] = pnl @ weights
            for a in ALPHAS:
                v, e = var_es(losses, weights, a)
                var_out[a][sl], es_out[a][sl] = v, e
        for a in ALPHAS:
            robust[a]["var"] = np.maximum(robust[a]["var"], var_out[a])
            robust[a]["es"] = np.maximum(robust[a]["es"], es_out[a])
        result["metrics"] = {"var": var_out, "es": es_out, "expected_pnl_model": epnl}
        per_member[member["id"]] = result

    valid_ids = [m["id"] for m in members if m.get("valid") and m.get("nodes") is not None]
    robust_es99 = robust[0.99]["es"]
    carry_per_tail = np.where(robust_es99 > 0, theta / np.where(robust_es99 > 0, robust_es99, 1.0), np.nan)

    out_rows = []
    for i, r in enumerate(rows):
        entry = dict(r)
        entry.update({
            "breakeven_daily_move_points": float(be_move[i]),
            "gamma_theta_efficiency": float(efficiency[i]),
            "robust": {str(a): {"var": float(robust[a]["var"][i]), "es": float(robust[a]["es"][i])} for a in ALPHAS},
            "robust_es99_over_max_loss": float(robust_es99[i] / max_loss[i]) if max_loss[i] > 0 else None,
            "theta_per_robust_es99": float(carry_per_tail[i]),
            "per_model": {mid: {str(a): {"var": float(per_member[mid]["metrics"]["var"][a][i]),
                                         "es": float(per_member[mid]["metrics"]["es"][a][i])} for a in ALPHAS}
                          | {"expected_pnl_model": float(per_member[mid]["metrics"]["expected_pnl_model"][i])}
                          for mid in valid_ids},
        })
        out_rows.append(entry)

    def floor_points(pct):
        return math.ceil(spot_ref * pct / 100.0 / 100.0) * 100.0

    selections = {}
    for label, pct in (("declared_floor", min_wing_pct), ("strict_floor", strict_wing_pct)):
        floor = floor_points(pct)
        eligible = [e for e in out_rows if min(e["put_width"], e["call_width"]) >= floor and not e["shape_flags"]]
        neutral = [e for e in eligible if abs(e["centre"] - forward) <= 100.0]
        pick = max(eligible, key=lambda e: e["theta_per_robust_es99"]) if eligible else None
        pick_neutral = max(neutral, key=lambda e: e["theta_per_robust_es99"]) if neutral else None
        selections[label] = {"wing_floor_points": floor, "wing_floor_pct": pct, "candidates": len(eligible),
                             "best_theta_per_robust_es99": pick["id"] if pick else None,
                             "best_neutral_centre_within_100_of_forward": pick_neutral["id"] if pick_neutral else None}

    # fixed-lot marginal ladder at the neutral centre nearest the forward
    ladder = {}
    if selections["declared_floor"]["best_neutral_centre_within_100_of_forward"]:
        best = next(e for e in out_rows if e["id"] == selections["declared_floor"]["best_neutral_centre_within_100_of_forward"])
        sym = sorted((e for e in out_rows if e["centre"] == best["centre"] and e["put_width"] == e["call_width"]
                      and e["put_width"] >= selections["declared_floor"]["wing_floor_points"]), key=lambda e: e["put_width"])
        horizon_days = float(group["carry_horizon_days"])
        steps = []
        for prev, cur in zip(sym, sym[1:]):
            d_theta_h = (cur["theta_inr_per_day"] - prev["theta_inr_per_day"]) * horizon_days
            d_es = cur["robust"]["0.99"]["es"] - prev["robust"]["0.99"]["es"]
            steps.append({"from_width": prev["put_width"], "to_width": cur["put_width"],
                          "extra_frozen_theta_over_horizon_inr": d_theta_h, "extra_robust_es99_inr": d_es,
                          "lambda_breakeven": (d_theta_h / d_es) if d_es > 0 else None,
                          "note": "widening pays only if the holder values 1 rupee of worst-case ES99 at less than lambda_breakeven rupees of frozen carry"})
        ladder = {"centre": best["centre"], "horizon_days": horizon_days, "steps": steps,
                  "widths": [{"width": e["put_width"], "theta_inr_per_day": e["theta_inr_per_day"],
                              "robust_es99": e["robust"]["0.99"]["es"], "max_loss_inr": e["max_loss_inr"],
                              "theta_per_robust_es99": e["theta_per_robust_es99"],
                              "gamma_theta_efficiency": e["gamma_theta_efficiency"]} for e in sym]}

    return {
        "engine": VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "inputs": {"packet": str(packet_path), "rows_csv": str(rows_path), "group": group["id"],
                   "forward": forward, "years": years, "units": units, "spot_reference": spot_ref,
                   "atm_iv_from_chain": atm_iv, "atm_strikes_used": atm_strikes,
                   "implied_daily_move_points": implied_daily_move, "band_points": band, "max_wing_points": max_wing,
                   "nodes": nodes, "quote_status": group["quote_status"], "pricing_basis": group["pricing_basis"]},
        "ambiguity_set": {mid: {k: v for k, v in per_member[mid].items() if k != "metrics"} for mid in per_member},
        "robust_definition": "worst ES/VaR across valid ambiguity-set members; a stress envelope from current inputs, not a physical expectation",
        "selection_rule": "maximise theta_inr_per_day / robust_es99 subject to wide floor; max loss is a cap only; ties/neutrality reported separately",
        "selections": selections,
        "fixed_lot_ladder": ladder,
        "rows": out_rows,
        "limitations": [
            "Closed-market LTP valuation marks; no bid/ask or depth; not executable entry prices.",
            "Every ambiguity-set member is a current-input model or explicit stress; none is a real-world probability forecast.",
            "Terminal-only payoff; earlier-exit risk needs full common-horizon repricing.",
            "Theta is a frozen local derivative; theta*H is a carry index, not earned decay or expected profit.",
            "The declared ratio rule is a preference: it assumes position size can scale to a tail budget. The fixed-lot ladder gives the break-even lambda per widening step instead.",
        ],
    }


def print_summary(report, top=12):
    rows = sorted(report["rows"], key=lambda e: -e["theta_per_robust_es99"])
    print(f"{report['engine']}  forward={report['inputs']['forward']:.0f}  ATM IV={report['inputs']['atm_iv_from_chain']:.4f}  "
          f"implied 1d move={report['inputs']['implied_daily_move_points']:.0f} pts  candidates={len(rows)}")
    for mid, m in report["ambiguity_set"].items():
        print(f"  {mid:9s} valid={m.get('valid')} {m.get('note','')}" + (f" density={m['density']}" if 'density' in m else ""))
    print(f"\n{'centre':>6} {'put':>6} {'call':>6} {'credit':>7} {'maxloss':>8} {'rES99':>8} {'rES/max':>7} {'theta':>6} {'eff':>5} {'th/rES99':>9}")
    for e in rows[:top]:
        print(f"{e['centre']:>6.0f} {e['lower_put']:>6.0f} {e['upper_call']:>6.0f} {e['credit_inr']:>7.0f} {e['max_loss_inr']:>8.0f} "
              f"{e['robust']['0.99']['es']:>8.0f} {e['robust_es99_over_max_loss']:>7.2f} {e['theta_inr_per_day']:>6.0f} "
              f"{e['gamma_theta_efficiency']:>5.2f} {e['theta_per_robust_es99']:>9.4f}")
    print("\nselections:", json.dumps(report["selections"], indent=1))
    if report["fixed_lot_ladder"]:
        print("\nfixed-lot ladder at centre", report["fixed_lot_ladder"]["centre"])
        for w in report["fixed_lot_ladder"]["widths"]:
            print(f"  width {w['width']:>5.0f}: theta {w['theta_inr_per_day']:>6.0f}/d  robustES99 {w['robust_es99']:>7.0f}  "
                  f"maxloss {w['max_loss_inr']:>7.0f}  eff {w['gamma_theta_efficiency']:.2f}  th/rES {w['theta_per_robust_es99']:.4f}")
        for s in report["fixed_lot_ladder"]["steps"]:
            lam = s["lambda_breakeven"]
            print(f"  {s['from_width']:.0f}->{s['to_width']:.0f}: +theta*H {s['extra_frozen_theta_over_horizon_inr']:>7.0f}  "
                  f"+robustES99 {s['extra_robust_es99_inr']:>7.0f}  lambda_be {lam if lam is None else round(lam,3)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--packet", required=True)
    parser.add_argument("--rows", required=True, help="CSV written by wide_butterfly_selector.py --csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--band", type=float, default=600.0, help="max |centre - forward| in points")
    parser.add_argument("--max-wing", type=float, default=3600.0)
    parser.add_argument("--nodes", type=int, default=4096)
    parser.add_argument("--min-wing-pct", type=float, default=2.0)
    parser.add_argument("--strict-wing-pct", type=float, default=3.0)
    args = parser.parse_args()
    report = analyse(Path(args.packet), Path(args.rows), args.band, args.max_wing, args.nodes,
                     args.min_wing_pct, args.strict_wing_pct)
    Path(args.output).write_text(json.dumps(report, indent=1, default=float))
    print_summary(report)
    print(f"\nwritten {args.output}")


if __name__ == "__main__":
    main()
