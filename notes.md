# Volarb Autonomous Butterfly Bot — Working Notes

This file is a living notebook for Aryan's design ideas. It should capture intent, interpretations, open questions, constraints, and architecture decisions as the discussion evolves. Do not treat early notes as final specifications unless explicitly marked as decided.

## Core objective

Transform the existing Volarb research and market-outlook ecosystem into an autonomous trading system focused primarily on managing short-gamma butterfly positions.

## Working principles

- Capture ideas first; formalize architecture later.
- Distinguish raw ideas from interpreted requirements and final decisions.
- Preserve uncertainty and open questions instead of silently inventing assumptions.
- Keep research, market-state assessment, trade construction, execution, monitoring, risk management, and post-trade learning conceptually separable unless a later design decision intentionally combines them.
- Do not assume that an existing research result automatically authorizes live trading behavior.

## Living graph

The current master decision graph is maintained in [docs/autonomous-butterfly-workflow.md](docs/autonomous-butterfly-workflow.md). It is the visual counterpart to these notes and should be updated as architectural decisions are added or changed.

## Notes log

### 2026-10-03 — Initial direction

**Raw intent:** Build an autonomous trading bot around Volarb, especially for short-gamma butterfly positions.

**Interpretation:** The eventual system should move beyond the current research-only `agent/` laboratory and be capable of operational decision-making around butterfly trades. The precise autonomy boundary, execution authority, risk controls, strategy-selection logic, monitoring cadence, and relationship to the existing research agent remain to be defined through subsequent discussion.

### 2026-10-03 — Broker/provider independence: Dhan must be replaceable

**Raw intent:** Dhan currently enters the system in three distinct places, but none of those integrations should become a fundamental dependency of the Volarb architecture. If Dhan is replaced by Kotak or another broker/data provider, the research logic, decision logic, strategy logic, and risk architecture should remain unchanged.

**Three Dhan touchpoints:**

1. **Research-data ingestion**
   - Dhan can supply historical market and derivatives data used during the research phase.
   - The research laboratory should consume a broker-neutral internal data contract rather than Dhan-specific response objects or schemas.
   - Historical research should therefore depend on a generic research-data interface, of which Dhan is only one implementation.

2. **Decision-time market-data ingestion**
   - Dhan can supply live data and/or historical context used by the autonomous system when deciding whether to enter, hold, recenter, hedge, reduce, or exit a butterfly.
   - The trading brain should receive normalized market state through a broker-neutral market-data interface.
   - Dhan websocket/feed semantics, instrument identifiers, timestamp conventions, reconnect logic, rate limits, etc. should terminate at the adapter boundary rather than leak into strategy logic.

3. **Execution and broker-control layer**
   - Dhan can supply order placement, modification, cancellation, position/order status, margin/account state, and any broker-specific operational requirements such as IP whitelisting and Dhan API authentication.
   - These concerns should live behind a generic execution/broker interface.
   - Strategy and risk components should issue broker-neutral execution intents; a Dhan execution adapter translates them into Dhan-specific API calls.

**Architecture interpretation:** Treat Dhan as an external infrastructure plug-in, not as part of Volarb's domain model. The core system should know concepts such as instruments, quotes, option chains, positions, orders, fills, margin, and account state — but it should not know Dhan-specific classes, payload fields, tokens, endpoints, or identifiers.

A useful conceptual boundary is:

```text
                  VOLARB CORE
        research / strategy / risk / policy
                       |
        -----------------------------------
        |                 |               |
 ResearchDataPort   MarketDataPort   ExecutionPort
        |                 |               |
        +---------- provider adapters -----+
                          |
                 Dhan / Kotak / ...
```

**Design rule:** No Dhan-specific object, enum, field name, authentication mechanism, endpoint, or exception should cross into the core research, strategy, risk, portfolio, or decision layers. Provider-specific details are translated at the edge into canonical Volarb models.

**Implication for replacement:** Replacing Dhan should ideally mean implementing or enabling a new set of provider adapters and changing configuration, not rewriting the trading engine.

**Likely implementation split:**
- `ResearchDataProvider` / historical-data adapter
- `MarketDataProvider` / live-and-decision-data adapter
- `ExecutionBroker` / orders, positions, fills, account and broker operations
- shared canonical Volarb schemas between adapters and the core
- provider selection through configuration/dependency injection rather than imports inside strategy code

**Important nuance:** The three interfaces may all be backed by Dhan initially, but they should remain independently replaceable. For example, future Volarb could research on an exchange/vendor archive, make live decisions from another market-data vendor, and execute through Kotak without changing the strategy engine.

**Acceptance test for this principle:** A broker migration should not require edits to hypothesis generation, signal/regime logic, butterfly construction, portfolio/risk rules, or trade-management policy. Changes should be confined primarily to provider adapters, configuration, and any provider-capability declarations.

### 2026-10-03 — Mandatory regime gate before butterfly deployment

**Raw intent:** Before trading volatility arbitrage or short-gamma butterflies, the system must first know whether the current market regime is favorable for deploying the strategy at all. The exact method for constructing this regime detector can be designed later, but the architectural box itself is mandatory.

