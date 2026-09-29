"""Synthetic in-memory checks: no broker access or production-ledger writes."""
import copy
import random
import unittest

from wide_butterfly_selector import (TerminalDistribution, describe_candidate,
                                     evaluate, pareto_frontier, positive_loss_var_es,
                                     terminal_pnl, timestamp)


def fixture():
    def leg(identifier, strike, kind, bid, ask, theta, gamma):
        return {"id": identifier, "strike": strike, "type": kind, "bid": bid, "ask": ask,
                "bid_size": 100, "ask_size": 100, "quote_at": "2026-09-20T10:00:00+05:30",
                "greeks": {"delta": .5 if kind == "CE" else -.5,
                           "gamma": gamma, "theta": theta, "vega": 1}}
    group = {"id": "one", "underlying": "TEST", "expiry": "2026-09-29",
             "as_of": "2026-09-20T10:00:00+05:30", "horizon_at": "2026-09-29T15:30:00+05:30",
             "horizon_kind": "EXPIRY", "units": 10, "lot_size": 10, "quote_status": "REFERENCE",
             "centres": [1000], "chain": [leg("lp", 800, "PE", 9, 10, -1, .001),
                                          leg("sp", 1000, "PE", 50, 51, -5, .005),
                                          leg("sc", 1000, "CE", 50, 51, -5, .005),
                                          leg("lc", 1200, "CE", 9, 10, -1, .001)],
             "costs_inr": None,
             "distribution": {"kind": "terminal_spot", "source": "SYNTHETIC_TEST_ONLY", "status": "SHADOW",
                              "horizon_at": "2026-09-29T15:30:00+05:30",
                              "scenarios": [{"id": "a", "spot": 1000, "weight": .9},
                                            {"id": "b", "spot": 750, "weight": .06},
                                            {"id": "c", "spot": 1300, "weight": .04}]}}
    return {"policy": {"min_wing_points": 150, "objective_mode": "PHYSICAL_EXPECTED_PNL"}, "groups": [group]}


def current_fixture():
    document = fixture()
    document["policy"]["objective_mode"] = "CURRENT_CARRY_TAIL"
    group = document["groups"][0]
    group["carry_horizon_days"] = (timestamp(group["horizon_at"]) - timestamp(group["as_of"])).total_seconds() / 86400
    group["distribution"].update(measure="Q", input_basis="CURRENT_OPTION_QUOTES", uses_historical_returns=False,
                                  as_of=group["as_of"], model="SYNTHETIC_CURRENT_Q_TEST_ONLY")
    return document


