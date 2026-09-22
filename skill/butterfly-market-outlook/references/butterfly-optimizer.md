# Wide Butterfly Optimizer — Engine v2

Use this reference for **new butterfly search/optimization**. The optimizer is for wide symmetric **short iron butterflies** by default, evaluated through their payoff-equivalent long-fly debit where useful.

The user-facing output remains only `Rank | Butterfly | Why` or one `NO TRADE` row.

## 1. Objective

Candidate selection is a constrained multi-objective problem:

1. maximize useful carry/theta over the intended holding horizon;
2. minimize carry burden: equivalent debit/capital at risk plus realistic execution friction;
3. minimize **combined tail risk** from:
   - option-implied RND geometry/pricing risk; and
   - separate real-world event/path stress;
4. require robust liquidity in **all actual iron-fly legs**;
5. align the body with parity forward, option-implied centre and real-world path centre unless the user explicitly wants a directional fly.

Theoretical maximum loss is descriptive. It is not the tail-risk objective.

## 2. Measure separation

Never treat the risk-neutral terminal distribution as the true real-world probability distribution.

- **RND layer:** market-priced distribution, wing mass, `P(loss)` under pricing measure, expected loss under pricing measure, VaR/CVaR, relative skew/curvature.
- **Path layer:** scheduled events, unscheduled shocks, price/futures persistence and cross-asset transmission. If probabilities are supplied here, they are explicit real-world/judgmental scenario weights.

The optimizer may combine both into a **risk score**, but must retain the provenance of each component.

## 3. Data-health gate

Before optimization run the v2 chain checks from `scripts/optimize_butterflies.py` / `scripts/analyze_option_surface.py`:

- two-sided quote sanity;
- strike coverage;
- robust put-call-parity forward;
- parity dispersion;
- pre-repair monotonicity/convexity diagnostics;
- RND repair fraction;
- timestamp/freshness state;
- leg liquidity.

If health is `INVALID`, return `NO TRADE` rather than ranking candidates.

If health is `DEGRADED`, rank only when the weakness clearly does not affect the relevant strikes and decision. If uncertainty is material, return `NO TRADE`.

## 4. Robust forward

Prefer a parity-implied forward from multiple liquid near-ATM strikes:

`F(K) = K + (C(K) - P(K)) / DF`

Use two-sided mids when possible, filter implausible estimates and aggregate robustly. Report dispersion. Do not silently set `forward = spot` when usable parity information exists.

Use exchange futures as a cross-check, not a reason to average contradictory timestamps.

## 5. Wide-only hard constraint

Default minimum half-width:

`max(user minimum, 1.25 * ATM straddle, 1.5% * spot, 0.90 * expiry 1-sigma move, 1.25 * horizon expected move when supplied)`

Round up to the listed strike interval.

This threshold protects against attractive-looking narrow tents whose gamma/path risk is inconsistent with the user's wide-fly mandate.

## 6. Candidate centres

Generate centres near:
- parity forward;
- RND median;
- RND mode;
- real-world path expected centre when available;
- nearby liquid strikes.

Avoid a materially directional centre unless the path layer supports it and the user intentionally wants that exposure.

## 7. Actual iron-fly execution representation

For a symmetric fly `K1 < K2 < K3`, evaluate the executable structure as:

- **long K1 put**;
- **short K2 put**;
- **short K2 call**;
- **long K3 call**.

Entry credit:

`C = K2 call + K2 put - K1 put - K3 call`

Equivalent long-fly debit:

`D = W - C`, where `W = K2-K1 = K3-K2`.

Break-evens:

`K2 - C` and `K2 + C`.

Maximum profit per point = `C`; maximum loss per point = `D`.

Use bid/ask-aware marks. The call-butterfly representation is payoff-equivalent but should not replace actual-leg execution/liquidity analysis.

## 8. Surface and RND

Construct a parity-consistent OTM call curve from liquid quotes. Before extracting the RND:
- check call-price monotonicity;
- diagnose convexity violations;
- repair noisy survival probabilities monotonically;
- record how much repair was required.

Preserve tail mass rather than renormalizing only the centre.

