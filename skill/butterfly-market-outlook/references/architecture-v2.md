# Butterfly strategy controller architecture — v2.6

The filename is a retained reference path, not a frozen v2 architecture. This
describes strategy-specific decision analytics, **not** the strategy-agnostic
[Execution Engine](https://github.com/ayyararyan/volarb/blob/main/execution-engine/README.md). Strategy semantics stay
outside `component.execution_engine`; Dhan supplies mechanical broker evidence.
The [personal covenant](https://github.com/ayyararyan/volarb/blob/main/docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md)
overrides generic overnight branches: intraday only, flat by 15:00 IST and no
entry/recenter thereafter.

## Module 0 - canonical decision controller

`references/decision-algorithm.md` is the only control plane. Start there on every run. Do not preload all references. Evaluate one gate at a time, load only the reference needed for that gate, and stop on the first terminal action. `scripts/decision_controller.py` can enforce normalized gate precedence. All modules below are calculation/data modules only; they may not reorder the controller.

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
9. **For intraday candidates, physical RV/drift comes before trade geometry.** Require a fresh approximately five-minute HF state forecast for the next 15-30 minutes before theta/gamma ranking.
10. **Regime comes before overnight trade geometry.** Classify whether the market is genuinely calm, transitioning, carrying latent jump risk, or already in active stress before approving overnight short gamma.
11. **Low implied volatility can be deceptive.** A compressed VIX/IV state with elevated event or tail-gap hazard is `LATENT_JUMP_RISK`, not calm.
12. **Recent opening-gap risk is state-dependent.** Carry must also pass a rolling realized-gap gate using recent close-to-open gaps, current-spot-to-break-even buffer and gap-gamma burden.
13. **Broker feasibility is part of the state.** A defined-risk payoff does not eliminate RMS/auto-squareoff risk; new expiry-eve overnight entries require validated broker feasibility.
14. **News interpretation is a child-skill responsibility.** Current raw news is classified once by `market-news-signal-filter`; the parent reuses its normalized packet and never independently re-scores the same headlines.
15. **Every closed trade can become a calibration episode.** Store forecasts and outcomes separately from the live decision logic; use them to measure whether rules add value before changing thresholds.
16. **v2.6 policy prerequisites precede candidate research.** Supply daily loss-budget/session-loss evidence; candidates require favourable session VRP and a complete fresh pass for same-session re-entry before HF sampling or optimization.
17. **Affordability is an exact-contract gate.** Ranked candidates still require fresh bound margin PASS packets; recentering requires separately verified full-transition margin, never entry-only evidence.

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
- `market-news-signal-filter`: current news/event interpretation and calibrated India transmission sensitivity;
- Reuters/primary/high-quality reporting: raw inputs used by the child news filter, not separately rescored by the parent.

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

Read `news-signal-integration.md`. Build the real-world event layer from one normalized child-skill packet plus current market observations. Do not reconstruct a separate headline narrative.

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


### 6A. Session VRP and loss/re-entry prerequisites

The controller checks the daily loss budget for every review. Before candidates
reach HF acquisition, it checks session variance-risk-premium state and any
same-session re-entry requirement. See [decision-algorithm.md](decision-algorithm.md)
and [session-vrp-gate.md](session-vrp-gate.md); this module list does not establish
a different gate order.

### 6B. Intraday HF realized-volatility / drift engine

Before any fresh `CANDIDATE_INTRADAY` reaches theta ranking, invoke `intraday-realized-volatility-forecast` on a fresh approximately five-minute futures/price block for the exact next-review horizon. The child estimates fast/slow continuous variance, recent jump pressure, same-horizon physical RV versus IV, and centre drift.

New intraday candidates require `FAVOURABLE`; `MARGINAL`, `UNFAVOURABLE`, or insufficient HF data terminate entry. Existing intraday positions treat medium/high-confidence `UNFAVOURABLE` as an exit-level signal and `MARGINAL` as a tighter-review state.

The HF child packet is P-measure state. Keep it separate from the RND/Q-measure surface. Pass its upper forecast move into width/stress construction after the gate passes.

### 6C. Market-regime engine

Before any actionable overnight carry decision, combine recent realized/gap state, option-implied state and the calibrated Market News Signal Filter hazard into one deterministic regime: `CALM_CARRY / TRANSITION / LATENT_JUMP_RISK / ACTIVE_STRESS / UNKNOWN`. See `regime-engine.md` and `scripts/classify_market_regime.py`.

The classifier explicitly detects a **complacency gap**: event/tail hazard materially above implied-volatility stress. A low VIX must not overrule this mismatch. Severe/unknown regimes block new next-session-expiry overnight carry; `TRANSITION` tightens the overnight thresholds.

### 6D. Overnight event-latency / broker-feasibility engine

When the intended hold crosses market close, run the v2.4 overnight gate before candidate ranking or a carry decision. Track the next actionable exit, a rolling 20-30-open realized-gap regime, current-spot-to-break-even buffer, gap-gamma burden, untradeable-window events, broker feasibility, and full-reprice +/-1.0/1.5/2.0 straddle joint spot/IV stresses. See `overnight-carry-gate.md` and `scripts/evaluate_overnight_carry.py`.

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
The ranked calculation is not yet an executable recommendation: apply the
[exact-candidate affordability gate](margin-affordability.md) and return only
the controller's margin-eligible candidate IDs.

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
An attractive diagnostic does not authorize RECENTRE without fresh verified
close/reopen transition evidence with scope `RECENTRE` and all earlier gates.

### 10. Decision policy

This module no longer owns gate precedence. `references/decision-algorithm.md` is the only control plane and must be followed literally.

Each analytical module returns a normalized gate result such as `PASS`, `WARN`, `BLOCK`, `FAIL`, `EXIT`, or `UNKNOWN`. The controller consumes those results in canonical order and the first terminal result wins. A later module may never resurrect a trade rejected by an earlier gate.

When normalized gate outputs are available, enforce the policy with `scripts/decision_controller.py`. The language model may explain a gate result but may not reorder the controller or override a terminal result with a later attractive metric such as theta.

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
