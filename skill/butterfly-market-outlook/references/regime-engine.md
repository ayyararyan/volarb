# Market Regime Engine - v2.2

Use this engine before any overnight butterfly decision and as a contextual input to intraday candidate ranking. The purpose is to distinguish a genuinely quiet carry environment from a market that only **looks** quiet in implied volatility while jump/event risk is elevated.

## Core idea

A short-gamma butterfly does not merely depend on today's IV level. Its economics depend on the **conditional distribution of future path and jumps**. Volatility and jumps cluster, and rare-event compensation changes through time. Therefore the same butterfly geometry can be attractive in one regime and unattractive in another.

A low volatility index is not by itself a `CALM_CARRY` signal. The dangerous state is:

`low implied stress + elevated event/tail hazard = LATENT_JUMP_RISK`

This is the regime in which overnight short gamma can be most deceptively attractive because premium may look easy while the market is exposed to discontinuous information arrival during the untradeable window.

## Research basis

The regime engine is consistent with several established findings:

- Bollerslev and Todorov (2011), *Journal of Finance*, show that rare-event compensation is large and strongly time-varying; tail risk is not summarized by ordinary volatility alone.
- Zhao et al. (2024), *Journal of Empirical Finance*, document volatility clustering in both intraday and overnight returns across global equity markets, with overnight clustering more pronounced.
- Broadie, Chernov and Johannes (2009), *Review of Financial Studies*, show that jump-risk premia and estimation risk are central to understanding market-neutral option returns.
- Cboe historical volatility reviews show that short-premium strategies tend to work well through extended calm realized-volatility periods and can suffer sharply when the regime breaks.

Treat these as motivation for a state-dependent risk process, not as evidence that a particular trade has positive expected value.

## Inputs

Prefer percentiles relative to the same underlying's own history. Measure realized-volatility percentile, rolling gap-tail percentile, tail-gap-frequency percentile, intraday-range percentile, implied-volatility/VIX percentile, skew stress and term-structure stress.

Score exogenous hazards on `0 / 1 / 2 / 3` for geopolitical conflict, macro/policy risk, oil/INR/rates stress, unscheduled news uncertainty and scheduled events inside the next untradeable window. Use Reuters and primary/official sources first. Score observable uncertainty, market transmission channels and timing rather than political rhetoric.

## States

### `CALM_CARRY`
Jointly quiet realized volatility, gaps and event hazard. This is the preferred environment for butterflies, provided option credit still compensates for residual risk and friction.

### `TRANSITION`
Mixed or changing signals. Overnight carry remains possible only with tighter stress-efficiency and break-even-buffer thresholds.

### `LATENT_JUMP_RISK`
Implied volatility looks relatively calm while event hazard, tail-gap frequency or recent gap severity is elevated. New next-session-expiry overnight entry/recenter/rotation is blocked.

### `ACTIVE_STRESS`
Realized volatility, tail gaps and/or implied stress are already high. New next-session-expiry overnight short-gamma initiation is blocked.

### `UNKNOWN`
Insufficient regime inputs. A new expiry-eve overnight carry cannot be approved.

## Deterministic thresholds

| Regime | New expiry-eve carry | Minimum `OCR_1_5` | Maximum p90-gap / nearest-BE-buffer ratio |
|---|---|---:|---:|
| `CALM_CARRY` | Allowed | 0.50 | 1.00 |
| `TRANSITION` | Allowed, cautious | 1.00 | 0.80 |
| `LATENT_JUMP_RISK` | Blocked | 1.25 for existing carry | 0.65 |
| `ACTIVE_STRESS` | Blocked | 1.50 for existing carry | 0.50 |
| `UNKNOWN` | Blocked | 1.25 | 0.65 |

These are conservative operating thresholds, not structural estimates. Recalibrate only after a sufficiently large post-trade sample.

## Workflow

Run:

```bash
python scripts/classify_market_regime.py --input regime_snapshot.json --pretty
```

For every actionable overnight review: measure recent realized/gap state; measure option-implied state; search fresh news/event risk through the next actionable exit; map oil, INR, rates, global equities and GIFT Nifty when relevant; classify the regime; feed the result into the overnight evaluator/optimizer; then apply regime-adjusted thresholds before theta/Pareto ranking.

Do not change the regime merely because spot had one quiet session. Require a meaningful change in the underlying path/event state.