For each candidate calculate at least:
- pricing-measure `P(loss)`;
- wing mass;
- expected loss;
- 95% VaR/CVaR;
- probabilities of losing 50%/80% of max loss when useful.

## 9. Carry/theta

Do not rank by the body option's theta.

Prefer **same-state carry** over the user's intended carry interval:

`carry = entry credit - modeled future close cost`

under the same spot/surface state, using the actual iron-fly legs.

Also aggregate live actual-leg theta when Greeks are available:

`net theta = long lower put - short body call - short body put + long upper call`

The sign convention follows the position, not individual-option theta.

Useful normalized metric:

`theta efficiency = same-state carry / equivalent debit`.

## 10. Real-world path overlay

When the market-outlook layer supplies scenarios, pass them as `path_scenarios`:

```json
[
  {"label":"base", "probability":0.55, "spot":75000, "iv_shift_vp":-0.5, "days_ahead":1},
  {"label":"adverse", "probability":0.35, "spot":74000, "iv_shift_vp":2.0, "days_ahead":1},
  {"label":"tail", "probability":0.10, "spot":72500, "iv_shift_vp":5.0, "days_ahead":1}
]
```

The optimizer revalues the four legs at the scenario horizon.

Only compute `scenario_expected_pnl_points` when explicit probabilities are supplied for all scenarios. These are **not** RND probabilities.

Even without scenario probabilities, use the worst scenario as a path-risk stress.

## 11. Carry burden

Carry burden includes:
- equivalent debit / half-width;
- estimated round-trip spread friction / debit;
- funding/margin if supplied separately.

Reject candidates whose friction is too large relative to debit or expected carry.

## 12. Liquidity filter

Check all four actual legs:
- bid/ask and spread percentage;
- OI;
- volume;
- displayed size/depth when the source provides it;
- LTP freshness versus midpoint.

Use liquidity as a hard filter and tie-break, not as a simplistic directional signal.

## 13. Combined tail score

Keep components visible internally:

- `rnd_tail_risk_score` from pricing-measure loss/wing/CVaR metrics;
- `path_tail_loss_ratio` and optional `path_expected_loss_ratio` from the separate scenario layer;
- `combined_tail_risk_score` used for Pareto ranking.

Never relabel the combined score as a literal probability.

## 14. Pareto optimization

Remove dominated candidates before ranking.

Candidate A dominates B when A has:
- theta efficiency >= B;
- carry burden <= B;
- combined tail risk <= B;

with at least one strict improvement.

Liquidity has already passed a hard filter and is used as a secondary tie-break.

Among the Pareto-efficient set, default to equal emphasis on:
- theta efficiency;
- low carry burden;
- low combined tail/path risk.

## 15. Tail-risk gate

Optimization cannot override a bad regime.

Return `NO TRADE` when:
- surface health is invalid or materially unreliable;
- a credible unpriced event/jump regime dominates;
- real-world stress can overwhelm even the wide candidates;
- execution quality is insufficient;
- domestic option quotes are stale relative to material fresher price discovery/news.

If the market is closed and the gate passes, candidates are a **pre-open watchlist** only until live quotes refresh.

## 16. Script input

The optimizer accepts normalized Dhan/NSE/BSE chain JSON:

```json
{
  "symbol": "SENSEX",
  "underlying_value": 74930.0,
  "asof": "2026-09-21",
  "expiry": "2026-09-24",
  "risk_free_rate": 0.06,
  "lot_size": 20,
  "carry_days": 1,
  "path_expected_center": 75000,
  "horizon_expected_move_points": 650,
  "min_oi": 20000,
  "max_spread_pct": 0.05,
  "path_scenarios": [],
  "chain": [
    {
      "strike": 75000,
      "call": {"bid":282.5,"ask":283.15,"iv":9.97,"oi":1097240,"volume":15865600,"greeks":{"delta":0.50,"gamma":0.00057,"theta":-53.5,"vega":35.0}},
      "put":  {"bid":399.05,"ask":400.0,"iv":14.23,"oi":793520,"volume":6367160,"greeks":{"delta":-0.50,"gamma":0.00040,"theta":-51.4,"vega":35.0}}
    }
  ]
}
```

Run:

```bash
python scripts/optimize_butterflies.py --input snapshot.json --pretty
```