**Interpretation:** Regime assessment is a distinct, upstream decision layer. It should not be buried inside trade construction, strike selection, position sizing, or execution. The system first answers a higher-order question: **"Is short-gamma butterfly deployment currently permitted by the market regime?"** Only after that gate is satisfied should the engine consider the details of an actual trade.

Conceptually:

```text
Market / historical / contextual data
                |
                v
        +------------------+
        |   REGIME GATE    |
        | favorable?       |
        +------------------+
           |           |
          NO          YES
           |           |
     no new short-     v
     gamma trade   trade opportunity /
                    construction logic
```

**Design principle:** The regime box should be treated as a first-class module with a clearly defined input contract and output contract. The eventual methodology may combine deterministic rules, statistical state classification, volatility structure, market microstructure, trend/range conditions, realized-versus-implied volatility, event/news risk, or other signals, but those details are deliberately deferred.

**Minimum conceptual output:** The regime layer should at least be able to distinguish between:
- favorable / eligible for short-gamma butterfly deployment,
- unfavorable / ineligible,
- uncertain or insufficient-data state where the system should fail safe rather than force a trade.

A richer implementation could later add regime labels, confidence, reasons, expiry-specific suitability, and recommended risk intensity, but those are not yet decided.

**Architectural consequence:** No new butterfly should be opened merely because a particular structure appears attractive in isolation. The regime layer sits above trade selection and acts as a precondition for deployment.

**Important separation:** Regime suitability and individual-trade attractiveness are different questions:
- Regime gate: *Should this type of risk be deployed now?*
- Trade-selection layer: *If yes, which specific butterfly, expiry, strikes, width, size and timing are best?*

**Future design task:** Define how the regime box is built, calibrated, validated, and updated over a multi-day horizon. This regime is explicitly not an intraday state classifier; it is intended to characterize persistent market conditions across continuous days or weeks. The exact cadence and evidence required for a regime transition remain open.


### 2026-10-03 — Unfavorable regime path and adaptive recheck timing

**Raw intent:** If the regime gate says the environment is not favorable for short-gamma butterflies, the system should not simply stop indefinitely or check again arbitrarily. It needs a separate mechanism that decides **when the regime should next be reassessed**.

**Critical clarification:** The regime being discussed is not an intraday regime. It is a persistent multi-day market state — potentially spanning several days or one or two weeks — describing whether the broader environment has recently been suitable for short-gamma butterfly deployment.

**Interpretation:** The negative branch of the regime gate requires its own box: a **Regime Recheck Scheduler**. Its job is not to decide whether the market is favorable; the regime detector already does that. Its job is to decide **when enough new information may plausibly have accumulated to justify asking the regime question again**.

Conceptually:

```text
                REGIME GATE
              favorable now?
               /          \
             YES           NO
              |             |
              v             v
      underlying       REGIME RECHECK
      allocator          SCHEDULER
                             |
                    when should we
                    test again?
                             |
                             v
                     next regime check
                             |
                             +-------> REGIME GATE
```

**Design principle:** An unfavorable regime should create a durable waiting state with an explicit next-review condition. The system should not continuously poll the regime merely because it is capable of doing so.

**Possible future recheck logic, not yet decided:** The next check could eventually depend on elapsed trading days, meaningful changes in realized volatility, implied-versus-realized relationships, trend/range behavior, event-risk conditions, volatility-of-volatility, drawdown in recent short-gamma proxies, or another state-change signal. The architecture should allow either:
- a time-based recheck,
- an event/state-change-triggered recheck,
- or a hybrid of the two.

**Output of this box:** At minimum, the scheduler should produce a next permitted or required regime-review time/condition. It may later also record the reason for that timing.

**Important separation:**
- Regime detector: *Is the multi-day environment favorable now?*
- Recheck scheduler: *If not, when should we ask that question again?*

**Behavioral consequence:** When the regime is unfavorable, the autonomous bot should remain in a deliberate **NO-NEW-SHORT-GAMMA / WAITING-FOR-REASSESSMENT** state rather than drifting into repeated trade searches.

### 2026-10-03 — Capital-aware underlying selection after regime approval

**Raw intent:** Once the regime gate says short-gamma butterflies are favorable, the next question is not yet strike selection or execution. The system must first decide **what underlying(s) to trade** from the allowed universe: NIFTY, BANKNIFTY, and SENSEX.

**Interpretation:** This is a separate instrument-allocation box that sits immediately after the regime gate. It decides which index options are eligible for deployment given both market attractiveness and the capital/margin actually available in the account.

The decision is therefore joint:

1. Is the underlying itself favorable for a short-gamma butterfly right now?
2. Can the account actually afford the required butterfly position and associated risk/margin buffer?
3. If several underlyings are both favorable and affordable, how many of them should be deployed simultaneously?

Conceptually:

```text
        REGIME GATE
       short gamma OK?
             |
            YES
             |
             v
   +----------------------+
   | UNDERLYING ALLOCATOR |
   | NIFTY / BANKNIFTY /  |
   | SENSEX               |
   +----------------------+
       |       |       |
     NIFTY   BANK    SENSEX
       |       |       |
       +-------+-------+
               |
      capital / margin
      feasibility check
               |
               v
   selected tradable subset
```

**Key principle:** Available capital is not merely a position-sizing input after instrument selection; it can determine the feasible instrument universe itself. If the account can support only one NIFTY butterfly, BANKNIFTY or SENSEX may be excluded before downstream trade construction. Conversely, if sufficient capital exists and all three markets are favorable, the allocator may permit exposure to all three.

**Important distinction:** This layer should not automatically force a single winner. The output may be a subset:
- NIFTY only,
- BANKNIFTY only,
- SENSEX only,
- any pair,
- all three,
- or none.

**Capital-awareness:** The allocator should consume live broker-neutral account state such as available funds, margin requirement, existing deployed capital, reserved risk buffer, and current portfolio exposure. The exact margin source may initially come from Dhan, but the allocator should consume normalized Volarb account/margin data rather than Dhan-specific fields.

**Architectural consequence:** Instrument choice should be separated from:
- regime eligibility,
- specific butterfly construction,
- strike/wing selection,
- sizing,
- execution.

The downstream trade-construction engine should receive only the underlying(s) approved by this allocator.

**Future design task:** Define how attractiveness is compared across NIFTY, BANKNIFTY and SENSEX, how margin is estimated conservatively before execution, how capital is reserved across simultaneous trades, and whether the allocator should optimize diversification, expected edge, risk-adjusted capital efficiency, or some other objective.


### 2026-10-03 — Fan-out into per-underlying graphs and intraday opportunity recheck

**Raw intent:** After the regime is favorable and the underlying allocator selects a tradable set, each selected underlying should receive its own graph. If NIFTY is selected, open the NIFTY graph. If NIFTY and SENSEX are selected, open both graphs. If all three are selected, all three graphs run. If none is selected despite the favorable broader regime, the system should not fall back into the multi-day unfavorable-regime loop; instead it should decide when to look again intraday for a tradable underlying.

**Interpretation:** The architecture now separates three different time scales and decisions:

1. **Multi-day regime state:** Is this generally a period in which short-gamma butterflies should be considered?
2. **Intraday underlying opportunity selection:** Given a favorable regime, which of NIFTY, BANKNIFTY, and SENSEX are worth trading now?
3. **Per-underlying trade graph:** Once an underlying is selected, run an independent graph for that market's actual butterfly decision and lifecycle.

Conceptually:

```text
                        REGIME GATE
                       favorable?
                      /          \
                    NO            YES
                    |              |
          multi-day regime         v
          recheck scheduler   UNDERLYING ALLOCATOR
                                   |
                    +--------------+--------------+
                    |              |              |
                  NIFTY        BANKNIFTY        SENSEX
                 selected?      selected?       selected?
                    |              |              |
                   YES            YES            YES
                    |              |              |
                    v              v              v
              NIFTY GRAPH     BANKNIFTY GRAPH  SENSEX GRAPH
                    \              |              /
                     \             |             /
                      +---- portfolio coordination ----+
```

The fan-out is set-valued rather than single-choice. The allocator can launch one, two, or three underlying graphs depending on current opportunity and capital feasibility.

**No-selection branch under a favorable regime:** A favorable multi-day regime does not imply that there must be a trade at every moment. If the allocator returns an empty set because none of the three indices currently offers an acceptable butterfly opportunity, the bot should enter a separate **INTRADAY OPPORTUNITY WAIT** state.

That state feeds a second scheduler:

```text
REGIME = FAVORABLE
        |
        v
UNDERLYING ALLOCATOR
        |
   selected set
   /          \
non-empty      empty
   |             |
   v             v
spawn graphs   INTRADAY OPPORTUNITY
               RECHECK SCHEDULER
                      |
             when should we scan
             NIFTY/BANK/SENSEX again?
                      |
                      v
             UNDERLYING ALLOCATOR
```

**Important distinction between the two schedulers:**
- **Regime Recheck Scheduler:** used when the broader multi-day environment is unfavorable; cadence is measured in persistent market-state change across days.
- **Intraday Opportunity Recheck Scheduler:** used when the broader regime is favorable but no specific underlying is currently worth trading; cadence is intraday and concerns opportunity availability, not regime classification.

These are separate loops and should not be conflated.

**Per-underlying graph principle:** Once selected, each underlying becomes its own stateful graph with its own trade construction, monitoring, decisions, and eventual terminal/re-entry behavior. NIFTY, BANKNIFTY, and SENSEX should therefore be able to progress independently after fan-out.

**Portfolio coordination consequence:** Although the underlying graphs are logically independent, they share account capital and risk. Capital/margin committed to one selected graph must be reserved before or during graph launch so two parallel graphs cannot both assume the same free capital is available. The exact portfolio-coordination mechanism remains to be designed later.

