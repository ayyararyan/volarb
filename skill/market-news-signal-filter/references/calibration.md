# Current India News-to-Market Calibration

## Calibration metadata

- Calibration as of: 2026-09-24
- Core price window: 2025-09-24 through 2026-09-24
- NIFTY 50 and SENSEX cleaned daily OHLC observations: 245 each
- BANKNIFTY cleaned OHLC observations used for percentile estimation: 225 through 2026-08-21, supplemented with recent September close-to-close event checks
- Target use: near-term and overnight NIFTY, SENSEX, and BANKNIFTY movement hazard for short-gamma/butterfly workflows
- Raw data retention: none. Keep only these parameters and calibration metadata.

These parameters are empirical hazard priors, not expected returns, forecasts, or causal coefficients.

## Empirical movement anchors

Use absolute gap percentiles to translate calibrated event hazard into intuitive movement buckets.

| Index | Median abs gap | 75th pct | 90th pct | 95th pct | 99th pct |
|---|---:|---:|---:|---:|---:|
| NIFTY | 0.23% | 0.47% | 0.83% | 1.30% | 2.50% |
| SENSEX | 0.24% | 0.52% | 0.86% | 1.35% | 3.02% |
| BANKNIFTY | 0.24% | 0.53% | 0.94% | 1.51% | 3.24% |

Use absolute close-to-close percentiles as a secondary same-session scale.

| Index | Median abs daily move | 75th pct | 90th pct | 95th pct | 99th pct |
|---|---:|---:|---:|---:|---:|
| NIFTY | 0.48% | 0.83% | 1.29% | 1.71% | 2.58% |
| SENSEX | 0.49% | 0.82% | 1.29% | 1.71% | 2.51% |
| BANKNIFTY | 0.50% | 0.98% | 1.71% | 2.33% | 3.65% |

The BANKNIFTY gap/daily percentiles use the 225-session cleaned OHLC subsample through 2026-08-21. Do not overstate precision beyond two decimals.

### Gap-risk mapping

For the target index:

- `none`: no credible movement channel, or expected movement materially below the median absolute gap.
- `low`: around or below the median absolute gap.
- `moderate`: approximately median to 75th-percentile hazard.
- `high`: approximately 75th to 95th-percentile hazard.
- `extreme`: credible hazard at or beyond the 95th-percentile scale, or a tail event with nonlinear interaction risk.

Use percentile language instead of pretending to know an exact gap forecast.

## Current channel sensitivity multipliers

Neutral sensitivity is 1.00. Apply these only after the information itself has been classified.

| Channel | NIFTY | SENSEX | BANKNIFTY | Current state | Confidence |
|---|---:|---:|---:|---|---|
| OIL_ENERGY | 1.35 | 1.35 | 1.20 | STRESSED | high |
| GEOPOLITICAL_OPERATIONAL | 1.30 | 1.30 | 1.25 | STRESSED | high |
| GLOBAL_RATES | 0.95 | 0.95 | 1.00 | HIGH | medium |
| GLOBAL_RISK_EQUITIES | 0.80 | 0.80 | 0.80 | HIGH | medium |
| INR_FX | 1.05 | 1.05 | 1.10 | HIGH | medium |
| RBI_MONETARY_LIQUIDITY | 1.10 | 1.05 | 1.35 | HIGH | medium-high |
| BANKING_REGULATION | 0.90 | 0.90 | 1.50 | HIGH for BANKNIFTY | medium-high |
| TRADE_TARIFF_POLICY | 1.35 | 1.30 | 1.25 | HIGH | medium-high |
| FISCAL_TAX_MARKET_STRUCTURE | 1.20 | 1.20 | 1.25 | NORMAL-HIGH | medium |
| FLOWS_FII_DII | 0.80 | 0.80 | 0.90 | NORMAL | medium |
| INDEX_HEAVYWEIGHT | 1.00 | 1.10 | 1.25 if financial heavyweight | NORMAL | medium |
| OTHER_DOMESTIC_MACRO | 1.00 | 1.00 | 1.00 | NORMAL | low-medium |

### Interpretation

- A multiplier above 1 means the index has recently shown above-neutral movement sensitivity to that channel.
- A multiplier below 1 means the channel is usually confirmation rather than a dominant standalone driver.
- A multiplier must not be used to infer direction without a directional transmission mechanism.
- Expected or fully priced policy decisions should be downweighted through novelty/surprise before the multiplier is applied.

## Empirical event anchors behind the current calibration

These are compact calibration anchors, not a raw event corpus.

