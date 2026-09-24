# Butterfly VolArb Operating Workflow

This is the human-readable operating procedure behind **Butterfly Market Outlook v2.2**.

## 1. Classify the task

- **Open butterfly before 14:45 IST:** HOLD / RECENTRE / SQUARE OFF.
- **Open butterfly at or after 14:45 IST:** CARRY / RECENTRE / SQUARE OFF.
- **No open butterfly:** ranked wide candidates or NO TRADE.

The user-facing answer stays small; the backend work does not.

## 2. Establish state and horizon

Record:
- current IST clock/session;
- index, expiry, exact geometry, quantities, and broker position truth;
- intended exit/review horizon;
- trading sessions/calendar time remaining;
- next actionable exit and untradeable-window duration when crossing market close;
- whether expiry-exit and overnight gates are active.

## 3. Acquire one coherent snapshot

Prefer:
1. Dhan for positions and the structured full option chain;
2. NSE/BSE for official validation/fallback;
3. NSE IX for GIFT Nifty;
4. Reuters/primary sources for decision-relevant event context;
5. cross-assets only when they materially affect Indian index path risk.

Fetch the full expiry once and reuse it.

## 4. Data-health gate

Before interpreting theta, skew, or probabilities, validate:
- two-sided quote sanity;
- strike coverage;
- parity consistency and forward;
- monotonicity/convexity and RND repair intensity;
- quote freshness versus later futures/news;
- actual four-leg liquidity.

States: **HEALTHY / DEGRADED / STALE / INVALID**.

`INVALID` blocks new entry.

## 5. Build the canonical MarketState

Track:
- clock/session/horizon;
- data health;
- spot/forward/futures/GIFT/VIX when relevant;
- surface/skew/curvature/term structure/RND;
- market-regime state;
- event clock and real-world scenarios;
- position/candidate economics;
- previous/current decision.

Follow-up reviews compare state changes rather than restarting from scratch.

## 6. Build the option-implied layer

Using the entire relevant expiry, derive:
- robust parity forward;
- ATM strike, straddle, and IV;
- skew/curvature;
- approximate 25-delta RR/BF;
- front-versus-next expiry IV;
- arbitrage-repaired risk-neutral terminal distribution;
- q10/median/q90/modal region;
- executable leg liquidity.

RND remains a **pricing-measure distribution**, not a physical forecast.

## 7. Build the real-world path/event layer

Search through the intended exit horizon for:
- scheduled macro/policy events;
- unscheduled geopolitical/policy shocks;
- domestic price persistence;
- oil, INR, U.S. rates/equities, and Asia when relevant;
- material index-heavyweight news.

Keep judgmental real-world scenarios separate from risk-neutral probabilities.

## 8. Classify the market regime

Run the v2.2 regime engine before any actionable overnight carry decision.

States:
- **CALM_CARRY** — realized/gap/event risk jointly quiet.
- **TRANSITION** — mixed or changing conditions.
- **LATENT_JUMP_RISK** — implied vol looks calm but event/tail hazard is high.
- **ACTIVE_STRESS** — realized/tail/implied stress is already high.
- **UNKNOWN** — insufficient inputs.

A low India VIX alone never establishes `CALM_CARRY`.

## 9. Apply the overnight carry gate

If the trade crosses the close, evaluate:
- 20–30 recent close-to-open gaps;
- p80/p90 absolute gap and tail-gap frequency;
- current spot to nearest break-even buffer;
- gap-gamma drag versus same-state next-open harvest;
- regime-adjusted OCR threshold;
- scheduled/unscheduled events in the untradeable window;
- broker/RMS feasibility and auto-squareoff risk;
- full-reprice ±1.0/1.5/2.0 straddle spot/IV stresses.

For new expiry-eve entry/recenter/rotation:
- `LATENT_JUMP_RISK`, `ACTIVE_STRESS`, or `UNKNOWN` blocks overnight initiation;
- `TRANSITION` requires materially stronger OCR and break-even buffer;
- missing recent gap history or unvalidated broker feasibility also blocks.

Intraday butterflies remain possible when the ordinary data/tail/liquidity gates pass.

## 10. Existing-position analysis

Calculate when data permit:
- entry credit / equivalent long-fly debit;
- executable close cost;
- bankable P&L;
- break-evens and wing distances;
- actual-leg delta/gamma/theta/vega;
- RND and real-world scenario mapping;
- unwind friction.

### Near expiry

With <=2 trading sessions or roughly <=36 hours remaining, compare:
- Dynamic Harvest Saturation;
- Remaining Static Harvest;
- break-even/straddle buffer;
- gamma/path stress;
- overnight regime and next-open risk when carry is contemplated.

Headline theta is never enough by itself.

## 11. Candidate search

Default to **wide symmetric iron butterflies**.

Candidates must:
- use forward-aware centering;
- respect the dynamic width floor;
- use executable four-leg quotes;
- compute same-state carry and actual-leg Greeks;
- include RND tail metrics and real-world stress;
- include regime and overnight penalties when applicable;
- remove Pareto-dominated candidates.

Rank survivors by theta efficiency, low carry burden, and low combined tail/path risk. Liquidity is a hard filter/tie-break.

## 12. Recenter gate

Never recenter merely because spot moved.

RECENTRE requires:
- range thesis still intact;
- healthy data;
- materially better alignment/tail risk;
- acceptable close-and-reopen friction;
- enough time to re-harvest;
- no worse regime/event state.

## 13. Decision precedence

Apply in this order:

1. data gate;
2. market-regime gate;
3. recent realized-gap gate;
4. broker/RMS feasibility;
5. overnight event-latency/full-reprice stress gate;
6. hard event/tail/liquidity override;
7. expiry-exit hard gates;
8. recenter gate;
9. ordinary HOLD/CARRY or candidate ranking.

Theta never overrides a higher-priority risk gate.

## 14. Logging and calibration

Persist:
- every completed outlook/review to `market-outlook/YYYY-MM-DD.md`;
- confirmed trade lifecycle facts to `trade-log/`;
- closed-trade episodes to `trade-log/episodes.jsonl`.

Do not infer missing broker facts.

Threshold changes require explicit review and regression testing; never auto-fit from a small sample.

## Executable components

The production source is `skill/butterfly-market-outlook/`. Key scripts include:

- `classify_market_regime.py`
- `analyze_option_surface.py`
- `analyze_position.py`
- `compare_market_states.py`
- `evaluate_expiry_exit.py`
- `evaluate_overnight_carry.py`
- `evaluate_recentre.py`
- `optimize_butterflies.py`
- `summarize_trade_log.py`

The control-plane source of truth remains `skill/butterfly-market-outlook/SKILL.md`.