**Return behavior:** If no underlying is selected, the loop returns to the underlying-selection decision at the next intraday recheck. The broader regime need not be recomputed on every opportunity scan unless its own validity/recheck condition has been reached or a separate event invalidates it.

**Future design task:** Define:
- what starts and terminates each underlying graph,
- whether the graphs are identical parameterized templates or separate implementations,
- what criteria cause an underlying to become temporarily unattractive,
- how the intraday recheck time is chosen,
- how portfolio capital/risk is reserved across simultaneously launched graphs,
- and when a material intraday event should force an early re-evaluation of the broader regime.


### 2026-10-03 — Per-underlying structure selection: what exactly do we trade?

**Raw intent:** Once an underlying graph is launched, the system already knows that this underlying is approved for trading. The next question inside that graph is therefore: **what exact options structure should be traded on this underlying?**

Using NIFTY as the running example, the answer should not be hard-coded to one symmetric iron butterfly. Candidate structures may include:
- symmetric iron butterflies with different wing widths, such as ATM ±500 or ATM ±600,
- asymmetric iron butterflies,
- iron condors,
- and potentially other bounded-risk short-volatility structures that are later admitted into the strategy universe.

**Interpretation:** Each underlying graph requires a dedicated **Structure Selector**. Its job is to evaluate the currently allowed structure universe for that underlying and choose the structure or structures that best satisfy the current trading objective and constraints.

Conceptually:

```text
NIFTY GRAPH
    |
    v
we are trading NIFTY
    |
    v
+----------------------+
|  STRUCTURE SELECTOR  |
| what exactly to      |
| trade in NIFTY?      |
+----------------------+
    |
    +--> symmetric iron butterfly
    |      - ATM +/- 500
    |      - ATM +/- 600
    |      - other admitted widths
    |
    +--> asymmetric butterfly
    |
    +--> iron condor
    |
    +--> other approved
         short-vol structures
```

**Key principle:** The underlying decision and the structure decision are separate. Selecting NIFTY means only that NIFTY is the market in which the system should search for a trade. It does not predetermine whether that trade is a butterfly, condor, symmetric structure, asymmetric structure, or a specific wing width.

**Structure universe should be extensible:** The core graph should depend on a broker-neutral and strategy-neutral catalogue of approved structures rather than containing hard-coded NIFTY-specific combinations. New structures should be addable to the candidate universe without rewriting the graph itself.

**Possible structure dimensions, to be designed later:**
- structure family: iron butterfly, asymmetric butterfly, iron condor, etc.,
- short-strike placement,
- call-side wing distance,
- put-side wing distance,
- symmetry/asymmetry,
- expiry,
- lot count,
- target net credit,
- maximum loss,
- Greeks or risk shape,
- liquidity and spread constraints,
- expected margin/capital use,
- expected carry/theta,
- short-gamma exposure,
- and any research-supported state variables.

**Architectural consequence:** The output of the Structure Selector should be a canonical trade-structure specification, not broker orders. Execution remains downstream.

For example, conceptually:

```text
StructureSpec
  underlying = NIFTY
  family = IRON_BUTTERFLY
  expiry = ...
  short_strike = ...
  put_wing = ...
  call_wing = ...
  lots = ...
```

The broker adapter later translates the final approved structure into actual instrument identifiers and orders.

**Important nuance:** The Structure Selector may eventually decide that, although NIFTY was worth examining, **no currently admissible structure is attractive enough to trade**. That case should not be forced into an execution. Its return path and recheck timing will need to be defined later.

**Research connection:** The allowed structure universe and any preference rules should eventually be informed by the research laboratory, but the live graph should not invent arbitrary structures outside approved/researched capabilities.

**Future design task:** Define how the Structure Selector compares candidate structures, whether it selects exactly one structure or can propose several, what evidence/score governs the choice, how expiry is chosen, and what happens when no structure passes the threshold.


### 2026-10-03 — Capital allocation to each graph, then constrained structure optimization

**Raw intent:** The candidate butterflies for an underlying form a feasible candidate set. For example, NIFTY may have many possible structures: ATM ±500, ATM ±600, asymmetric butterflies, iron condors, and so on. Once NIFTY has been selected for trading, a separate allocator first assigns a specific amount of capital to the NIFTY graph. The NIFTY graph then uses an optimizer to choose the best candidate structure that can actually be afforded within that assigned capital.

**Interpretation:** There are two separate decisions here and they should not be merged:

1. **Capital allocation across underlying graphs**
   - A higher-level allocator decides how much capital is assigned to each selected underlying graph.
   - If the selected set is `S = {NIFTY, BANKNIFTY}`, then the portfolio layer may assign budgets such as `W_NIFTY` and `W_BANKNIFTY`.
   - These allocations are hard resource constraints for the downstream graphs.

2. **Constrained optimization inside each underlying graph**
   - The graph receives its capital allocation `W_X`.
   - It evaluates the admissible candidate structures for underlying `X`.
   - It chooses the best candidate among only those structures that satisfy the graph's capital/margin constraint and all other admissibility rules.

Conceptually:

```text
SELECTED UNDERLYINGS
        |
        v
+----------------------+
| PORTFOLIO / CAPITAL  |
| ALLOCATOR            |
+----------------------+
   |               |
 W_NIFTY         W_BANK
   |               |
   v               v
NIFTY GRAPH     BANK GRAPH
   |               |
   v               v
candidate set    candidate set
   |               |
   v               v
CONSTRAINED      CONSTRAINED
OPTIMIZER        OPTIMIZER
   |               |
   v               v
best affordable  best affordable
structure        structure
```

**Key principle:** The optimizer does not optimize over the entire theoretical structure universe. It optimizes over the subset that is:
- approved for that underlying,
- currently admissible,
- operationally executable,
- and affordable within the capital allocation `W_X`.

**Budget constraint:** If the NIFTY graph receives only INR 100,000, then any candidate requiring more deployable capital or margin than that amount is infeasible and should be excluded before final selection.

**Important separation:** The portfolio allocator answers:

> How much capital should graph X receive?

The per-underlying optimizer answers:

> Given `W_X`, which admissible structure should graph X trade?

The optimizer should not silently borrow unused capital from another graph unless the portfolio allocator explicitly reallocates it.

**Objective deliberately left open:** The architecture requires an optimizer, but the quantity being optimized is not yet fixed. It could later involve expected edge, expected return on deployed capital, risk-adjusted return, theta capture, short-gamma efficiency, expected utility, drawdown, execution quality, robustness, or a multi-objective score. That choice should be decided later from research evidence rather than assumed now.

**Canonical formulation:**

```text
For underlying X:

Candidate universe: C_X
Capital allocation: W_X

Choose c* in C_X

subject to:
    required_capital(c*) <= W_X
    c* passes all admissibility constraints

and maximizing:
    Objective_X(c)
```

The exact definition of `Objective_X(c)` remains open.

**No-feasible-candidate case:** It is possible that an underlying has been selected and receives capital, but no candidate structure fits the budget or passes the remaining constraints. The optimizer must be allowed to return **NO FEASIBLE CANDIDATE** rather than force a trade. The return/recheck path for that state remains to be specified.

**Architectural consequence:** Capital allocation belongs above the per-underlying optimizer. Structure optimization must be capital-aware by construction, not corrected after a structure has already been chosen.

**Future design task:** Define:
- how total account capital is allocated across selected underlying graphs,
- whether allocations are static, proportional, risk-budgeted, or optimization-based,
- what exact objective the structure optimizer maximizes,
- which constraints besides capital/margin are hard constraints,
- whether one or multiple structures can be selected per underlying,
- and how unused capital is returned or reallocated.


### 2026-10-03 — Third scheduling layer: within-hour structure recheck inside Graph X

**Raw intent:** Once Graph X has been opened, the higher-level decision to trade underlying X has already been made. If the graph cannot currently find an appropriate candidate structure in its admissible subset C_X, it should not return to the underlying-selection layer. Instead, it should remain inside Graph X and decide **when within the hour to search for a suitable structure again**.

**Interpretation:** This introduces a third and faster scheduling horizon.

There are now three distinct re-evaluation clocks in the architecture:

1. **Regime clock — days / weeks**
   - Question: *Is the broader multi-day environment favorable for short gamma at all?*
   - If unfavorable, the Regime Recheck Scheduler decides when to revisit the regime.

2. **Underlying-opportunity clock — intraday**
   - Question: *Given a favorable regime, which of NIFTY, BANKNIFTY, and SENSEX should be traded now?*
   - If none is selected, the Intraday Opportunity Recheck Scheduler decides when to scan the index universe again.

3. **Structure-opportunity clock — within the hour**
   - Question: *Given that Graph X is already active and X is intended to be traded, is there an acceptable structure in C_X right now?*
   - If not, the **Within-Hour Structure Recheck Scheduler** decides when Graph X should run its candidate search and constrained optimizer again.

Conceptually:

```text
Graph X active
    |
    v
Build / refresh candidate set C_X
    |
    v
Constrained optimizer
    |
    +-- candidate found
    |      |
    |      v
    |   continue to selected StructureSpec
    |
    +-- no acceptable candidate
           |
           v
    WITHIN-HOUR STRUCTURE
       RECHECK SCHEDULER
           |
     when should Graph X
      search C_X again?
           |
           v
          WAIT
           |
           +------> refresh C_X / optimizer
```

**Key principle:** A failure to find a structure is not the same as a failure to select the underlying. The graph should preserve the higher-level decision that X is currently a chosen market and remain local to Graph X while searching again on a faster cadence.

**Example:** If both NIFTY and BANKNIFTY are selected, BANKNIFTY may immediately find a feasible butterfly and continue toward execution while NIFTY enters its within-hour structure-search loop. The two graphs progress independently.

**Scheduling horizon:** This scheduler is explicitly intended to operate within the hour rather than on a multi-hour or multi-day regime horizon. The exact cadence is not yet defined. It may later depend on quote changes, volatility movement, option-chain changes, liquidity, spot displacement, elapsed minutes, or another state-change trigger.