- 2025-09-18: an expected 25 bp Fed cut produced only a modest positive Indian-equity response. Lesson: scheduled global rates news is highly surprise-dependent.
- 2025-10-01: RBI banking reforms produced a stronger BANKNIFTY response than broad-index response. Lesson: direct domestic banking/liquidity policy has a BANKNIFTY-specific beta.
- 2025-11-26: Fed cut expectations plus falling crude and positive global markets produced a broad roughly 1.2% rally across NIFTY, SENSEX, and BANKNIFTY. Lesson: aligned global rates plus oil can matter broadly even without a single dramatic headline.
- 2026-02-03: clarity on the India-US trade agreement generated a roughly 4.5%-4.9% positive opening gap across the three indices. Lesson: hard operational trade-policy resolution can dominate ordinary macro cues.
- 2026-03-02, 2026-03-09, 2026-03-19, 2026-03-23, and 2026-03-30: escalating Middle-East conflict, crude spikes, INR pressure, global risk-off conditions, and on some dates hawkish rates or banking-specific policy produced repeated tail-scale negative gaps/moves. Lesson: oil and operational geopolitics became a stressed regime rather than isolated events.
- 2026-04-01 and 2026-04-08: de-escalation/ceasefire news and falling oil generated very large positive gaps, including roughly 3%-4% broad-index gaps on April 8. Lesson: the same stressed channel works in both directions when the state genuinely changes.
- 2026-04-13: failed peace talks and oil above the psychologically important $100 area again produced a large negative gap. Lesson: failed resolution is itself new information when it changes the probability tree.
- 2026-06-12 and 2026-06-15: peace-deal/Hormuz reopening hopes produced strong positive gaps. Lesson: operational supply-route information deserves more weight than rhetoric.
- 2026-07-08: renewed geopolitical escalation and crude strength produced a roughly 2% broad selloff and a larger BANKNIFTY decline. Lesson: intraday re-pricing can remain large even when the opening gap is modest.
- 2026-09-24: oil, US-rate pressure, global risk-off cues, and domestic insurance-distribution regulation aligned; NIFTY, SENSEX, and BANKNIFTY closed roughly 1.6%, 1.7%, and 2.0% lower, respectively. Lesson: independent aligned channels can create nonlinear short-gamma risk.

## Interaction multipliers

Apply interactions only after removing duplicate stories and confirming that channels are independent.

| Interaction | Multiplier / rule |
|---|---|
| OIL_ENERGY + GEOPOLITICAL_OPERATIONAL, aligned | x1.25 movement hazard |
| OIL_ENERGY + GLOBAL_RATES, aligned inflation/risk-off direction | x1.20 |
| RBI_MONETARY_LIQUIDITY + BANKING_REGULATION on BANKNIFTY | x1.20 |
| Two independent broad channels aligned | x1.15 unless a more specific interaction already applies |
| Three or more independent broad channels aligned | x1.35, cap total calibrated multiplier at 2.25 |
| Opposing directional channels | do not stack direction; retain the higher volatility hazard |
| Duplicate articles within one channel | no multiplier increase |
| Weak rumor + strong market attention | apply attention/uncertainty hazard, not fundamental-information multiplier |

Never multiply every article. Multiply independent economic channels.

## Current-regime interpretation

As of 2026-09-24:

- Oil/energy: STRESSED. Physical supply, shipping-route, sanctions, and war developments deserve first-order attention.
- Operational geopolitics: STRESSED. Rhetoric alone remains lower-quality than action, but operational state changes have repeatedly generated tail-scale Indian moves.
- Global rates: HIGH. Rate news matters most through surprise, inflation, oil, and the dollar rather than as a standalone headline count.
- INR/FX: HIGH as an amplifier when oil and rates move against India.
- Domestic banking/regulatory policy: HIGH for BANKNIFTY and financial-heavyweight transmission.
- Global equity direction: HIGH as confirmation, but usually below oil, direct Indian policy, or operational geopolitics as a standalone causal prior.
- FII/DII flow headlines: NORMAL. Treat them mainly as persistence/liquidity context unless unusually large and corroborated by price breadth.

## Guardrails

- Do not use these multipliers as return forecasts.
- Do not infer causality from same-day co-movement without timing and transmission evidence.
- Do not increase evidence quality because prices moved in the predicted direction.
- When one month is dominated by a single conflict or theme, let recency affect regime state but shrink structural multipliers toward 1.00.
- Sparse channels must remain close to 1.00 until enough independent event windows accumulate.
- Recalibrate monthly using `monthly-recalibration.md`.
