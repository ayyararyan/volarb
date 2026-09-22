# Butterfly VolArb Operating Workflow

This document is the human-readable operating procedure behind the Butterfly Market Outlook v2 skill.

## 1. Classify the task

There are three front-end branches:

- **Open butterfly before 14:45 IST:** decide exactly one of HOLD / RECENTRE / SQUARE OFF.
- **Open butterfly at or after 14:45 IST:** decide exactly one of CARRY / RECENTRE / SQUARE OFF.
- **No open butterfly / candidate search:** return up to three wide candidates or NO TRADE.

The final answer is intentionally tiny. The work underneath it is not.

## 2. Establish clock, position, expiry and horizon

Record internally:

- current Asia/Kolkata date/time and market session;
- index and exact option expiry;
- exact four-leg geometry when a position exists;
- intended exit/review horizon;
- trading sessions and calendar time remaining;
- whether the near-expiry exit layer is active.

Dhan account state is the preferred source of truth for live positions.

## 3. Acquire one coherent market snapshot

Prefer:

1. Dhan positions and structured option chain;
2. NSE/BSE official validation and fallback;
3. NSE IX for GIFT Nifty;
4. Reuters and primary/high-quality sources for fresh event context;
5. relevant cross-assets only when they materially affect the path distribution.

Fetch the full relevant expiry once per pass and reuse it. Pull the next expiry when term structure matters.

## 4. Run the data-health gate first

Before interpreting skew, theta or probabilities, validate:

- two-sided quote sanity;
- strike coverage;
- parity consistency and robust parity-implied forward;
- raw monotonicity / convexity and RND repair intensity;
- timestamp consistency between the option surface and later futures/GIFT/news;
- actual leg liquidity and quote quality.

Health states:

- **HEALTHY** — optimization allowed;
- **DEGRADED** — broad context usable; fine ranking only if weakness is immaterial;
- **STALE** — later price discovery/news has superseded the tradable surface;
- **INVALID** — do not optimize or infer terminal probabilities.

New entry is blocked on INVALID data.

## 5. Build the canonical MarketState

The state combines:

- clock/session/horizon;
- data health/freshness;
- spot, forward, futures, GIFT and VIX when relevant;
- surface, skew, curvature and term structure;
- risk-neutral terminal distribution;
- scheduled and unscheduled event clock;
- real-world path regime/scenarios;
- position or candidate economics;
- prior decision and current decision fields.

Follow-up reviews compare the current state with the previous state instead of restarting the narrative.

## 6. Build the option-implied layer

Use the entire relevant expiry and parity-consistent OTM pricing.

Derive:

- robust forward;
- ATM strike, straddle and IV;
- local skew and curvature;
- approximately 25-delta risk reversal and butterfly;
- front-versus-next-expiry IV;
- arbitrage-repaired risk-neutral terminal distribution;
- q10 / median / q90 and modal region;
- leg liquidity and quote quality.

The RND is a **pricing-measure distribution**. It is used for geometry, relative wing mass and tail compensation. It is not called the true physical probability of expiry outcomes.

## 7. Build the real-world path/event layer separately

Search from now through intended exit/expiry for decision-relevant information:

- scheduled macro or policy events;
- unscheduled geopolitical / policy shocks;
- domestic spot/futures/GIFT persistence;
- oil, INR, U.S. rates/equities and Asia when relevant;
- material index-heavyweight news.

Build benign/base, adverse-plausible and tail/stress scenarios. Judgmental physical-world weights, when used, remain explicitly separate from RND probabilities.

## 8A. Existing-position analysis

Reconstruct and verify exact legs and ratios.

When data permit calculate:

- entry credit / equivalent long-fly debit;
- executable close cost;
- bankable P&L versus expiry payoff;
- break-evens and wing distances;
- actual-leg net delta, gamma, theta and vega;
- RND mapping to body/break-evens/wings;
- real-world scenario mapping;
- liquidity and unwind friction.

### Near expiry

With roughly <=2 trading sessions or <=36 calendar hours remaining, activate the expiry-exit layer.

Compare:

- Dynamic Harvest Saturation;
- Remaining Static Harvest;
- break-even / straddle buffer;
- gamma stress and plausible path risk.

Original maximum-profit capture is only a secondary reference. High theta by itself is not a HOLD/CARRY signal.

## 8B. Candidate search

Default to **wide symmetric iron butterflies**.

Candidate generation should:

- use forward-aware centering;
- enforce a dynamic wide-width floor;
- use actual four-leg execution quotes;
- compute same-state carry and actual-leg Greeks;
- calculate RND P(loss), wing mass, expected loss, VaR/CVaR;
- incorporate real-world scenario MTM stress when defensible;
- include close/open friction and liquidity;
- remove Pareto-dominated candidates.

Among Pareto-efficient flies, give equal conceptual emphasis to:

1. theta efficiency;
2. low carry burden;
3. low combined tail/path risk.

Liquidity is a hard filter and tie-break, not an afterthought.

## 9. Recenter gate

Never recenter simply because spot moved.

RECENTRE requires all of the following:

- the range-bound/choppy thesis still survives;
- data are healthy enough;
- body alignment and/or tail risk improves materially;
- close-and-reopen friction is acceptable;
- enough time remains to re-harvest carry;
- event/path state is not worse.

Near expiry the hurdle is deliberately higher.

## 10. Decision precedence

Apply in this order:

1. data gate;
2. hard event/tail/liquidity override;
3. expiry-exit hard gates;
4. recenter gate;
5. ordinary HOLD/CARRY or candidate ranking.

A lower-priority theta benefit never overrides a higher-priority risk gate.

## 11. Review timing

For HOLD/CARRY, choose the earliest useful observation point among:

- next scheduled event;
- next price-discovery session;
- meaningful MarketState change;
- expiry gamma cadence;
- 14:45 carry gate / close.

## 12. Post-trade learning

After a trade is fully closed, store one episode containing:

- geometry and fills when available;
- entry and exit market state;
- decision sequence;
- realized P&L;
- slippage;
- forecast / tail misses;
- profit give-back;
- recenter incremental P&L only where a defensible counterfactual exists.

Periodically summarize the episode log. Do **not** auto-change live thresholds from a small sample. Calibration changes require explicit review, regression testing and a new skill version.

## Executable components

See `skill/butterfly-market-outlook/scripts/` for:

- `analyze_option_surface.py`
- `analyze_position.py`
- `compare_market_states.py`
- `evaluate_expiry_exit.py`
- `evaluate_recentre.py`
- `fetch_nse_option_chain.py`
- `normalize_dhan_option_chain.py`
- `optimize_butterflies.py`
- `summarize_trade_log.py`

The source-of-truth control plane remains `skill/butterfly-market-outlook/SKILL.md`.