**Important distinction among the three waiting loops:**
- unfavorable regime -> multi-day Regime Recheck Scheduler,
- favorable regime but no underlying selected -> intraday Opportunity Recheck Scheduler,
- underlying selected but no acceptable structure -> within-hour Structure Recheck Scheduler.

**State persistence:** Graph X should remain active while waiting for a structure recheck. Whether its capital allocation W_X remains fully reserved during this waiting period, can be partially released, or expires after a timeout is a separate portfolio-allocation decision and remains TBD.

**Future design task:** Define:
- how the within-hour scheduler determines its next check,
- whether a structure search can be triggered earlier by material market changes,
- how long Graph X may remain in this state before its higher-level selection expires,
- and what happens to W_X while Graph X is waiting.


### 2026-10-03 — Sticky daily underlying commitment and reserved capital

**Raw intent:** Once the system has decided that an underlying X should be traded today, that decision should persist. The next question is no longer whether X should be traded, unless some higher-level condition explicitly changes that decision. The question becomes **when** to trade X and **which structure** to use.

If NIFTY is selected for the day, the capital assigned to the NIFTY graph should remain reserved for NIFTY even if no acceptable structure is available immediately. The trade may happen 15 minutes later, 20 minutes later, an hour later, or not happen at all that day, but the capital slot remains reserved because the system has already committed to NIFTY as a target underlying for that trading day.

**Interpretation:** Underlying selection creates a durable **daily commitment state** for Graph X.

Once Graph X is activated:
- X remains selected,
- W_X remains reserved,
- structure search may pause and resume,
- and the graph keeps asking **when/how to trade X**, not **whether X should still be traded**.

The selection is only reconsidered if an explicit higher-level invalidation or revocation condition is triggered.

Conceptually:

```text
Underlying X selected for today
        |
        v
Reserve W_X
        |
        v
Graph X = ACTIVE / COMMITTED
        |
        v
Search candidate set C_X
        |
   candidate found?
    /          \
  YES           NO
   |             |
   v             v
trade path   within-hour scheduler
                 |
                 v
            search again
                 |
                 +------> W_X still reserved
```

**Key rule:** Capital reservation follows the underlying commitment, not the immediate existence of a candidate structure.

Therefore:
- no acceptable candidate does **not** release W_X,
- a delayed trade does **not** release W_X,
- and another graph may not consume W_X merely because Graph X is temporarily waiting.

**State hierarchy:** The system should distinguish:
- `UNDERLYING_SELECTED`
- `CAPITAL_RESERVED`
- `WAITING_FOR_STRUCTURE`
- `STRUCTURE_SELECTED`
- `POSITION_OPEN`

These are different states. A graph can be `UNDERLYING_SELECTED + CAPITAL_RESERVED + WAITING_FOR_STRUCTURE` for an extended period.

**Daily persistence:** The commitment is conceptually tied to the current trading day unless explicitly revoked earlier. If the entire day passes without a suitable structure, the system may finish the day having made no trade in X while still having correctly reserved capacity for it throughout the session.

**Revocation remains separate:** A later architecture decision must define what can revoke the daily commitment before the day ends. Examples might include:
- the broader regime becoming invalid,
- a hard risk event,
- capital becoming unavailable due to an external account change,
- market closure or a time cutoff,
- or an explicit portfolio-level cancellation rule.

Until such a revocation occurs, the graph should not silently fall back to asking whether X belongs in the selected set.

**Portfolio consequence:** Portfolio capital allocation becomes sticky after underlying selection. The portfolio allocator cannot reclaim W_X opportunistically just because Graph X has not yet executed.

**Future design task:** Define:
- what events are permitted to revoke an active underlying commitment,
- whether the commitment expires automatically at market close,
- whether unused W_X may be reallocated only after explicit revocation,
- and how the next trading day rebuilds the selected set and allocations from scratch.


### 2026-10-03 — Decision-to-execution handoff and separate execution/risk layer

**Raw intent:** Once Graph X has selected a concrete candidate structure through its constrained optimizer, the decision is complete: that exact structure X is to be traded now. At that point the workflow should leave the selection/optimization logic and hand the approved trade into a separate execution layer.

Execution and risk management should be treated as their own downstream layer and designed independently later.

**Interpretation:** The architecture needs an explicit boundary between **decision formation** and **trade realization**.

Upstream logic decides:
- the regime is favorable,
- underlying X is selected,
- W_X is reserved,
- candidate structures are evaluated,
- and the optimizer selects a specific broker-neutral `StructureSpec`.

Once a `StructureSpec` has been selected and approved, the upstream graph should not continue reconsidering what to trade. It should emit a trade intent into the downstream **Execution + Risk Management layer**.

Conceptually:

```text
Graph X
  |
  v
Constrained optimizer
  |
  v
Selected StructureSpec
  |
  v
DECISION COMPLETE
  |
  v
+------------------------------+
| EXECUTION + RISK MANAGEMENT  |
| LAYER                        |
+------------------------------+
  |
  +--> order realization       TBD
  +--> fill handling           TBD
  +--> live position risk      TBD
  +--> monitoring              TBD
  +--> adjustments/exits       TBD
```

