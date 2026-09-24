# Butterfly Engine v2.1 Candidate Architecture

This is the control architecture behind every live butterfly review and candidate search. The user-facing format remains intentionally tiny; all complexity stays in the backend.

## Design principles

1. **Separate price-implied state from real-world judgment.** Risk-neutral distributions (RNDs) describe option prices under the pricing measure; they are not literal forecasts. Use them for relative pricing, geometry and tail compensation. Use the event/path layer for real-world carry judgment.
2. **Code fragile arithmetic; let the model interpret.** Forward extraction, quote checks, RND construction, Greeks aggregation, payoff math, candidate enumeration, exit diagnostics and recenter diagnostics should be deterministic whenever inputs permit.
3. **Risk before reward.** Data health and tail/event gates run before theta optimization.
4. **State before narrative.** Build one canonical MarketState object, compare it with the previous review, and reason from the change in state rather than recreating a story from scratch.
5. **No false precision.** If data are stale, repaired heavily, missing, or conflicting, downgrade the state and refuse to turn an unreliable surface into an executable recommendation.
6. **Execution is part of strategy economics.** Use the actual iron-fly legs (lower put, body call+put, upper call) for bid/ask, OI, volume, slippage and live Greeks.
7. **Near expiry, remaining harvest matters more than headline theta.** Apply the Dynamic Harvest Saturation / remaining-harvest-versus-gamma framework.
8. **Overnight carry is a next-exit problem.** When the home market will be closed, model next-actionable-exit MTM under joint gap/IV/execution stress before theta optimization.
9. **Recent opening-gap risk is state-dependent.** Carry must also pass a rolling realized-gap regime gate using recent close-to-open gaps, current-spot-to-break-even buffer and gap-gamma burden.
10. **Broker feasibility is part of the state.** A defined-risk payoff does not eliminate RMS/auto-squareoff risk; new expiry-eve overnight entries require validated broker feasibility.
11. **Every closed trade can become a calibration episode.** Store forecasts and outcomes separately from the live decision logic; use them to measure whether rules add value before changing thresholds.

## Modules

### 1. Orchestrator / clock

Determine:
- index and expiry;
- current IST time and exchange session;
- open-position vs candidate-search mode;
- intended holding/review horizon;
- whether the expiry-exit layer is active;
- whether this is a first review or a follow-up with a prior state.

The orchestrator alone chooses which modules run. It does not calculate option metrics itself.

### 2. Data gateway

Source hierarchy:
- Dhan: positions and structured option chain when healthy;
- NSE/BSE: official validation/fallback and exchange status;
- NSE IX: GIFT Nifty;
- Reuters/primary/high-quality reporting: current event and cross-asset context.

Fetch one option-chain snapshot per expiry per decision pass and reuse it.

### 3. Data-health gate

Before interpreting the chain, validate:
- quote sanity (`bid <= ask`, non-negative prices, usable mids);
- strike coverage and spacing;
- put-call parity consistency and robust parity-implied forward;
- call monotonicity / convexity diagnostics before repair;
- RND repair intensity;
- timestamps and freshness relative to spot/futures/GIFT/news;
- leg-level liquidity for any actual or proposed fly.

Classify the option state as:
- `HEALTHY`: suitable for live optimization;
- `DEGRADED`: usable for broad risk context but not fine ranking unless the weakness is immaterial to the chosen legs;
- `STALE`: valid historical surface but superseded by fresher price discovery/news;
- `INVALID`: do not optimize or infer probabilities from it.

A candidate search cannot pass the tail/data gate with `INVALID` data. `STALE` data may support a pre-open watchlist only when explicitly identified as such.

### 4. MarketState builder

Create the canonical state described in `market-state.md` from:
- price discovery;
- full surface diagnostics;
- event clock;
- real-world path scenarios;
- current position/candidate state;
- data health.

If a previous review exists, run `scripts/compare_market_states.py` and focus the decision layer on meaningful changes.

### 5. Surface / distribution engine

Run on the full relevant expiry and next expiry when useful:
- robust parity forward;
- ATM strike, straddle and ATM IV;
- local skew and curvature;
- approximately 25-delta risk reversal / butterfly;
- term structure;
- arbitrage-repaired risk-neutral terminal distribution;
- RND q10 / median / q90 / mode;
- wing and break-even price-implied masses;
- liquidity and quote quality.