class RiskTests(unittest.TestCase):
    def test_fractional_tail_atom(self):
        risk = positive_loss_var_es([100, -10, -100], [.9, .06, .04], .95)
        self.assertEqual(risk["var"], 10)
        self.assertAlmostEqual(risk["es"], 82)
        self.assertEqual(positive_loss_var_es([3, 4], [.5, .5], .99), {"var": 0, "es": 0})

    def test_invalid_probabilities(self):
        with self.assertRaises(ValueError):
            positive_loss_var_es([-2, -5], [.1, .1], .95)

    def test_signed_payoff_and_gamma(self):
        result = evaluate(fixture())["groups"][0]
        row = result["rows"][0]
        self.assertAlmostEqual(row["entry_credit_inr"], 800)
        self.assertAlmostEqual(row["theta"], 80)
        self.assertAlmostEqual(row["gamma"], -.08)
        self.assertAlmostEqual(row["adverse_gamma"], .08)
        self.assertEqual(row["max_loss_gross_inr"], 1200)
        self.assertEqual(row["breakeven_low_gross"], 920)
        self.assertEqual(row["breakeven_high_gross"], 1080)
        self.assertAlmostEqual(terminal_pnl(row["legs"], 800, 920), 0)
        self.assertAlmostEqual(row["expected_gross_pnl_inr"], 600)
        self.assertIsNone(row["expected_net_pnl_inr"])
        self.assertEqual(row["objective_basis"], "GROSS")
        self.assertEqual(result["model_status"], "SHADOW")
        self.assertFalse(result["live_trade_approval"])
        self.assertEqual(result["lambda_sensitivity"][-1]["research_choice"], "NO_NEW_TRADE")

    def test_costs_are_not_fabricated(self):
        document = fixture()
        document["groups"][0]["costs_inr"] = 125
        row = evaluate(document)["groups"][0]["rows"][0]
        self.assertAlmostEqual(row["expected_net_pnl_inr"], 475)
        self.assertEqual(row["objective_basis"], "NET")
        self.assertAlmostEqual(row["risk_net"]["0.95"]["es"], 1325)

    def test_narrow_exclusion_has_exact_coverage(self):
        document = fixture()
        document["policy"]["min_wing_points"] = 250
        result = evaluate(document)["groups"][0]
        self.assertEqual(result["coverage"]["policy_excluded_narrow_pairs"], 1)
        self.assertEqual(result["rows"], [])
        original = fixture()["groups"][0]
        candidate = {"id": "explicit", "legs": [dict(leg, qty=10 if i in (0, 3) else -10)
                                                     for i, leg in enumerate(original["chain"])]}
        row = describe_candidate(candidate, original, {"min_wing_points": 250})
        self.assertIn("NARROW_WING", row["reject_reasons"])

    def test_crossed_and_insufficient_books(self):
        document = fixture()
        document["groups"][0]["chain"][0]["ask"] = 8
        result = evaluate(document)["groups"][0]
        self.assertIn("lp:CROSSED_BOOK", result["rows"][0]["reject_reasons"])
        document = fixture()
        document["groups"][0]["chain"][1]["bid_size"] = 2
        self.assertIn("sp:INSUFFICIENT_BID_DEPTH", evaluate(document)["groups"][0]["rows"][0]["reject_reasons"])

    def test_failed_zero_greeks_do_not_create_spurious_winner(self):
        document = fixture()
        group = document["groups"][0]
        group["chain"][1]["greeks"] = dict.fromkeys(("delta", "gamma", "theta", "vega"), 0)
        result = evaluate(document)["groups"][0]
        row = result["rows"][0]
        self.assertFalse(row["eligible"])
        self.assertIn("sp:UNAVAILABLE_GREEKS_ALL_ZERO", row["reject_reasons"])
        self.assertIsNone(row["theta"])
        self.assertIsNone(row["gamma"])
        self.assertIsNone(row["delta"])
        self.assertIsNone(row["expected_gross_pnl_inr"])
        self.assertEqual(result["coverage"]["reject_reason_counts"]["UNAVAILABLE_GREEKS_ALL_ZERO"], 1)
        self.assertEqual(result["coverage"]["distribution_scored"], 0)
        self.assertTrue(all(not s["candidate_ids"] for s in result["lambda_sensitivity"]))
        # The identical gate must apply when the caller supplies explicit legs.
        group["candidates"] = [{"id": "bad-explicit", "legs": [dict(leg, qty=10 if i in (0, 3) else -10)
                                                                  for i, leg in enumerate(group.pop("chain"))]}]
        explicit = evaluate(document)["groups"][0]["rows"][0]
        self.assertIn("sp:UNAVAILABLE_GREEKS_ALL_ZERO", explicit["reject_reasons"])

    def test_supplied_nonpositive_iv_is_not_valid_model_data(self):
        for key in ("iv", "implied_volatility"):
            for value in (0, -1):
                document = fixture()
                document["groups"][0]["chain"][0][key] = value
                row = evaluate(document)["groups"][0]["rows"][0]
                self.assertFalse(row["eligible"])
                self.assertIn("lp:UNAVAILABLE_GREEKS_INVALID_IV", row["reject_reasons"])
                self.assertIsNone(row["adverse_gamma"])

    def test_real_positive_gamma_and_individual_rounded_zero_are_allowed(self):
        document = fixture()
        legs = document["groups"][0]["chain"]
        for leg in legs:
            leg["iv"] = 20
        legs[0]["greeks"]["gamma"] = 0
        legs[3]["greeks"]["gamma"] = .02
        row = evaluate(document)["groups"][0]["rows"][0]
        self.assertTrue(row["eligible"])
        self.assertAlmostEqual(row["gamma"], .1)
        self.assertEqual(row["adverse_gamma"], 0)

    def test_expiry_not_used_for_intraday(self):
        document = fixture()
        group = document["groups"][0]
        group["horizon_at"] = group["distribution"]["horizon_at"] = "2026-09-21T15:00:00+05:30"
        result = evaluate(document)["groups"][0]
        self.assertIn("TERMINAL_PAYOFF_REQUIRES_EXPIRY_HORIZON", result["blocking_distribution_errors"])
        self.assertEqual(result["model_status"], "UNCOMPUTABLE")
        self.assertIsNone(result["rows"][0]["risk_gross"])

    def test_unvalidated_flags_cannot_promote(self):
        document = fixture()
        group = document["groups"][0]
        group["distribution"]["status"] = "VALIDATED"
        result = evaluate(document)["groups"][0]
        self.assertEqual(result["model_status"], "SHADOW")
        self.assertIn("UNVALIDATED_PHYSICAL", result["cautions"])

    def test_asymmetric_one_profitable_tail_is_retained(self):
        document = fixture()
        group = document["groups"][0]
        group["chain"][0]["strike"] = 940
        document["policy"]["min_wing_points"] = 50
        row = evaluate(document)["groups"][0]["rows"][0]
        self.assertTrue(row["eligible"])
        self.assertIsNone(row["breakeven_low_gross"])
        self.assertEqual(row["downside_max_loss_gross_inr"], 0)
        self.assertEqual(row["tail_pnl_down_gross_inr"], 200)

    def test_full_liquidation_uses_closing_sides(self):
        document = fixture()
        group = document["groups"][0]
        group["horizon_at"] = "2026-09-21T15:00:00+05:30"
        group["horizon_kind"] = "INTRADAY"
        quotes = {leg["id"]: {"bid": leg["bid"], "ask": leg["ask"], "bid_size": 100, "ask_size": 100}
                  for leg in group["chain"]}
        group["distribution"] = {"kind": "liquidation_matrix", "horizon_at": group["horizon_at"],
                                 "scenarios": [{"id": "same_book", "weight": 1, "quotes": quotes}],
                                 "status": "SHADOW"}
        row = evaluate(document)["groups"][0]["rows"][0]
        self.assertAlmostEqual(row["expected_gross_pnl_inr"], -40)
        self.assertAlmostEqual(row["risk_gross"]["0.99"]["es"], 40)

    def test_prefix_matches_direct_empirical_atoms(self):
        randomizer = random.Random(807)
        for _ in range(80):
            k, wp, wc = 1000, randomizer.randint(50, 500), randomizer.randint(50, 500)
            q, credit = 30, randomizer.uniform(10, 8000)
            spots = [k - wp, k, k + wc] + [randomizer.uniform(0, 2000) for _ in range(30)]
            raw_weights = [randomizer.randint(0, 10) for _ in spots]
            weights = [w / sum(raw_weights) for w in raw_weights]
            scenarios = [{"spot": s, "weight": w} for s, w in zip(spots, weights)]
            row = {"centre": k, "put_width": wp, "call_width": wc, "units": q, "entry_credit_inr": credit}
            costs = randomizer.uniform(0, 5000)
            pnl = [credit - costs - q * (min(max(k - s, 0), wp) + min(max(s - k, 0), wc)) for s in spots]
            expected, risk = TerminalDistribution(scenarios).metrics(row, costs)
            self.assertAlmostEqual(expected, sum(p * w for p, w in zip(pnl, weights)), places=6)
            for alpha in (.95, .99):
                direct = positive_loss_var_es(pnl, weights, alpha)
                self.assertAlmostEqual(risk[str(alpha)]["var"], direct["var"], places=5)
                self.assertAlmostEqual(risk[str(alpha)]["es"], direct["es"], places=5)

    def test_frontiers_match_bruteforce_with_ties(self):
        rng = random.Random(203)
        rows = [{"id": str(i), "v": tuple(rng.randint(-3, 3) for _ in range(4))} for i in range(150)]
        for dimensions in (2, 3, 4):
            expected = {r["id"] for r in rows if not any(
                all(a >= b for a, b in zip(other["v"][:dimensions], r["v"][:dimensions]))
                and other["v"][:dimensions] != r["v"][:dimensions] for other in rows)}
            actual = set(pareto_frontier(rows, [lambda r, i=i: r["v"][i] for i in range(dimensions)]))
            self.assertEqual(actual, expected)

    def test_exhaustive_asymmetry_and_separate_expiries(self):
        document = fixture()
        group = document["groups"][0]
        group["chain"].append(dict(group["chain"][0], id="lp2", strike=700))
        group["chain"].append(dict(group["chain"][3], id="lc2", strike=1300))
        result = evaluate(document)["groups"][0]
        self.assertEqual(result["coverage"]["enumerated"], 4)
        self.assertEqual(sum(r["symmetric"] for r in result["rows"]), 2)
        second = copy.deepcopy(group)
        second["id"], second["expiry"] = "two", "2026-10-27"
        second["horizon_at"] = second["distribution"]["horizon_at"] = "2026-10-27T15:30:00+05:30"
        document["groups"].append(second)
        self.assertEqual(len(evaluate(document)["groups"]), 2)

    def test_current_mode_uses_carry_score_not_q_mean_or_cash_verdict(self):
        document = current_fixture()
        result = evaluate(document)["groups"][0]
        row = result["rows"][0]
        self.assertNotIn("expected_gross_pnl_inr", row)
        self.assertNotIn("expected_net_pnl_inr", row)
        self.assertNotIn("cash_benchmark", result)
        self.assertEqual(result["model_status"], "CURRENT_Q_PROXY_DIAGNOSTIC_ONLY")
        self.assertEqual(row["risk_measure"], "Q")
        self.assertAlmostEqual(row["theta_carry_proxy_inr"], 80 * result["carry_horizon_days"])
        self.assertEqual(set(result["frontiers"]["0.95"]), {"theta_carry_es_adverse_gamma"})
        first = result["lambda_sensitivity"][0]
        self.assertAlmostEqual(first["score_inr"], row["theta_carry_proxy_inr"])
        last = result["lambda_sensitivity"][-1]
        self.assertLess(last["score_inr"], 0)
        self.assertNotIn("cash_benchmark_score", last)
        self.assertNotIn("research_choice", last)
        self.assertIsNone(result["trade_verdict"])
        self.assertIn("quadrature_nodes", result["tail_diagnostics"])
        self.assertNotIn("kish_weight_effective_sample_size", result["tail_diagnostics"])
        self.assertNotIn("UNVALIDATED_PHYSICAL", result["cautions"])

    def test_current_mode_rejects_historical_and_non_q_inputs(self):
        for key, value, reason in [
                ("uses_historical_returns", True, "CURRENT_MODE_FORBIDS_HISTORICAL_RETURN_INPUTS"),
                ("input_basis", "EMPIRICAL_RETURNS", "CURRENT_MODE_FORBIDS_HISTORICAL_RETURN_INPUTS"),
                ("measure", "P", "CURRENT_MODE_REQUIRES_EXPLICIT_Q_MEASURE"),
                ("as_of", "2026-09-18T10:00:00+05:30", "CURRENT_DISTRIBUTION_SNAPSHOT_MISMATCH"),
                ("source", "", "CURRENT_MODE_REQUIRES_SOURCE_AND_MODEL")]:
            document = current_fixture()
            document["groups"][0]["distribution"][key] = value
            result = evaluate(document)["groups"][0]
            self.assertIn(reason, result["blocking_distribution_errors"])
            self.assertEqual(result["coverage"]["distribution_scored"], 0)
            self.assertEqual(result["model_status"], "UNCOMPUTABLE")

    def test_objective_and_matched_carry_clock_must_be_explicit(self):
        document = fixture()
        del document["policy"]["objective_mode"]
        with self.assertRaisesRegex(ValueError, "explicit objective_mode"):
            evaluate(document)
        for value in (None, 0, 1):
            document = current_fixture()
            document["groups"][0]["carry_horizon_days"] = value
            with self.assertRaisesRegex(ValueError, "matching the risk horizon"):
                evaluate(document)

    def test_q_mean_cannot_change_zero_lambda_carry_score(self):
        document = current_fixture()
        baseline = evaluate(document)["groups"][0]
        document["groups"][0]["distribution"]["scenarios"] = [
            {"id": "all_far_tail", "spot": 3000, "weight": 1}]
        shifted = evaluate(document)["groups"][0]
        self.assertEqual(baseline["lambda_sensitivity"][0]["score_inr"],
                         shifted["lambda_sensitivity"][0]["score_inr"])
        self.assertEqual(baseline["rows"][0]["theta_carry_proxy_inr"], shifted["rows"][0]["theta_carry_proxy_inr"])

    def test_ltp_reference_valuation_does_not_invent_books_or_depth(self):
        document = current_fixture()
        group = document["groups"][0]
        group["pricing_basis"] = "LTP_VALUATION_ONLY"
        for i, leg in enumerate(group["chain"]):
            leg["valuation_price"] = leg["ask" if i in (0, 3) else "bid"]
            for key in ("bid", "ask", "bid_size", "ask_size"):
                del leg[key]
        result = evaluate(document)["groups"][0]
        row = result["rows"][0]
        self.assertTrue(row["eligible"])
        self.assertFalse(row["executable"])
        self.assertFalse(result["execution_pricing_available"])
        self.assertEqual(row["pricing_basis"], "LTP_VALUATION_ONLY")
        self.assertAlmostEqual(row["entry_credit_inr"], 800)
        self.assertIsNone(row["roundtrip_book_spread_inr"])
        self.assertIsNone(row["wing_ask_points"])
        self.assertEqual(row["wing_valuation_points"], 20)
        for leg in result["contract_book"]:
            self.assertIn("valuation_price", leg)
            for key in ("bid", "ask", "bid_size", "ask_size"):
                self.assertNotIn(key, leg)
        self.assertIn("ENTRY_FROM_LTP_VALUATION_ONLY_NO_EXECUTABLE_BOOK_OR_DEPTH", result["cautions"])

    def test_ltp_mode_never_accepts_live_or_physical_mode(self):
        document = current_fixture()
        document["groups"][0]["pricing_basis"] = "LTP_VALUATION_ONLY"
        document["groups"][0]["quote_status"] = "LIVE"
        with self.assertRaisesRegex(ValueError, "never LIVE"):
            evaluate(document)
        document["groups"][0]["quote_status"] = "REFERENCE"
        document["policy"]["objective_mode"] = "PHYSICAL_EXPECTED_PNL"
        with self.assertRaisesRegex(ValueError, "CURRENT_CARRY_TAIL"):
            evaluate(document)

    def test_ltp_price_is_required_even_if_old_book_is_present(self):
        document = current_fixture()
        document["groups"][0]["pricing_basis"] = "LTP_VALUATION_ONLY"
        result = evaluate(document)["groups"][0]
        self.assertFalse(result["rows"][0]["eligible"])
        self.assertIn("lp:MISSING_OR_NONPOSITIVE_LTP_VALUATION", result["rows"][0]["reject_reasons"])


if __name__ == "__main__":
    unittest.main()
