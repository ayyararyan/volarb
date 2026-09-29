import math
import unittest

import numpy as np

import robust_tail_selection as rts


class TailMeasures(unittest.TestCase):
    def test_var_es_with_fractional_atom(self):
        losses = np.array([[0.0, 10.0, 20.0, 100.0]])
        weights = np.array([0.5, 0.3, 0.15, 0.05])
        var, es = rts.var_es(losses, weights, 0.95)
        # cumulative 0.5, 0.8, 0.95 -> VaR at 20; tail mass 0.05 sits entirely at 100
        self.assertAlmostEqual(var[0], 20.0)
        self.assertAlmostEqual(es[0], 100.0)
        var90, es90 = rts.var_es(losses, weights, 0.90)
        # tail 0.10 = 0.05 atom of the 20 bucket + 0.05 of 100
        self.assertAlmostEqual(var90[0], 20.0)
        self.assertAlmostEqual(es90[0], (0.05 * 20 + 0.05 * 100) / 0.10)

    def test_terminal_payoff_caps_both_wings(self):
        pnl = rts.terminal_pnl(30, 800.0, 56400.0, 1800.0, 1800.0, np.array([40000.0, 56400.0, 70000.0]))
        self.assertAlmostEqual(pnl[0], 30 * (800 - 1800))
        self.assertAlmostEqual(pnl[1], 30 * 800)
        self.assertAlmostEqual(pnl[2], 30 * (800 - 1800))


class Distributions(unittest.TestCase):
    def test_t3_inverse_cdf_roundtrip_and_symmetry(self):
        for u in (0.01, 0.2, 0.5, 0.9, 0.999):
            t = rts.t3_inv_cdf(u)
            self.assertAlmostEqual(rts.t3_cdf(t), u, places=8)
        self.assertAlmostEqual(rts.t3_inv_cdf(0.5), 0.0, places=6)
        self.assertAlmostEqual(rts.t3_inv_cdf(0.9), -rts.t3_inv_cdf(0.1), places=6)

    def test_lognormal_and_t_nodes_are_forward_neutral(self):
        for spots, weights in (rts.lognormal_nodes(56539.0, 0.13, 0.0245, 4096),
                               rts.student_t3_nodes(56539.0, 0.13, 0.0245, 4096)):
            self.assertAlmostEqual(float(np.sum(weights)), 1.0, places=12)
            self.assertLess(abs(float(np.sum(weights * spots)) / 56539.0 - 1.0), 2e-3)

    def test_t3_has_fatter_tail_than_lognormal_at_matched_variance(self):
        ln_s, ln_w = rts.lognormal_nodes(56539.0, 0.13, 0.0245, 4096)
        t_s, t_w = rts.student_t3_nodes(56539.0, 0.13, 0.0245, 4096)
        ln_tail = float(np.sum(ln_w[np.abs(np.log(ln_s / 56539.0)) > 0.06]))
        t_tail = float(np.sum(t_w[np.abs(np.log(t_s / 56539.0)) > 0.06]))
        self.assertGreater(t_tail, ln_tail)

    def test_flat_smile_density_reproduces_lognormal_tail(self):
        forward, years, sigma = 56539.0, 0.0245, 0.13
        chain = []
        for strike in range(50000, 63001, 250):
            kind = "PE" if strike < forward else "CE"
            price = rts.black(forward, strike, sigma, years, kind)
            chain.append({"strike": strike, "type": kind, "iv": sigma, "valuation_price": price})
        smile = rts.fit_smile(chain, forward, years)
        self.assertLess(smile["rmse"], 1e-9)
        spots, weights, diag, valid = rts.smile_density_nodes(forward, years, smile)
        self.assertTrue(valid, diag)
        losses = np.maximum(-rts.terminal_pnl(30, 800.0, 56500.0, 1800.0, 1800.0, spots)[None, :], 0.0)
        _, es_bl = rts.var_es(losses, weights, 0.99)
        ln_s, ln_w = rts.lognormal_nodes(forward, sigma, years, 8192)
        ln_losses = np.maximum(-rts.terminal_pnl(30, 800.0, 56500.0, 1800.0, 1800.0, ln_s)[None, :], 0.0)
        _, es_ln = rts.var_es(ln_losses, ln_w, 0.99)
        self.assertLess(abs(es_bl[0] - es_ln[0]) / es_ln[0], 0.02)


class Efficiency(unittest.TestCase):
    def test_single_atm_option_gamma_theta_efficiency_is_one(self):
        forward, years, sigma = 56539.0, 0.0245, 0.13
        sd = sigma * math.sqrt(years)
        d1 = sd / 2
        density = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
        gamma = density / (forward * sd)
        theta = forward * density * sigma / (2 * math.sqrt(years) * 365)
        breakeven_move = math.sqrt(2 * theta / gamma)
        implied_daily = forward * sigma / math.sqrt(365)
        self.assertAlmostEqual(breakeven_move / implied_daily, 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