The surface engine never claims the RND is a physical forecast.

### 6. Event / path engine

Build a separate real-world path overlay from:
- scheduled events before intended exit/expiry;
- unscheduled geopolitical/policy/corporate shocks;
- spot/futures/GIFT direction and persistence;
- oil, FX, rates and global risk confirmation when relevant;
- concentration in large index constituents when material.

Create at least:
- benign/base path;
- adverse but plausible path;
- tail/stress path.

Use probabilities only when defensible. If judgmental scenario weights are used, label them internally as subjective and never mix them with RND probabilities as though they were the same measure.

### 6A. Overnight event-latency / broker-feasibility engine

When the intended hold crosses market close, run the v2.1 overnight gate before candidate ranking or a carry decision. Track the next actionable exit, a rolling 20-30-open realized-gap regime, current-spot-to-break-even buffer, gap-gamma burden, untradeable-window events, broker feasibility, and full-reprice +/-1.0/1.5/2.0 straddle joint spot/IV stresses. See `overnight-carry-gate.md` and `scripts/evaluate_overnight_carry.py`.

A new next-session-expiry entry/recenter/rotation requires broker status `PASS`; `UNKNOWN` is not enough. After market close, the operational state is `LOCKED_OVERNIGHT`, not a fresh carry decision.

### 7. Position engine

For an existing fly:
- reconstruct exact legs, entry and current executable close marks;
- calculate break-evens, payoff, spot/forward/body distances and net Greeks;
- map RND and path scenarios onto the body, break-evens and wings;
- when near expiry, run `evaluate_expiry_exit.py`;
- compute whether the current position is harvest-dominated or gamma/path-dominated.

### 8. Candidate optimizer

For a new fly:
- apply the tail/data gate first;
- enumerate only wide symmetric candidates by default;
- center candidates near parity forward, RND median/mode and the real-world expected path center;
- use actual iron-fly execution legs for credit, slippage, OI, volume and Greeks;
- compute price-implied tail metrics from the RND;
- compute same-state carry/theta and, when supplied, path-scenario mark-to-market outcomes;
- remove Pareto-dominated candidates;
- rank the Pareto set on theta efficiency, low carry burden and combined tail/path risk, with liquidity as a hard filter and tie-break.

Use `scripts/optimize_butterflies.py` whenever chain data are structured enough.

### 9. Recenter evaluator

RECENTRE is a capital reallocation, not an emotional response to drift.

Run `scripts/evaluate_recentre.py` when the current distribution/body alignment has moved materially. Compare:
- alignment improvement;
- price-implied tail-risk reduction;
- path-scenario improvement when available;
- fresh carry available in the new fly;
- close+reopen transaction friction;
- remaining time to expiry;
- event regime and liquidity.

Do not claim positive EV unless a real-world scenario distribution has actually been supplied. Without it, call the result a **risk/carry improvement diagnostic**, not expected value.

### 10. Decision policy

Only this module can emit the final action.

Hard precedence:
1. invalid/stale-to-shock data that prevent reliable entry -> `NO TRADE` for candidate mode;
2. broker/RMS feasibility gate;
3. overnight event-latency / next-open stress gate;
4. hard event/tail/liquidity override -> `SQUARE OFF` / `NO TRADE`;
5. expiry-exit hard gates;
6. recenter gate;
7. ordinary HOLD/CARRY or ranked candidate selection.

The language model may synthesize evidence, but must not override deterministic hard gates without an explicit, documented reason from newer evidence.

### 11. Review scheduler

Set the next review from the earliest meaningful state-change opportunity:
- event timestamp;
- next price-discovery session;
- elevated state-change score;
- expiry gamma cadence;
- close/carry gate.

Do not schedule frequent reviews merely because many indicators exist.

### 12. Post-trade calibration

After a butterfly is fully closed, optionally append one episode using the schema in `post-trade-learning.md` and periodically run `scripts/summarize_trade_log.py`.

Measure separately:
- RND calibration diagnostics (descriptive, not expected to equal physical frequencies);
- real-world scenario hit rates / Brier scores when explicit probabilities were used;
- centre forecast error;
- tail-event misses;
- recenter incremental P&L when a valid counterfactual is available;
- exit timing and profit give-back;
- execution slippage.

Never auto-change live thresholds from a tiny sample. Require a meaningful history and review changes explicitly.
