# Market Regime Engine - v2.4

Use this engine before any overnight butterfly decision and as a contextual input to intraday candidate ranking. The purpose is to distinguish a genuinely quiet carry environment from a market that only **looks** quiet in implied volatility while jump/event risk is elevated.

## Core idea

A short-gamma butterfly does not merely depend on today's IV level. Its economics depend on the **conditional distribution of future path and jumps**. Volatility and jumps cluster, and rare-event compensation changes through time. Therefore the same butterfly geometry can be attractive in one regime and unattractive in another.

A low volatility index is not by itself a `CALM_CARRY` signal. The dangerous state is:

`low implied stress + elevated calibrated event/tail hazard = LATENT_JUMP_RISK`

This is the regime in which overnight short gamma can be most deceptively attractive because premium may look easy while the market is exposed to discontinuous information arrival during the untradeable window.

## Research basis

The regime engine is consistent with several established findings:

- Bollerslev and Todorov (2011), *Journal of Finance*, show that rare-event compensation is large and strongly time-varying; tail risk is not summarized by ordinary volatility alone.
- Zhao et al. (2024), *Journal of Empirical Finance*, document volatility clustering in both intraday and overnight returns across global equity markets, with overnight clustering more pronounced.
- Broadie, Chernov and Johannes (2009), *Review of Financial Studies*, show that jump-risk premia and estimation risk are central to understanding market-neutral option returns.
- Cboe's historical volatility reviews show that short-premium strategies tend to work well through extended calm realized-volatility periods and can suffer sharply when the regime breaks.

Treat these as motivation for a state-dependent risk process, not as evidence that a particular trade has positive expected value.

## Inputs

Build regime inputs from one coherent time window. Prefer percentiles relative to the same underlying's own history rather than absolute cutoffs.

### Endogenous path state

Estimate where possible:

- 20-day realized-volatility percentile versus roughly one year;
- rolling 20-30-open absolute-gap p90 percentile versus history;
- tail-gap-frequency percentile, such as frequency of `|gap| >= 0.50%`;
- intraday-range percentile;
- option-implied volatility / India VIX percentile;
- downside-skew stress percentile;
- front-versus-next-expiry term-structure stress percentile.

### Exogenous hazard state

**Primary source:** the normalized `market-news-signal-filter` packet from `news-signal-integration.md`. Do not independently browse and score current articles here when the child skill is available.

The classifier accepts the child packet as `news_filter` and maps its aggregate state, calibrated gap risk, butterfly relevance, and event hazards into the event-hazard leg. Legacy 0/1/2/3 fields remain supported for compatibility and explicit non-news hazards.

Score any remaining explicit hazard overrides on `0 / 1 / 2 / 3`:

- `0` - quiet / no material active catalyst;
- `1` - ordinary background risk;
- `2` - meaningful active uncertainty that can plausibly move the index;
- `3` - rapidly evolving or unresolved shock with material overnight transmission risk.

Assess:

- geopolitical / military-conflict risk;
- macro and central-bank policy risk;
- oil, INR, global-rate and cross-asset stress relevant to India;
- unscheduled news uncertainty;
- scheduled events inside the next untradeable window.

Raw-source selection, novelty/sensationalism filtering, and calibrated India transmission sensitivity are owned by `market-news-signal-filter`. This regime engine consumes that result. Do not convert political opinions or rhetorical language into risk scores, and do not let market price reactions retroactively change the truth/evidence score of a story.

## Deterministic classifier

Run:

```bash
python scripts/classify_market_regime.py --input regime_snapshot.json --pretty
```

The classifier returns one of five states.

### `CALM_CARRY`

Jointly quiet realized volatility, gaps and event hazard. Implied volatility need not be high, but there is no obvious hidden catalyst.

This is the preferred environment for butterflies, **provided** the option credit still compensates for residual risk and execution friction. Calm is necessary, not sufficient.

### `TRANSITION`

Mixed signals or a changing regime. Examples: realized volatility is still modest but gaps are rising; VIX is moving higher; oil/rates are becoming unstable; or news hazard is no longer trivial.

Overnight carry is allowed only with tighter stress-efficiency and break-even-buffer thresholds.

### `LATENT_JUMP_RISK`

Implied volatility looks relatively calm while event hazard, tail-gap frequency or recent gap severity is elevated.

This is a **complacency mismatch**. For next-session-expiry butterflies, new overnight entry/recenter/rotation is blocked. Existing positions require materially stronger next-open stress efficiency and break-even buffers.

### `ACTIVE_STRESS`

Realized volatility, tail gaps and/or implied stress are already high. The market is openly turbulent rather than deceptively calm.

Next-session-expiry overnight short-gamma initiation is blocked. Intraday butterflies may still be considered only when the ordinary data/tail/liquidity gates pass and the holding window is explicitly intraday.

### `UNKNOWN`

Insufficient regime inputs. A new expiry-eve overnight carry cannot be approved from an unclassified regime.

## Regime-adjusted overnight thresholds

The deterministic defaults are:

| Regime | New expiry-eve carry | Minimum `OCR_1_5` | Maximum p90-gap / nearest-BE-buffer ratio |
|---|---|---:|---:|
| `CALM_CARRY` | Allowed | 0.50 | 1.00 |
| `TRANSITION` | Allowed, cautious | 1.00 | 0.80 |
| `LATENT_JUMP_RISK` | Blocked | 1.25 for existing carry | 0.65 |
| `ACTIVE_STRESS` | Blocked | 1.50 for existing carry | 0.50 |
| `UNKNOWN` | Blocked | 1.25 | 0.65 |

These are conservative operating thresholds for the candidate engine, not estimated structural parameters. Recalibrate only after a sufficiently large post-trade sample.

## Important interaction with implied volatility

Do not equate a high VIX with a bad butterfly regime or a low VIX with a good one.

- A high IV regime may offer large premium but also large realized/jump risk.
- A low IV regime may be excellent if realized and event risk are genuinely low.
- A low IV regime may be especially dangerous if event risk is high because the market may be underpricing discontinuity risk.

The relevant question is:

`Is the premium/carry sufficient for the conditional path + gap + event regime we are actually in?`

## Current-regime workflow

For every actionable overnight review:

1. Measure recent realized/gap state.
2. Measure option-implied state.
3. Invoke `market-news-signal-filter` once for the relevant horizon and normalize the result using `news-signal-integration.md`.
4. Use oil, INR, rates, global equities and GIFT Nifty as live confirmation of the child-identified channels, not as a second raw-news classifier.
5. Set `news_filter_required=true` for actionable overnight decisions and run `classify_market_regime.py`.
6. Feed the returned regime object plus the same news packet into `evaluate_overnight_carry.py` or `optimize_butterflies.py`.
7. Apply regime-adjusted thresholds before theta/Pareto ranking.

Do not change the regime merely because spot had one quiet session. Require a meaningful change in the underlying path/event state.