**Key rule:** The execution layer should receive a clear, canonical trade intent. Broker-specific translation remains downstream through the execution provider interface.

**Boundary principle:** The decision graph should answer **what should be traded**. The execution/risk layer should answer **how to establish, supervise, modify, and eventually close that position safely in the real market**.

**Separation from Dhan:** The execution/risk layer may initially use Dhan for broker operations, but the layer itself must remain broker-neutral. Dhan-specific API calls, order identifiers, authentication, IP whitelisting, and execution errors belong behind the execution adapter.

**Current stopping point:** The internal design of the Execution + Risk Management layer is intentionally left unresolved for now and will be developed as a separate subgraph.


### 2026-10-03 — Smart Volarb execution/risk layer vs thin broker executor

**Raw intent:** The execution layer being designed belongs to Volarb itself. This is where the strategy continues to make intelligent decisions about how the chosen trade should actually be established and managed. That intelligent layer should then hand explicit broker actions to a separate Dhan executor.

The Dhan executor is a plug-in and should contain very little trading intelligence. Its job is to faithfully execute instructions through Dhan's API. Tomorrow the same interface could be implemented by Kotak, ICICI Securities, or another broker without changing the Volarb execution/risk logic.

**Interpretation:** The previously named **Execution + Risk Management layer** must itself be split into two architectural levels:

1. **Volarb Execution + Risk Management Engine**
   - owns trading intelligence after the StructureSpec has been selected;
   - decides how and when to express the approved trade in the market;
   - determines execution sequencing, monitoring, risk responses, adjustments, exits, and other strategy decisions that will be designed later;
   - remains broker-neutral.

2. **Broker Executor / Adapter**
   - receives explicit execution commands from the Volarb engine;
   - translates canonical commands into broker-specific API requests;
   - handles broker-specific authentication, instrument/token mapping, IP whitelisting, order IDs, API responses, retries/errors, and status synchronization;
   - should not decide whether a trade is desirable or how the strategy should manage risk.

Conceptually:

```text
Selected StructureSpec
        |
        v
+--------------------------------+
| VOLARB EXECUTION + RISK ENGINE |
|                                |
| smart strategy decisions       |
| execution policy               |
| live risk decisions            |
| adjustments / exits            |
+--------------------------------+
        |
        | canonical execution commands
        v
+-------------------------------+
| BROKER EXECUTOR PLUG-IN       |
| Dhan / Kotak / ICICI / ...    |
|                               |
| thin translation + execution  |
+-------------------------------+
        |
        v
Broker / Exchange
```

**Key boundary:** Volarb decides **what action should happen**. The broker executor decides only **how to express that already-decided action through a specific broker API**.

**Broker executor should be intentionally dumb:** It should not independently choose strikes, alter the strategy, resize because it "thinks" another size is better, decide to recenter, change exit logic, or substitute another structure. If an instruction cannot be executed, it reports the execution state/failure back to the Volarb engine, which decides what to do next.

**Canonical command layer:** The interface between the Volarb execution/risk engine and the broker plug-in should eventually use broker-neutral commands such as:
- place order,
- modify order,
- cancel order,
- query order status,
- query fills,
- query positions,
- query margin/account state.

The exact command schemas remain TBD.

**Feedback direction:** Although the broker executor contains little intelligence, it must return authoritative execution facts to Volarb: accepted/rejected orders, fills, partial fills, prices, quantities, broker errors, position state, and account/margin state. Volarb then uses those facts for subsequent risk and execution decisions.

**Replacement test:** Replacing Dhan with Kotak or ICICI Securities should require changing/configuring the broker executor plug-in, not rewriting the Volarb execution/risk engine.

**Architectural naming clarification:**
- **Volarb Execution + Risk Management Engine** = intelligent strategy layer.
- **Dhan Executor** = thin provider-specific implementation of the broker execution interface.

The internal structure of the intelligent Volarb execution/risk engine remains to be designed separately.


### 2026-10-03 — Broker-dependent margin feasibility as an explicit execution input

**Raw intent:** There is one important place where the intelligent Volarb Execution + Risk Management Engine necessarily depends on the selected broker: actual margin feasibility. The margin required to establish a proposed position can depend on the broker/account environment. Therefore, before Volarb sends an execution plan, it must ask the active broker whether that exact plan is feasible given current margin/account state.

**Interpretation:** Broker-independence does not mean broker-blindness. Volarb remains independent of Dhan-specific APIs and semantics, but it must consume certain authoritative broker facts before acting.

This should be represented through a broker-neutral interface such as:

`BrokerMarginFeasibilityPort`

with provider-specific implementations such as:

- `DhanMarginFeasibilityAdapter`
- `KotakMarginFeasibilityAdapter`
- `ICICIMarginFeasibilityAdapter`

Conceptually:

