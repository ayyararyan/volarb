"""Read-only, exhaustive wide short-iron-butterfly research (stdlib only).

No broker calls, fitted distribution, ledger writes or automatic trade approval.
Input JSON has ``policy.min_wing_points`` and ``groups``. Each group freezes one
underlying, expiry, unit quantity, quote snapshot and decision horizon. Supply a
chain plus centres, or explicit candidates with four signed-unit legs. All wide
combinations are retained, including rejection reasons. Narrow combinations are
recorded as exact non-overlapping per-centre exclusions, not sampled candidates.
Current diagnostic groups may explicitly use ``LTP_VALUATION_ONLY`` with
``REFERENCE`` status and per-leg ``valuation_price``; no bid/ask or depth is
fabricated, and those results are never labelled executable.

Scenario probabilities must be supplied, not inferred from Greeks or payoff
geometry. ``terminal_spot`` scenarios contain spot/weight at expiry;
``liquidation_matrix`` scenarios contain full executable-side option books by
leg id at the common future horizon. Physical validation is an external gate,
never something that this numerical engine establishes by running successfully.
"""

import argparse
from bisect import bisect_left, bisect_right
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

VERSION = "wide-butterfly-selector/2.1"
ALPHAS = (0.95, 0.99)
LAMBDAS = (0, 0.25, 0.5, 1, 2)
GREEKS = ("delta", "gamma", "theta", "vega")


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def timestamp(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return result


def positive_loss_var_es(pnls, weights, alpha):
    """Weighted VaR and ES of max(-PnL, 0), including fractional tail atoms."""
    if not 0 < alpha < 1 or len(pnls) != len(weights) or not pnls:
        raise ValueError("invalid loss sample/alpha")
    if not all(number(x) for x in pnls) or not all(number(w) and w >= 0 for w in weights):
        raise ValueError("nonfinite values or negative weights")
    total = math.fsum(weights)
    if abs(total - 1) > 1e-8:
        raise ValueError("probability weights must sum to one")
    ordered = sorted((max(-p, 0.0), w / total) for p, w in zip(pnls, weights) if w > 0)
    cumulative, var = 0.0, ordered[-1][0]
    for loss, weight in ordered:
        cumulative += weight
        if cumulative + 1e-14 >= alpha:
            var = loss
            break
    remaining, tail_sum = 1 - alpha, 0.0
    for loss, weight in reversed(ordered):
        take = min(remaining, weight)
        tail_sum += loss * take
        remaining -= take
        if remaining <= 1e-14:
            break
    return {"var": var, "es": tail_sum / (1 - alpha)}


def terminal_pnl(legs, entry_credit, spot):
    return entry_credit + math.fsum(
        leg["qty"] * max((spot - leg["strike"]) if leg["type"] == "CE"
                         else (leg["strike"] - spot), 0.0) for leg in legs)


class TerminalDistribution:
    """Exact empirical terminal expectations via sorted probability moments.

    VaR is numerically solved to sub-paise tolerance; ES uses the exact CVaR
    identity at that quantile, preserving fractional discrete boundary mass.
    Runtime per candidate is independent of the scenario count except bisects.
    """

    def __init__(self, scenarios):
        ordered = sorted((s["spot"], s["weight"]) for s in scenarios if s["weight"] > 0)
        self.spots = [s for s, _ in ordered]
        total = math.fsum(w for _, w in ordered)
        self.mass, self.moment = [0.0], [0.0]
        for spot, weight in ordered:
            normalized = weight / total
            self.mass.append(self.mass[-1] + normalized)
            self.moment.append(self.moment[-1] + normalized * spot)
        self.mass[-1] = 1.0

    def capped_put(self, strike, width):
        if width <= 0:
            return 0.0
        lo, hi = bisect_left(self.spots, strike - width), bisect_left(self.spots, strike)
        return max(0.0, width * self.mass[lo] + strike * (self.mass[hi] - self.mass[lo])
                   - (self.moment[hi] - self.moment[lo]))

    def capped_call(self, strike, width):
        if width <= 0:
            return 0.0
        lo, hi = bisect_right(self.spots, strike), bisect_right(self.spots, strike + width)
        return max(0.0, width * (1 - self.mass[hi]) + self.moment[hi] - self.moment[lo]
                   - strike * (self.mass[hi] - self.mass[lo]))

    def metrics(self, row, costs=0):
        k, wp, wc, q = row["centre"], row["put_width"], row["call_width"], row["units"]
        effective_credit = (row["entry_credit_inr"] - costs) / q
        mean_payout = self.capped_put(k, wp) + self.capped_call(k, wc)
        expected = q * (effective_credit - mean_payout)

        def cdf(loss):
            threshold = effective_credit + loss / q
            if threshold < 0:
                return 0.0
            left = bisect_left(self.spots, k - threshold) if threshold < wp else 0
            right = bisect_right(self.spots, k + threshold) if threshold < wc else len(self.spots)
            return self.mass[right] - self.mass[left]

        risk = {}
        for alpha in ALPHAS:
            low, high = 0.0, max(0.0, q * (max(wp, wc) - effective_credit))
            if cdf(0) + 1e-12 >= alpha:
                var = 0.0
            else:
                for _ in range(48):
                    middle = (low + high) / 2
                    if cdf(middle) + 1e-12 >= alpha:
                        high = middle
                    else:
                        low = middle
                var = high
            threshold = effective_credit + var / q
            if threshold < 0:
                excess = q * (mean_payout - threshold)
            else:
                excess = q * (self.capped_put(k - threshold, wp - threshold)
                              + self.capped_call(k + threshold, wc - threshold))
            risk[str(alpha)] = {"var": var, "es": var + excess / (1 - alpha)}
        return expected, risk


def all_candidates(group, min_width=0):
    """Enumerate every lower PE / upper CE pair for every declared centre."""
    if "candidates" in group:
        if "chain" in group:
            raise ValueError("provide chain or explicit candidates, not both")
        return group["candidates"], {"scope": "explicit supplied candidates", "exhaustive_chain": False}
    chain = group["chain"]
    index = {}
    for leg in chain:
        key = (leg["strike"], leg["type"])
        if key in index:
            raise ValueError("duplicate strike/type in frozen chain")
        index[key] = leg
    centres = group["centres"]
    if len(set(centres)) != len(centres):
        raise ValueError("duplicate centres")
    if len({leg["id"] for leg in chain}) != len(chain):
        raise ValueError("duplicate contract IDs")
    q = group["units"]
    candidates, centre_coverage = [], []
    for centre in centres:
        all_lower = sorted(k for k, kind in index if kind == "PE" and k < centre)
        all_upper = sorted(k for k, kind in index if kind == "CE" and k > centre)
        lower = [k for k in all_lower if centre - k >= min_width]
        upper = [k for k in all_upper if k - centre >= min_width]
        missing_body = any((centre, kind) not in index for kind in ("PE", "CE"))
        centre_coverage.append({"centre": centre, "lower_puts": len(lower),
                                "upper_calls": len(upper), "pairs": len(lower) * len(upper),
                                "all_geometry_pairs": len(all_lower) * len(all_upper),
                                "policy_excluded_narrow_pairs": len(all_lower) * len(all_upper) - len(lower) * len(upper),
                                "missing_body": missing_body})
        for lo in lower:
            for hi in upper:
                refs = [(lo, "PE", q), (centre, "PE", -q),
                        (centre, "CE", -q), (hi, "CE", q)]
                legs = [dict(index[(strike, kind)], qty=qty) for strike, kind, qty in refs
                        if (strike, kind) in index]
                candidates.append({"id": f"{group['id']}:{centre:g}:{lo:g}:{hi:g}", "legs": legs})
    return candidates, {"scope": "every pair in frozen chain for declared centres",
                        "exhaustive_chain": True, "centres": centre_coverage,
                        "chain_contracts": len(chain), "declared_centres": centres,
                        "listed_universe_complete": group.get("listed_universe_complete", False),
                        "listing_source": group.get("listing_source")}


def check_book(leg, quantity, entering, live=False, as_of=None, max_age=30):
    reasons = []
    bid, ask = leg.get("bid"), leg.get("ask")
    if not number(bid) or not number(ask) or bid <= 0 or ask <= 0:
        reasons.append("MISSING_OR_NONPOSITIVE_BOOK")
    elif bid > ask:
        reasons.append("CROSSED_BOOK")
    # Entry: long ask / short bid. Liquidation: long bid / short ask.
    side = "ask" if (quantity > 0) == entering else "bid"
    depth = leg.get(side + "_size")
    if not number(depth) or depth < abs(quantity):
        reasons.append("INSUFFICIENT_" + side.upper() + "_DEPTH")
    if live:
        try:
            age = (timestamp(as_of) - timestamp(leg["quote_at"])).total_seconds()
            if age < -1 or age > max_age:
                reasons.append("STALE_OR_FUTURE_QUOTE")
        except (ValueError, TypeError, KeyError, AttributeError):
            reasons.append("MISSING_QUOTE_CLOCK")
    return reasons


def greek_data_issues(leg):
    """Provider model failures are unavailable exposures, never real zero risk.

    A single rounded zero (e.g. gamma on a distant wing) is legitimate. An
    entire zero delta/gamma/theta/vega tuple on a quoted option is not a usable
    model result for ranking. IV is optional, but a supplied invalid IV is a
    further model-quality failure even if the Greek tuple looks nonzero.
    """
    issues = []
    values = [leg.get("greeks", {}).get(greek) for greek in GREEKS]
    if all(number(value) and value == 0 for value in values):
        issues.append("UNAVAILABLE_GREEKS_ALL_ZERO")
    for key in ("iv", "implied_volatility"):
        value = leg.get(key)
        if value is not None and (not number(value) or value <= 0):
            issues.append("UNAVAILABLE_GREEKS_INVALID_IV")
            break
    return issues


def describe_candidate(candidate, group, policy):
    legs = candidate.get("legs", [])
    pricing_basis = group.get("pricing_basis", "BID_ASK_ENTRY_SIDES")
    valuation_only = pricing_basis == "LTP_VALUATION_ONLY"
    row = {"id": candidate["id"], "group": group["id"], "underlying": group["underlying"],
           "expiry": group["expiry"], "as_of": group["as_of"], "horizon_at": group["horizon_at"],
           "quote_status": group["quote_status"], "units": group["units"],
           "pricing_basis": pricing_basis, "executable": False,
           "legs": legs, "eligible": False, "reject_reasons": [],
           "costs_inr": candidate.get("costs_inr", group.get("costs_inr")),
           "costs_source": candidate.get("costs_source", group.get("costs_source")),
           "expected_gross_pnl_inr": None, "expected_net_pnl_inr": None,
           "risk_gross": None, "risk_net": None, "objective_basis": None}
    reasons = row["reject_reasons"]
    q = group["units"]
    if not number(q) or q <= 0 or int(q) != q:
        raise ValueError("units must be a positive integer, not lots")
    if len(legs) != 4 or any(leg.get("type") not in ("CE", "PE")
                            or not number(leg.get("strike")) or leg["strike"] < 0
                            or leg.get("qty") not in (q, -q) for leg in legs):
        reasons.append("NOT_FOUR_MATCHED_UNIT_OPTION_LEGS")
        return row
    if len({leg.get("id") for leg in legs}) != 4 or any(not leg.get("id") for leg in legs):
        reasons.append("MISSING_OR_DUPLICATE_CONTRACT_ID")
        return row
    if any(leg.get("expiry", group["expiry"]) != group["expiry"]
           or leg.get("underlying", group["underlying"]) != group["underlying"] for leg in legs):
        reasons.append("MIXED_EXPIRY_OR_UNDERLYING")
        return row
    parts = {(kind, sign): [leg for leg in legs if leg["type"] == kind and leg["qty"] == sign * q]
             for kind in ("PE", "CE") for sign in (-1, 1)}
    if any(len(values) != 1 for values in parts.values()):
        reasons.append("NOT_SHORT_IRON_BUTTERFLY")
        return row
    lp, sp, sc, lc = (parts[key][0] for key in (("PE", 1), ("PE", -1), ("CE", -1), ("CE", 1)))
    centre, lo, hi = sp["strike"], lp["strike"], lc["strike"]
    if sc["strike"] != centre or not lo < centre < hi:
        reasons.append("INVALID_BODY_OR_PROTECTION")
        return row
    wp, wc = centre - lo, hi - centre
    row.update(centre=centre, lower_put=lo, upper_call=hi, put_width=wp,
               call_width=wc, symmetric=wp == wc)
    if min(wp, wc) < policy["min_wing_points"]:
        reasons.append("NARROW_WING")
    if valuation_only and group["quote_status"] != "REFERENCE":
        reasons.append("LTP_VALUATION_REQUIRES_REFERENCE_STATUS")
    for leg in legs:
        if valuation_only:
            if not number(leg.get("valuation_price")) or leg["valuation_price"] <= 0:
                reasons.append(f"{leg['id']}:MISSING_OR_NONPOSITIVE_LTP_VALUATION")
        else:
            reasons.extend(f"{leg['id']}:{reason}" for reason in check_book(
                leg, leg["qty"], True, group["quote_status"] == "LIVE", group["as_of"],
                policy.get("max_quote_age_seconds", 30)))
    if any(reason != "NARROW_WING" for reason in reasons):
        return row
    entry_price = lambda leg: leg["valuation_price"] if valuation_only else leg["ask" if leg["qty"] > 0 else "bid"]
    credit = -math.fsum(leg["qty"] * entry_price(leg) for leg in legs)
    c = credit / q
    if c <= 0:
        reasons.append("NONPOSITIVE_ENTRY_CREDIT")
        return row
    # Verify caps and roots from the generic signed-leg payoff, not the label.
    payoff = lambda spot: terminal_pnl(legs, credit, spot)
    tail_pnls = (payoff(0), payoff(hi + max(wp, wc)))
    caps = tuple(max(-value, 0.0) for value in tail_pnls)
    breakevens = (centre - c if c < wp else None, centre + c if c < wc else None)
    if any(abs(payoff(be)) > 1e-6 for be in breakevens if be is not None) or abs(payoff(centre) - credit) > 1e-6:
        raise ValueError("signed-leg payoff validation failed")
    row.update(entry_credit_inr=credit, entry_credit_points=c, max_profit_gross_inr=credit,
               downside_max_loss_gross_inr=caps[0], upside_max_loss_gross_inr=caps[1],
               max_loss_gross_inr=max(caps), breakeven_low_gross=breakevens[0],
               breakeven_high_gross=breakevens[1],
               profitable_width_gross_points=2 * c if all(b is not None for b in breakevens) else None,
               tail_pnl_down_gross_inr=tail_pnls[0], tail_pnl_up_gross_inr=tail_pnls[1],
               breakeven_note="A null root means that side never crosses zero; a zero tail can be an interval, not one root.",
               apparent_nonpositive_loss_caps=not any(caps),
               roundtrip_book_spread_inr=None if valuation_only else q * math.fsum(leg["ask"] - leg["bid"] for leg in legs),
               wing_ask_points=None if valuation_only else lp["ask"] + lc["ask"],
               wing_valuation_points=entry_price(lp) + entry_price(lc))
    invalid_greek_ids = []
    for leg in legs:
        issues = greek_data_issues(leg)
        if issues:
            invalid_greek_ids.append(leg["id"])
            reasons.extend(f"{leg['id']}:{issue}" for issue in issues)
    for greek in GREEKS:
        values = [leg.get("greeks", {}).get(greek) for leg in legs]
        row[greek] = (math.fsum(leg["qty"] * value for leg, value in zip(legs, values))
                      if not invalid_greek_ids and all(map(number, values)) else None)
    if row["theta"] is None or row["gamma"] is None:
        reasons.append("MISSING_THETA_OR_GAMMA")
    elif row["theta"] <= 0:
        reasons.append("NONPOSITIVE_THETA")
    row["adverse_gamma"] = max(-row["gamma"], 0) if row["gamma"] is not None else None
    if row["costs_inr"] is not None and (not number(row["costs_inr"]) or row["costs_inr"] < 0):
        reasons.append("INVALID_COSTS")
    row["eligible"] = not reasons
    row["executable"] = row["eligible"] and not valuation_only and group["quote_status"] == "LIVE"
    return row


def distribution_gate(group, mode):
    distribution = group.get("distribution")
    if not distribution:
        return None, ["NO_PROBABILITY_DISTRIBUTION"], []
    errors, cautions = [], []
    if distribution.get("horizon_at") != group["horizon_at"]:
        errors.append("DISTRIBUTION_HORIZON_MISMATCH")
    kind = distribution.get("kind")
    if kind not in ("terminal_spot", "liquidation_matrix"):
        errors.append("UNSUPPORTED_REPRICING_KIND")
    if kind == "terminal_spot":
        if group["horizon_at"][:10] != group["expiry"][:10]:
            errors.append("TERMINAL_PAYOFF_REQUIRES_EXPIRY_HORIZON")
        if group.get("horizon_kind") not in (None, "EXPIRY"):
            errors.append("TERMINAL_PAYOFF_NOT_INTRADAY_MODEL")
        if group.get("expiry_at") and group["expiry_at"] != group["horizon_at"]:
            errors.append("TERMINAL_SETTLEMENT_TIME_MISMATCH")
        if not group.get("settlement_clock_verified"):
            cautions.append("SETTLEMENT_CLOCK_NOT_VERIFIED")
    scenarios = distribution.get("scenarios", [])
    if not scenarios or any(not number(s.get("weight")) or s["weight"] < 0 for s in scenarios):
        errors.append("MISSING_OR_INVALID_PROBABILITIES")
    elif abs(math.fsum(s["weight"] for s in scenarios) - 1) > 1e-8:
        errors.append("PROBABILITIES_DO_NOT_SUM_TO_ONE")
    if len({s.get("id") for s in scenarios}) != len(scenarios) or any(not s.get("id") for s in scenarios):
        errors.append("MISSING_OR_DUPLICATE_SCENARIO_ID")
    if kind == "terminal_spot" and any(not number(s.get("spot")) or s["spot"] < 0 for s in scenarios):
        errors.append("INVALID_TERMINAL_SPOT")
    validation = distribution.get("validation", {})
    if mode == "CURRENT_CARRY_TAIL":
        if distribution.get("measure") != "Q":
            errors.append("CURRENT_MODE_REQUIRES_EXPLICIT_Q_MEASURE")
        if (distribution.get("input_basis") != "CURRENT_OPTION_QUOTES"
                or distribution.get("uses_historical_returns") is not False):
            errors.append("CURRENT_MODE_FORBIDS_HISTORICAL_RETURN_INPUTS")
        if not distribution.get("source") or not distribution.get("model"):
            errors.append("CURRENT_MODE_REQUIRES_SOURCE_AND_MODEL")
        try:
            if timestamp(distribution["as_of"]) != timestamp(group["as_of"]):
                errors.append("CURRENT_DISTRIBUTION_SNAPSHOT_MISMATCH")
        except (KeyError, ValueError, TypeError, AttributeError):
            errors.append("CURRENT_DISTRIBUTION_SNAPSHOT_UNVERIFIED")
        if group["quote_status"] == "HISTORICAL":
            errors.append("CURRENT_MODE_REJECTS_HISTORICAL_QUOTE_STATUS")
        cautions.extend(["Q_OPTION_IMPLIED_NOT_PHYSICAL_LOSS_FORECAST",
                         "PARAMETRIC_CURRENT_INPUT_RISK_PROXY_NOT_CALIBRATED_REAL_WORLD_RISK",
                         "FROZEN_THETA_CARRY_INDEX_NOT_INTEGRATED_DECAY_OR_EXPECTED_PROFIT"])
    else:
        for key in ("physical", "out_of_sample", "tail_support", "calibration", "horizon_matched"):
            if validation.get(key) is not True:
                cautions.append("UNVALIDATED_" + key.upper())
        if kind == "liquidation_matrix" and validation.get("joint_repricing") is not True:
            cautions.append("UNVALIDATED_JOINT_REPRICING")
        if not distribution.get("source"):
            cautions.append("MISSING_DISTRIBUTION_SOURCE")
        if not validation.get("details"):
            cautions.append("MISSING_VALIDATION_EVIDENCE")
        if distribution.get("status") != "VALIDATED":
            cautions.append("DISTRIBUTION_DECLARED_SHADOW")
    return distribution, errors, cautions


def scenario_values(row, distribution):
    gross, net, errors = [], [], []
    for scenario in distribution["scenarios"]:
        if distribution["kind"] == "terminal_spot":
            value = terminal_pnl(row["legs"], row["entry_credit_inr"], scenario["spot"])
        else:
            quotes, future_value = scenario.get("quotes", {}), 0.0
            for leg in row["legs"]:
                quote = quotes.get(leg["id"], {})
                bad = check_book(quote, leg["qty"], False)
                if bad:
                    errors.append(f"{scenario['id']}:{leg['id']}:" + ",".join(bad))
                    continue
                future_value += leg["qty"] * quote["bid" if leg["qty"] > 0 else "ask"]
            value = row["entry_credit_inr"] + future_value
        gross.append(value)
        costs = scenario.get("costs_by_candidate", {}).get(row["id"], scenario.get("costs_inr", row["costs_inr"]))
        if costs is not None and (not number(costs) or costs < 0):
            errors.append(f"{scenario['id']}:INVALID_TOTAL_COSTS")
        net.append(value - costs if number(costs) and costs >= 0 else None)
    return gross, net, errors


def pareto_frontier(rows, objectives):
    """Exact nondominance, maximizing all objectives; ties are retained.

    Lexicographic sweep plus a sparse Fenwick dominance index avoid quadratic
    pairwise comparisons. There is no candidate sampling or top-K truncation.
    """
    if len(objectives) == 3:
        # Constant padding preserves exact three-objective dominance.
        objectives = [*objectives, lambda row: 0]
    points = sorted(((tuple(fn(row) for fn in objectives), row["id"]) for row in rows), reverse=True)
    if not points:
        return []
    if len(objectives) == 2:
        frontier, best = [], -math.inf
        previous = None
        for point, identifier in points:
            if point[1] > best or point == previous:
                frontier.append(identifier)
                best, previous = point[1], point
        return frontier
    if len(objectives) != 4:
        raise ValueError("efficient frontier supports two, three or four objectives")
    # Sweep descending objective 1. A sparse two-dimensional Fenwick index
    # answers dominance in objectives 2/3 while storing max objective 4.
    ranks = {value: i + 1 for i, value in enumerate(sorted({p[1] for p, _ in points}, reverse=True))}
    size = len(ranks)
    coordinates = [[] for _ in range(size + 1)]
    for point, _ in points:
        at = ranks[point[1]]
        while at <= size:
            coordinates[at].append(-point[2])
            at += at & -at
    coordinates = [sorted(set(values)) for values in coordinates]
    trees = [[-math.inf] * (len(values) + 1) for values in coordinates]
    frontier, previous, previous_passed = [], None, False
    for point, identifier in points:
        if point == previous:
            if previous_passed:
                frontier.append(identifier)
            continue
        at, maximum = ranks[point[1]], -math.inf
        while at > 0:
            pos = bisect_right(coordinates[at], -point[2])
            while pos > 0:
                maximum = max(maximum, trees[at][pos])
                pos -= pos & -pos
            at -= at & -at
        previous, previous_passed = point, maximum < point[3]
        if previous_passed:
            frontier.append(identifier)
        # Dominated points can be inserted without changing correct queries.
        at = ranks[point[1]]
        while at <= size:
            pos = bisect_left(coordinates[at], -point[2]) + 1
            while pos < len(trees[at]):
                trees[at][pos] = max(trees[at][pos], point[3])
                pos += pos & -pos
            at += at & -at
    return frontier


def evaluate_group(group, policy):
    mode = policy["objective_mode"]
    current = mode == "CURRENT_CARRY_TAIL"
    pricing_basis = group.get("pricing_basis", "BID_ASK_ENTRY_SIDES")
    if pricing_basis not in ("BID_ASK_ENTRY_SIDES", "LTP_VALUATION_ONLY"):
        raise ValueError("unknown pricing_basis")
    if pricing_basis == "LTP_VALUATION_ONLY" and (not current or group["quote_status"] != "REFERENCE"):
        raise ValueError("LTP_VALUATION_ONLY requires CURRENT_CARRY_TAIL and REFERENCE status; never LIVE")
    if group["quote_status"] not in ("LIVE", "REFERENCE", "HISTORICAL"):
        raise ValueError("quote_status must be LIVE, REFERENCE or HISTORICAL")
    horizon_days = (timestamp(group["horizon_at"]) - timestamp(group["as_of"])).total_seconds() / 86400
    if horizon_days < 0:
        raise ValueError("horizon precedes quote snapshot")
    carry_days = group.get("carry_horizon_days")
    if current and (not number(carry_days) or carry_days <= 0
                    or abs(carry_days - horizon_days) > 1 / 86400):
        raise ValueError("current mode requires positive explicit carry_horizon_days matching the risk horizon within one second")
    candidates, coverage = all_candidates(group, policy["min_wing_points"])
    if len({c["id"] for c in candidates}) != len(candidates):
        raise ValueError("duplicate candidate IDs")
    rows = [describe_candidate(candidate, group, policy) for candidate in candidates]
    distribution, errors, cautions = distribution_gate(group, mode)
    if pricing_basis == "LTP_VALUATION_ONLY":
        cautions.append("ENTRY_FROM_LTP_VALUATION_ONLY_NO_EXECUTABLE_BOOK_OR_DEPTH")
    if group["quote_status"] != "LIVE":
        cautions.append("REFERENCE_ONLY_ENTRY_QUOTES")
    if not group.get("contracts_verified") or group.get("lot_size") != group["units"]:
        cautions.append("CURRENT_CONTRACTS_OR_ONE_LOT_NOT_VERIFIED")
    if not group.get("greek_conventions"):
        cautions.append("GREEK_UNITS_AND_CLOCK_NOT_VERIFIED")
    if not group.get("account_verified"):
        cautions.append("ACCOUNT_AND_CORRELATED_EXPOSURES_NOT_VERIFIED")
    eligible = [row for row in rows if row["eligible"]]
    weighted = []
    if distribution and not errors:
        weights = [scenario["weight"] for scenario in distribution["scenarios"]]
        total_weight = math.fsum(weights)
        weights = [w / total_weight for w in weights]
        fast_terminal = (distribution["kind"] == "terminal_spot"
                         and all("costs_by_candidate" not in s and "costs_inr" not in s
                                 for s in distribution["scenarios"]))
        terminal = TerminalDistribution(distribution["scenarios"]) if fast_terminal else None
        for row in eligible:
            if terminal:
                row["expected_gross_pnl_inr"], row["risk_gross"] = terminal.metrics(row)
                if row["costs_inr"] is not None:
                    row["expected_net_pnl_inr"], row["risk_net"] = terminal.metrics(row, row["costs_inr"])
                row["scenario_errors"] = []
                weighted.append(row)
                continue
            gross, net, scenario_errors = scenario_values(row, distribution)
            row["scenario_errors"] = scenario_errors
            if scenario_errors:
                continue
            row["expected_gross_pnl_inr"] = math.fsum(v * w for v, w in zip(gross, weights))
            row["risk_gross"] = {str(alpha): positive_loss_var_es(gross, weights, alpha) for alpha in ALPHAS}
            if all(value is not None for value in net):
                row["expected_net_pnl_inr"] = math.fsum(v * w for v, w in zip(net, weights))
                row["risk_net"] = {str(alpha): positive_loss_var_es(net, weights, alpha) for alpha in ALPHAS}
            weighted.append(row)
    # Do not compare net and gross metrics within a group. If any candidate has
    # unknown costs, use gross for the entire research frontier and flag it.
    basis = "net" if weighted and all(r["risk_net"] is not None for r in weighted) else "gross"
    if basis == "gross":
        cautions.append("NET_OBJECTIVE_UNAVAILABLE_OR_INCOMPLETE_COSTS")
    for row in weighted:
        row["objective_basis"] = basis.upper()
        if current:
            row["theta_carry_proxy_inr"] = row["theta"] * carry_days
            row["risk_measure"] = "Q"
    frontiers, sensitivity = {}, []
    benefit = (lambda row: row["theta_carry_proxy_inr"]) if current else (lambda row: row[f"expected_{basis}_pnl_inr"])
    for alpha in ALPHAS:
        tail = lambda row, alpha=alpha: row[f"risk_{basis}"][str(alpha)]["es"]
        if current:
            frontiers[str(alpha)] = {"theta_carry_es_adverse_gamma": pareto_frontier(
                weighted, [benefit, lambda r: -tail(r), lambda r: -r["adverse_gamma"]])}
        else:
            frontiers[str(alpha)] = {
                "expected_pnl_vs_es": pareto_frontier(weighted, [benefit, lambda r: -tail(r)]),
                "expected_pnl_es_theta_adverse_gamma": pareto_frontier(
                    weighted, [benefit, lambda r: -tail(r), lambda r: r["theta"], lambda r: -r["adverse_gamma"]])}
        for penalty in LAMBDAS:
            scores = [(benefit(row) - penalty * tail(row), row["id"]) for row in weighted]
            maximum = max((value for value, _ in scores), default=None)
            ties = [identifier for value, identifier in scores
                    if maximum is not None and math.isclose(value, maximum, rel_tol=1e-12, abs_tol=1e-8)]
            item = {"alpha": alpha, "lambda": penalty, "score_inr": maximum, "candidate_ids": ties}
            if current:
                item["label"] = "FROZEN_THETA_MINUS_Q_ES_PREFERENCE_SCORE_NOT_EXPECTED_PNL_OR_TRADE_VERDICT"
            else:
                item.update(cash_benchmark_score=0.0,
                            clears_cash_benchmark=maximum is not None and maximum > 0,
                            research_choice="CANDIDATE" if maximum is not None and maximum > 0 else "NO_NEW_TRADE",
                            label="SHADOW_RESEARCH_WEIGHT_WINNERS_NOT_TRADE_ADVICE")
            sensitivity.append(item)
    reasons = {}
    for row in rows:
        for reason in row["reject_reasons"]:
            key = reason.split(":")[-1]
            reasons[key] = reasons.get(key, 0) + 1
    coverage.update(enumerated=len(rows), eligible=len(eligible), rejected=len(rows) - len(eligible),
                    distribution_scored=len(weighted), reject_reason_counts=reasons,
                    enumeration_reconciled=len(rows) == len(eligible) + sum(not r["eligible"] for r in rows),
                    no_top_k_or_width_sampling=True)
    coverage["policy_excluded_narrow_pairs"] = sum(c.get("policy_excluded_narrow_pairs", 0) for c in coverage.get("centres", []))
    coverage["narrow_rejection_retention"] = "Exact non-overlapping per-centre geometry counts; explicit supplied narrow candidates retain individual reasons."
    if weighted:
        weights = [s["weight"] for s in distribution["scenarios"]]
        if current:
            tail_diagnostics = {"quadrature_nodes": len(weights), "measure": "Q",
                                "note": "Numerical quadrature, not historical observations or independent statistical samples. Tail accuracy depends on the supplied current-input model and numerical convergence."}
        else:
            neff = 1 / math.fsum(w * w for w in weights)
            tail_diagnostics = {"scenario_count": len(weights), "kish_weight_effective_sample_size": neff,
                                "nominal_tail_effective_observations": {str(a): neff * (1 - a) for a in ALPHAS},
                                "note": "Not independent observations when windows overlap; numeric ES is not tail validation."}
    else:
        tail_diagnostics = None
    # The immutable input contract book is retained once. Per-row signed refs
    # preserve every exact leg while avoiding repeated full quote/Greek blobs.
    for row in rows:
        row["legs"] = [{key: leg[key] for key in ("id", "type", "strike", "qty")} for leg in row["legs"]]
        if current:
            # Do not publish risk-neutral means under expected-profit labels.
            row.pop("expected_gross_pnl_inr", None)
            row.pop("expected_net_pnl_inr", None)
    book = group.get("chain") or list({leg["id"]: leg for c in candidates for leg in c["legs"]}.values())
    output = {"id": group["id"], "underlying": group["underlying"], "expiry": group["expiry"],
            "horizon_at": group["horizon_at"], "horizon_days": horizon_days,
            "objective_mode": mode,
            "pricing_basis": pricing_basis,
            "execution_pricing_available": pricing_basis != "LTP_VALUATION_ONLY",
            "quote_status": group["quote_status"], "objective_basis": basis.upper() if weighted else None,
            "model_status": "UNCOMPUTABLE" if not weighted else ("CURRENT_Q_PROXY_DIAGNOSTIC_ONLY" if current else ("SHADOW" if cautions else "VALIDATED_INPUTS_RESEARCH_ONLY")),
            "live_trade_approval": False, "unique_optimum": None,
            "blocking_distribution_errors": errors, "cautions": cautions,
            "coverage": coverage, "distribution_metadata": {k: v for k, v in (distribution or {}).items() if k != "scenarios"},
            "tail_diagnostics": tail_diagnostics, "frontiers": frontiers,
            "contract_book": book, "lambda_sensitivity": sensitivity, "rows": rows}
    if current:
        output.update(carry_horizon_days=carry_days, risk_measure="Q",
                      carry_label="FROZEN_THETA_CARRY_INDEX_NOT_INTEGRATED_DECAY_OR_EXPECTED_PROFIT",
                      carry_cost_basis="GROSS_LOCAL_THETA_INDEX; known costs affect tail losses separately",
                      trade_verdict=None)
    else:
        output["cash_benchmark"] = {"expected_pnl_inr": 0, "es_inr": 0, "theta": 0, "adverse_gamma": 0}
    return output


def evaluate(document):
    policy = document.get("policy", {})
    minimum = policy.get("min_wing_points")
    if not number(minimum) or minimum <= 0:
        raise ValueError("an explicit positive min_wing_points is required; wide has no universal default")
    mode = policy.get("objective_mode")
    if mode not in ("CURRENT_CARRY_TAIL", "PHYSICAL_EXPECTED_PNL"):
        raise ValueError("explicit objective_mode required: CURRENT_CARRY_TAIL or separately authorized PHYSICAL_EXPECTED_PNL")
    groups = document.get("groups", [])
    if len({g["id"] for g in groups}) != len(groups):
        raise ValueError("duplicate group IDs")
    return {"engine": VERSION, "input_sha256": hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest(),
            "policy": policy, "research_alphas": ALPHAS, "research_lambdas": LAMBDAS,
            "objective": ("FrozenTheta * H - lambda * ES_Q_alpha(max(-PnL_H,0)); preference index, not expected profit"
                          if mode == "CURRENT_CARRY_TAIL" else "E[PnL_H] - lambda * ES_alpha(max(-PnL_H, 0)); use net only with complete costs"),
            "theta_gamma_objective": "maximize positive theta and minimize max(-signed_gamma,0) on exact multiobjective frontier",
            "interpretation": ["No unique mathematical optimum without a chosen tradeoff.",
                               "Lambda/alpha are research sensitivities, not the user's risk preferences.",
                               "No cross-expiry, cross-horizon or cross-unit ranking.",
                               "Full repricing already includes carry: theta and gamma are not added to expected P&L.",
                               "Maximum loss is a disclosed cap, never a ranking denominator.",
                               "Expiry scenarios say nothing quantitative about earlier liquidation without full repricing.",
                               "This engine never places orders or certifies personalized risk acceptability."],
            "groups": [evaluate_group(group, policy) for group in groups]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.input.read_text()))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    if args.csv:
        rows = [row for group in result["groups"] for row in group["rows"]]
        keys = list(dict.fromkeys(key for row in rows for key in row))
        with args.csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            writer.writerows({key: json.dumps(value, sort_keys=True, allow_nan=False)
                              if isinstance(value, (dict, list)) else value for key, value in row.items()} for row in rows)
    print(json.dumps({"engine": VERSION, "output": str(args.output),
                      "groups": [{"id": g["id"], "status": g["model_status"], "coverage": g["coverage"]}
                                 for g in result["groups"]]}, indent=2))


if __name__ == "__main__":
    main()