```text
Selected StructureSpec
        |
        v
Volarb Execution + Risk Management Engine
        |
        v
Build intended execution plan
        |
        v
PRE-TRADE MARGIN FEASIBILITY CHECK
        |
        v
BrokerMarginFeasibilityPort
        |
        +--> Dhan margin/account API
        +--> Kotak margin/account API
        +--> ICICI margin/account API
        |
        v
Normalized MarginFeasibility result
        |
   +----+----+
   |         |
 feasible  infeasible
   |         |
   v         v
execute    return to Volarb engine
           for strategy decision TBD
```

**Key principle:** The broker supplies facts; Volarb supplies intelligence.

The broker-specific adapter may determine or retrieve:
- current available margin/account capacity,
- broker-recognized margin requirement for the intended order basket or position,
- current margin already consumed,
- any broker-specific feasibility response needed to know whether the trade can actually be placed.

But the adapter should not decide what alternative trade to take if the proposed execution is infeasible.

**Normalized result:** The broker adapter should translate its native API response into a canonical result, conceptually something like:

```text
MarginFeasibility
  feasible: true / false
  required_margin: ...
  available_margin: ...
  margin_shortfall: ...
  broker: ...
  checked_at: ...
  raw_reference: ...
```

The exact schema is TBD.

**Execution rule:** No live order plan should be sent to the broker executor until the Volarb execution layer has passed the broker-derived margin feasibility check.

**Infeasible case:** If the chosen structure or intended execution plan is not feasible under the active broker's margin state, control returns to the Volarb Execution + Risk Management Engine. What Volarb does next — resize, choose another execution sequence, return to optimization, wait, or abandon the structure — remains deliberately unresolved for now.

**Architectural consequence:** The intelligent execution layer therefore has one legitimate broker dependency: a dependency on normalized, authoritative broker margin/account state. It should not depend directly on Dhan classes, payloads, endpoints, or calculations.

**Relationship to the thin broker executor:** The margin interface may be implemented by the same provider plug-in package as order execution, but it is conceptually a separate capability:
- **MarginFeasibilityPort** = broker facts needed before a decision is executable.
- **ExecutionPort** = enact already-approved broker-neutral commands.

## Open questions / unresolved design choices

- What decisions should be fully autonomous versus require human approval?
- What exact instruments, expiries, entry windows, and butterfly constructions are in scope?
- What market-regime conditions should permit or forbid short-gamma deployment?
- How should the regime detector be built, calibrated and validated?
- Should regime state be market-wide, underlying-specific, expiry-specific, or a hierarchy of all three?
- How frequently should the multi-day regime state be recomputed, and what evidence is required before switching states?
- How should the Regime Recheck Scheduler choose the next review: fixed trading-day cadence, state-change trigger, or hybrid?
- How should the Intraday Opportunity Recheck Scheduler decide when to rescan NIFTY, BANKNIFTY, and SENSEX after an empty selection?
- Should NIFTY, BANKNIFTY, and SENSEX use one parameterized underlying graph template or have genuinely different graph structures?
- What candidate structure families and parameter ranges belong in each underlying's approved Structure Selector universe?
- Should the Structure Selector choose one structure, rank several candidates, or return an empty set when nothing is attractive?
- How should expiry selection interact with structure-family and wing-width selection?
- How should shared capital and risk be reserved across multiple underlying graphs launched in parallel?
- How should total deployable capital be allocated into per-underlying budgets W_X before graph-level optimization?
- What objective should each per-underlying optimizer maximize under its W_X constraint?
- What happens to unused capital when a graph finds no feasible or attractive candidate?
- How should the Within-Hour Structure Recheck Scheduler choose its next candidate-search time?
- How long can Graph X remain selected without finding a structure before the higher-level underlying decision must be reconsidered?
- W_X is fully reserved once X is selected for the day; define only the explicit revocation conditions that can release it.
- What events may revoke a daily underlying commitment before market close?
- Does every daily underlying commitment automatically expire at the end of the trading session?
- Should the regime gate output only eligible/ineligible/uncertain, or also a confidence score and risk-intensity recommendation?
- How should the research laboratory feed evidence into the live trading system without creating look-ahead or uncontrolled adaptation?
- What are the hard portfolio, loss, margin, liquidity, and execution-risk limits?
- What should trigger hold, recenter, hedge, scale, or square-off actions?
- What broker/execution infrastructure should the bot eventually control?
- What canonical TradeIntent/StructureSpec contract should cross the decision-to-execution boundary?
- How should the Volarb Execution + Risk Management subgraph be structured internally?
- What canonical broker-neutral execution command and execution-event schemas should connect Volarb to broker executor plug-ins?
- What exact schema should `BrokerMarginFeasibilityPort` return to the Volarb execution engine?
- If a selected StructureSpec fails the broker margin feasibility check, which Volarb node should receive control next?
- Which broker/API failures should be handled entirely inside the adapter versus escalated to the Volarb engine?
- Should research data and decision-time historical data share one canonical market-data schema while retaining separate provider capabilities?
- Which broker-neutral identifiers should Volarb own for underlyings, expiries, strikes, option types and contracts, and where should broker token mapping live?
- How should the system express provider capability differences without contaminating strategy logic?
