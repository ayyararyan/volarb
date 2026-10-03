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

The architecture is now split into one small master orchestrator and five detailed graphs. Every architectural entity uses the immutable Volarb Vector Identity System (VID):

- [VID specification](docs/workflows/vector-id-system.md)
- [VID registry](docs/workflows/vector-id-registry.json)
- [Master workflow](docs/autonomous-butterfly-workflow.md)
- [Regime Gate](docs/workflows/regime-gate.md)
- [Underlying Allocation](docs/workflows/underlying-allocation.md)
- [Trade Selection](docs/workflows/trade-selection.md)
- [Position Management](docs/workflows/position-management.md)
- [Internal Execution](docs/workflows/internal-execution.md)

The master graph should remain deliberately small. New decision detail should be added to the owning box rather than expanding the master unless a genuinely new top-level phase appears.

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


### 2026-10-03 — Refactor into master graph plus four owned subgraphs

**Decision:** The previous single workflow graph had become too detailed and difficult to reason about. The architecture is now explicitly decomposed into one small orchestration graph and four independently evolvable graphs.

1. **Regime Gate — Regime Decision Graph**
   - days/weeks horizon;
   - owns regime eligibility and the multi-day regime recheck loop.

2. **Underlying Allocation — Intraday Instrument Selection & Capital Allocation**
   - intraday horizon;
   - chooses the subset of NIFTY/BANKNIFTY/SENSEX;
   - owns the intraday no-selection recheck loop;
   - allocates and reserves W_X for each selected daily commitment.

3. **Trade Selection — Per-Underlying Trade Selection Graph X**
   - one independent instance for every selected X;
   - owns structure universe C_X, constrained optimization, sticky W_X reservation, and the within-hour no-candidate recheck loop;
   - emits a broker-neutral TradeIntent when a StructureSpec is selected.

4. **Position Management — Shared Execution & Risk Management Graph**
   - common across all Graph X instances for the day;
   - owns intelligent execution and live risk decisions;
   - queries broker-derived margin feasibility;
   - delegates broker-specific transport to thin replaceable provider plug-ins such as Dhan.

**Preservation rule:** No prior decision has been discarded by this decomposition. Existing loops, capital-reservation rules, broker-independence rules, margin-feasibility dependency, optimizer behavior, and unresolved commitment-revocation question are assigned to the box that owns them.

**Architecture rule going forward:** The master graph should describe only transitions between major phases. Detailed decisions belong in the relevant box graph.


### 2026-10-03 — Vector Identity System becomes mandatory

**Decision:** Every architectural entity now receives an immutable vector ID before it is added to the workflow.

Canonical form:

`VID = [Box, Instance, Layer, Type, Ordinal]`

The coordinates encode top-level box, graph instance, logical layer, entity class, and stable ordinal. This applies to boxes, nodes, states, schedulers, arrows/transitions, future workers/agents, interfaces/ports, data contracts, broker adapters, and capital/resources.

Examples:
- Regime Gate root: `[1,0,0,0,0]`
- Multi-day Regime Gate: `[1,0,3,1,1]`
- Regime Recheck Scheduler: `[1,0,5,3,1]`
- Portfolio Capital Allocator: `[2,0,7,1,1]`
- Trade Selection template optimizer: `[3,0,5,1,1]`
- NIFTY optimizer instance: `[3,1,5,1,1]`
- BrokerMarginFeasibilityPort: `[4,0,5,6,1]`

**Trade Selection instance convention:**
- `I=0` template
- `I=1` NIFTY
- `I=2` BANKNIFTY
- `I=3` SENSEX

**Immutability rule:** Existing IDs are never renumbered or reused. Display names may change, but VIDs do not. Removed entities are tombstoned rather than recycled.

**Topology rule:** The vector identifies an entity; explicit edge/source/target relationships define the actual graph topology. This prevents future graph insertions from forcing renumbering.

**Operational rule going forward:** Every architecture edit must update both the owning graph document and the central machine-readable VID registry.


## Next workstream

### [5,0,0,0,0] External Dhan Execution Layer — bottom-up design

The next dedicated design session should focus only on the **Dhan-specific execution layer**, not on the intelligent Volarb strategy execution/risk engine in Position Management.

Scope for the next chat:
- treat the Dhan execution layer as an external plug-in / provider box;
- define the exact interface between Position Management and Dhan;
- map canonical Volarb execution commands into Dhan API operations;
- map Dhan responses, fills, rejects, positions, order states, and margin/account facts back into normalized Volarb events;
- cover Dhan-specific authentication, IP whitelisting, instrument/token mapping, connectivity, retries, idempotency, failure handling, and reconciliation;
- keep Dhan intentionally low-intelligence: it executes instructions and reports authoritative facts;
- preserve replaceability so Kotak, ICICI Securities, or another broker can later implement the same external contract.

Do **not** redesign Position Management strategy intelligence in that session unless an interface requirement from Dhan forces a contract change.

The internal graph for [5,0,0,0,0] is intentionally undefined at this point and should be designed in the next chat from the bottom up.

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


### 2026-10-03 — Internal Execution discovery baseline: existing Dhan execution substrate

**Raw intent:** Begin the bottom-up design of `[5,0,0,0,0] External Dhan Execution Layer` without inventing its final internal graph. Inspect the live `main` branch and Dhan's actual broker capabilities first. Preserve any useful existing implementation rather than rebuilding it.

**Architecture interpretation:** Internal Execution remains a thin Dhan-specific provider/execution boundary. Position Management owns strategy and risk intelligence. This discovery pass records facts about the current implementation and broker surface; it does **not** yet assign internal Internal Execution nodes or settle unresolved design choices.

**Existing implementation discovered:** `services/dhan-chatgpt-mcp/` is already a substantial Dhan integration and should be treated as reusable substrate.

Current capabilities include:
- Dhan API v2 client with profile, funds, positions, holdings, orders, trades, order-by-ID, order-by-correlation-ID, order trades, quotes, LTP, option expiries, option chain, single-order margin, multi-order margin, order placement, cancellation and static-IP lookup.
- Detailed Dhan instrument-master ingestion with index alias resolution, Security ID lookup, lot-size/freeze/tick metadata and a six-hour cache.
- Read-only MCP tools for account state, market/option data, surface analytics and sequence-aware butterfly margin preflight.
- A separate authenticated execution MCP endpoint, disabled by default.
- Static-egress readiness checking against Dhan's whitelist plus Dhan account-identity verification.
- OAuth/PKCE protection for the execution endpoint plus a private owner token and process lock.
- A durable, fsynced execution state store with write-ahead placement intent.
- Correlation IDs for recovery lookup and explicit protection against blind re-POST after an ambiguous placement.
- Fill verification against Dhan trades and positions; order acceptance alone is never treated as a fill.
- Partial-fill, rejection, cancellation-race and restart/recovery handling.
- Quote-age, spread, displayed-depth, price-band, tick-size, lot-size and freeze-quantity validation.
- Per-leg and sequence-bound margin checks.
- An existing four-leg butterfly ENTRY/EXIT executor using LIMIT / INTRADAY / DAY orders.

**Important limitation of the current executor:** `ButterflyExecutor` is not yet the final Internal Execution abstraction. It embeds butterfly-specific sequencing, entry/exit semantics, timing rules, price-repricing policy, hedge-coverage rules and other execution-policy intelligence. Under the new architecture, we must decide which of those controls belong in Position Management versus which are purely mechanical broker safeguards that legitimately remain in Internal Execution.

**Observed gaps relative to the eventual external Dhan layer:**
- no generic broker-neutral Box-4 <-> Box-5 command/event contract;
- no general-purpose Dhan executor for arbitrary canonical broker commands;
- no order-modification wrapper in the current `DhanClient`, although Dhan supports modification;
- no live Dhan order-update WebSocket or postback consumer in the current service; execution currently reconciles primarily through REST polling;
- no explicit general rate-limit governor/backoff subsystem;
- no normalized provider-wide error taxonomy yet;
- current authentication/browser recovery contains office-Mac-specific behavior and may stop for human OTP/CAPTCHA/manual verification;
- restart reconciliation intentionally fails closed when an order remains live or ambiguous rather than improvising a recovery trade;
- Dhan's multi-order margin calculator is present, but no atomic arbitrary four-leg butterfly order-placement facility has been identified in the official API documentation.

**Dhan capability facts verified from current official documentation:**
- order placement, modification and cancellation require static-IP whitelisting;
- individual access tokens are 24-hour credentials; API key/secret can be long-lived while access tokens are generated for sessions;
- order API limits are 10 requests/second, 250/minute, 1,000/hour and 7,000/day, with order modifications capped per order;
- Dhan exposes order-book/trade-book REST endpoints, order lookup by correlation ID, live order-update WebSocket and access-token-level postbacks/webhooks;
- Dhan exposes positions, funds, single-order margin and multi-order/basket margin calculation;
- Dhan exposes order slicing for quantities above freeze limits;
- Dhan exposes broker-side Super Orders, account Kill Switch, P&L-based exit and Exit All, but these are only broker capabilities at this stage and are **not** adopted as Internal Execution policy.

**Preservation rule:** Reuse the mature safety/recovery primitives already present where they fit the new boundary. Do not preserve butterfly-specific policy in Internal Execution merely because it already exists.

**VID decision:** No new internal Internal Execution VIDs are allocated by this discovery pass. `[5,0,0,0,0]` remains the only Internal Execution VID until the first internal architectural object is actually decided.


### 2026-10-03 — Internal Execution atomicity boundary: instrument-level commands, never butterflies

**Raw intent:** By the time control reaches the external Dhan execution layer, the strategy/execution intelligence has already selected the exact option contract to transact. Dhan should not be asked to "execute a butterfly" as a strategic object. Its unit of work is an individual tradable instrument instruction such as buy/sell a specific call or put at a specific strike and maturity.

**Architecture interpretation:** The Position Management -> Internal Execution execution boundary is **atomic at the instrument level**. A butterfly remains an upstream Volarb concept. Position Management decomposes any multi-leg structure into individual instrument commands and determines when each command should be issued. Internal Execution does not need to know whether a given leg belongs to a butterfly, hedge, recenter, exit, or some future strategy.

The existing `[4,0,5,7,1]` contract is therefore clarified as an **Atomic Broker-Neutral Instrument Execution Command**.

Conceptually:

```text
Position Management knows:
  "this is a butterfly and these are its legs / desired sequence"

Internal Execution receives only:
  BUY or SELL
  + exact economic instrument identity
  + size
  + later-defined execution parameters

Example semantic identity:
  underlying = NIFTY
  instrument = OPTION
  option_type = CALL
  strike = 25,000
  expiry = YYYY-MM-DD
```

**Important provider boundary:** Position Management should identify the economic contract, not pass a Dhan-specific Security ID. Internal Execution mechanically resolves the semantic instrument identity into Dhan-specific identifiers and metadata such as Security ID, exchange segment, lot size, tick size and freeze quantity. The existing Dhan instrument-master code is reusable for this translation.

**Explicitly not part of the Internal Execution command:** butterfly geometry, wing/body role, strategy name, recenter intent, substitute strikes, alternative structures or any other strategy-level meaning.

**Still unresolved:** exact quantity representation (lots versus units), price/limit fields, order type, repricing authority, sequencing rules, modification semantics and fill-driven progression. This decision fixes only the atomic execution unit.

**VID decision:** No new Internal Execution VID is created yet. This is a clarification of the existing boundary contract `[4,0,5,7,1]`, whose VID remains unchanged.


### 2026-10-03 — Fundamental correction: Internal Execution is broker-neutral optimal execution

**Raw intent:** The execution layer should not be Dhan-specific. At a given moment it may receive several already-decided instrument instructions — for example the four legs that happen to constitute a butterfly — but it does not need to know that the collection is a butterfly, caterpillar, mouse, hedge, recenter, or any other strategy object. It maintains a registry of the instrument executions currently required and an optimal-execution algorithm works that registry.

Dhan itself should be much thinner: it is the broker plug-in that actually translates and places/modifies/cancels orders and reports broker facts. If Dhan is replaced by Kotak, ICICI Securities, or another broker, Volarb should not need a new optimal-execution engine.

**Architecture interpretation:** The previous provisional meaning of Internal Execution as the "External Dhan Execution Layer" is superseded before any Internal Execution internals were allocated.

The corrected chain is:

```text
[4,0,0,0,0] Volarb Execution + Risk Management
        |
        | one or more atomic broker-neutral instrument execution intents
        v
[5,0,0,0,0] Broker-Neutral Optimal Execution Layer
        |
        | broker-neutral placement / modify / cancel / query operations
        v
Broker Execution Port
        |
        +--> Dhan provider plug-in
        +--> Kotak provider plug-in
        +--> ICICI Securities provider plug-in
        +--> future broker provider
```

**Responsibility split:**
- Position Management decides **what economic instrument actions are desired** as part of strategy/risk management.
- Internal Execution decides **how to execute the currently registered instrument intentions optimally**.
- The broker plug-in performs **broker-specific translation and transport** and returns authoritative broker facts.
- The broker plug-in does not contain the reusable optimal-execution algorithm.

**Execution registry:** Internal Execution maintains a live registry containing the atomic instrument execution intentions currently awaiting, undergoing, or completing execution. If four butterfly legs are handed down together, they appear as four instrument-level entries. Their common strategy meaning is not required by the execution algorithm unless a future explicit execution constraint says otherwise.

**Important supersession:** The earlier note that Position Management would necessarily determine when every individual leg command is issued is superseded. Position Management supplies the required instrument actions; Internal Execution owns the broker-neutral optimal execution algorithm over the registry.

**Provider identity rule:** Concrete broker plug-ins such as Dhan are now outside the numbered Volarb box/VID namespace. The Volarb-owned port through which they plug in receives a VID; the concrete provider implementation uses a provider key/name and implementation version instead of a Volarb architectural VID.

**Preserved Dhan work:** Existing code in `services/dhan-chatgpt-mcp/` remains valuable as provider-specific substrate — authentication, Security-ID resolution, order transport, broker-state retrieval, recovery primitives, etc. Its current butterfly-specific optimal/execution-policy logic is not automatically retained in the Dhan plug-in; reusable optimization belongs in Internal Execution.

**New Internal Execution internal identities:**
- `[5,0,1,9,1]` Active Instrument Execution Registry
- `[5,0,2,1,1]` Broker-Neutral Optimal Execution Engine
- `[5,0,3,6,1]` Broker Execution Port
- `[5,0,4,7,1]` Normalized Broker Execution Facts

The internals of the optimal-execution algorithm remain deliberately unresolved.


### 2026-10-03 — Internal Execution margin-aware dependency sequencing

**Raw intent:** Internal Execution uses dynamically refreshed market microstructure, account margin/capital and the current execution registry. It must infer which instruments hedge or offset others without knowing the parent strategy, and sequence execution to use margin and cash efficiently.

**Architecture interpretation:** Add normalized live market state and live broker account state as first-class Internal Execution inputs. The account state includes current positions and pending orders because existing protection and locked resources affect what can safely execute next.

**Rule:** Convert inferred hedge relationships into quantity-aware execution dependencies. Protection that is required to avoid an unnecessary unhedged/high-margin intermediate state must be confirmed before the dependent risk-adding action may proceed. On reduction/unwind, the dependency reverses when removing protection first would expose the remaining position.

**Dynamic rule:** Recompute after authoritative execution/account changes. Do not treat an expected fill, premium credit or margin release as available before the broker confirms it.

**Broker-neutrality:** Internal Execution infers structural hedge relationships. The active broker supplies authoritative current and hypothetical margin/account facts. The optimizer therefore remains reusable across brokers.


### 2026-10-03 — Internal Execution mission clarified as registry-to-position convergence

**Raw intent:** Internal Execution takes whatever exists in the execution registry and must optimally push it through execution until it actually appears in the broker account/positions. The registry is the source; the broker position state is the drain.

**Architecture interpretation:** Internal Execution is a convergence engine. It does not optimize toward "order submitted" or "order accepted." It optimizes until authoritative broker fills/positions demonstrate that the required economic position change has actually occurred.

**Important semantic distinction:** Registry items are outstanding required position deltas, not broker order tickets. One registry item may require multiple place/modify/cancel/replace attempts over time. Those broker orders are transient mechanisms for satisfying the persistent economic execution requirement.

**Completion invariant:** A registry item remains active until its required position delta is satisfied by authoritative broker state, Position Management changes/revokes the requirement, or execution enters a fail-safe/error state requiring escalation.

**Exit nuance:** "Shown in positions" means the intended final position effect. For an entry this may mean creating/increasing a position; for an exit it may mean reducing or eliminating an existing position.

**VID decision:** No new VID is required. This clarifies the purpose and terminal condition of the existing Internal Execution registry/engine/account-state objects.


### 2026-10-03 — Time-Space Execution Sub-Box inside Internal Execution

**Raw intent:** After the Internal Execution registry has passed hedge/margin eligibility rules, a separate sub-box performs true optimal execution through time. Its unit of calculation is time and current market/order state. It observes eligible remaining quantity and the LOB, then decides whether to place, reprice, cancel, wait, or use a market order.

**Architecture interpretation:** Internal Execution now has two conceptually separate execution stages.

Upper Internal Execution:
- registry;
- hedge/offset inference;
- dependency graph;
- margin-aware sequencing;
- releases only the instrument/quantity currently eligible to be worked.

Lower Internal Execution:
- [5,0,3,0,1] Time-Space Execution Sub-Box;
- consumes eligible work plus current LOB/order/fill state;
- repeatedly makes broker-neutral order-management decisions through time;
- sends those actions to the Broker Execution Port.

**Plug-and-play requirement:** Micro-execution policy is swappable behind [5,0,4,6,1] Execution Algorithm Port. The rest of Volarb must not depend on which execution algorithm is active.

**Current action space:** WAIT, PLACE_LIMIT, REPRICE_LIMIT, CANCEL_LIMIT, PLACE_MARKET.

**Hard boundary:** The temporal algorithm can choose timing, price, order type and quantity up to the released amount. It cannot make an ineligible instrument eligible, bypass margin/hedge constraints, alter instrument identity or reinterpret strategy intent.

**Clock remains open:** fixed interval, event-driven or hybrid scheduling will be decided later.


### 2026-10-03 — Architecture naming and execution cleanup

**Canonical naming rule:** Top-level modules are referred to by short semantic names, never as "Regime Gate", "Underlying Allocation", etc. Numeric identity remains only inside immutable VIDs.

Canonical modules:
- `[1,0,0,0,0]` Regime Gate
- `[2,0,0,0,0]` Underlying Allocation
- `[3,0,0,0,0]` Trade Selection
- `[4,0,0,0,0]` Position Management
- `[5,0,0,0,0]` Internal Execution

**Internal Execution layering:** Internal Execution has exactly two ordered sub-boxes:
1. `[5,0,2,0,1]` Margin Optimization
2. `[5,0,3,0,1]` Optimal Execution

Margin Optimization must release an Eligible Execution Work Slice before Optimal Execution may act. Optimal Execution may choose timing, price, order type and quantity only within that released slice.

**Repository cleanup:** Canonical workflow documents now use semantic filenames. Older numbered workflow files and the superseded Dhan-specific handoff are historical artifacts and are being removed from the active workflow set. Earlier notes that use "Box" terminology remain historical context only and are superseded by this naming rule.


### 2026-10-03 — Passive Chase default execution algorithm

**Raw intent:** Use a deliberately simple default micro-execution algorithm so the Optimal Execution workflow can be built and tested without committing to a sophisticated execution model. More complex algorithms must later be replaceable without changing the workflow.

**Name:** `[5,0,5,5,1] Passive Chase`.

**Boundary:** Passive Chase sits behind `[5,0,4,6,1] Execution Algorithm Port`. It receives only the Eligible Execution Work Slice already released by Margin Optimization plus live LOB/order/fill state. It does not reorder margin dependencies or make additional quantity eligible.

**Policy:**
- BUY: place a passive limit at the current best bid.
- SELL: place a passive limit at the current best ask.
- Do not deliberately cross the spread during the passive phase.
- Wait parameter `T`.
- Refresh the LOB and work only the confirmed unfilled remainder.
- If the passive touch moved, reprice the remaining limit to the new passive touch; if unchanged, leave it resting.
- Repeat for up to `N` passive refresh cycles.
- If quantity remains after the passive phase, cancel the resting limit, confirm/reconcile cancellation, then submit a market order for the exact confirmed remainder.
- Partial fills reduce all subsequent quantities.

**Parameters:** `T` and `N` are intentionally unspecified for now.

**Safety invariant:** Never submit the market fallback while an earlier passive limit could still fill. Ambiguous cancellation must reconcile before a market order is allowed.

**Plug-and-play rule:** Passive Chase is the current default only. Replacing it with a future execution algorithm must not change Margin Optimization, Position Management, the Temporal Execution Decision contract, Broker Execution Port, or provider implementations.


### 2026-10-03 — Mandatory sequence handoff into Optimal Execution

**Raw intent:** Margin Optimization does not merely decide that several instruments are eligible. It must provide the execution sequence to Optimal Execution. Otherwise the downstream execution algorithm could choose instruments in an arbitrary order and violate the margin/hedge logic.

**Architecture rule:** Margin Optimization always emits `[5,0,2,7,2] Execution Sequence Plan`, even when the plan contains only one step.

**Optimal Execution rule:** `[5,0,3,1,1] Sequence Enforcer` is a hard algorithm-independent constraint. It releases only the current sequence step as `[5,0,3,7,1] Eligible Execution Work Slice`.

**Fail-closed rule:** No valid sequence -> no execution. Optimal Execution must never invent an ordering.

**Plug-in rule:** Every execution algorithm, including the current Passive Chase default and any future replacement, may optimize only how the current step is executed. It may not reorder, skip, or select future steps.

**Separation:** Margin Optimization decides ORDER. Optimal Execution decides HOW to execute the current ordered step.


### 2026-10-03 — Ordering may be explicitly unconstrained

**Correction:** Margin Optimization must not invent a sequence when no hedge or margin dependency requires one.

Its mandatory output is now an **Execution Ordering Plan**, not necessarily an execution sequence.

Two modes are valid:
- `ORDERED`: precedence constraints exist and Optimal Execution must obey them.
- `UNCONSTRAINED`: Margin Optimization explicitly determined that no sequencing constraint exists among the released items.

Example: several independent long option purchases may be UNCONSTRAINED if none relies on another for hedge or margin feasibility.

**Optimal Execution behavior:** Ordering Constraint Enforcer applies the plan. ORDERED releases only currently permitted work. UNCONSTRAINED releases all otherwise eligible items and allows the selected execution algorithm to choose order or concurrency.

**Fail-closed rule:** Missing or invalid ordering decision means no execution. UNCONSTRAINED is a valid explicit decision and must not be confused with a missing sequence.

**Passive Chase default:** In UNCONSTRAINED mode, Passive Chase may work all released items independently, each with its own passive order, T timer and N-cycle counter.


### 2026-10-03 — NVIC-inspired Interrupt Control

**Raw intent:** Internal Execution needs a nested vectored interrupt mechanism so emergency control can preempt whatever Margin Optimization or Optimal Execution is currently doing.

**Architecture:** `[5,0,6,0,1] Interrupt Control` is an orthogonal supervisory sub-box, not a third stage in the normal chain.

**Current vector table:**
- **L1 CANCEL_WORK:** cancel all working/unfilled orders in scope and block normal convergence from recreating them.
- **L2 FLATTEN_SCOPE:** cancel/reconcile scoped orders, then bypass the normal execution algorithm and market-flatten confirmed positions in that scope.
- **L3 FLATTEN_ALL:** highest priority; cancel/reconcile all controlled working orders and market-flatten all controlled positions.

**Nested priority:** L3 > L2 > L1 > normal execution. Higher interrupts preempt lower handlers. Lower interrupts cannot downgrade a higher active emergency.

**Latch rule:** Interrupt state persists after cancellation/flatten actions. Normal work in the affected scope does not resume automatically; an authorized clear/resume is required.

**Emergency execution boundary:** Emergency market actions bypass Passive Chase / the plug-in Optimal Execution algorithm, but still go through the broker-neutral Broker Execution Port and authoritative broker reconciliation.

**Flatten semantics:** Longs are sold; shorts are bought back. Emergency scope must be explicit and broker-neutral.

### 2026-10-03 — Internal Execution completion pass

The architecture audit identified three missing cross-cutting controls and one additional normal-flow layer.

**Execution Slicing `[5,0,7,0,1]`:** inserted between Margin Optimization and Optimal Execution. It converts permitted instrument quantity into execution slices. Canonical terminology uses "slice" rather than "leg" to avoid confusion with option-strategy legs. Default is `slice_count=1`, `scheduling_mode=SEQUENTIAL`. Future large positions may use multiple slices; under the default scheduler each slice is sent through Optimal Execution and reconciled before the next slice is released.

**Runtime intent versioning `[5,0,1,7,3]`:** live execution requirements now carry `intent_id`, `intent_version`, supersession and status. This is distinct from architectural VIDs. Broker mutations generated under stale/superseded versions are rejected.

**Execution Recovery `[5,0,8,0,1]`:** broker-neutral write-ahead ledger and reconciliation layer. Every normal or interrupt broker mutation passes through Command Commit Guard and Execution Ledger before the Broker Execution Port. Ambiguous mutation outcome means reconcile, never blind retry. Recovery handles restart, timeout, partial-fill ambiguity and correlation to broker truth.

**State Integrity `[5,0,9,0,1]`:** action-class-aware readiness guard over market/account/order/recovery state. Stale/unknown truth cannot create new exposure. Emergency cancel/flatten has separate minimum-integrity requirements and reports unresolved emergency if those cannot be met.

**Canonical normal path:** Margin Optimization -> Execution Slicing -> Optimal Execution -> Execution Recovery / Command Commit Guard -> Broker Execution Port.

**Cross-cutting:** State Integrity gates action permission; Interrupt Control can preempt normal flow; Execution Recovery applies to both normal and interrupt broker mutations.

### Deferred Internal Execution implementation tasks

Do not implement these now; resume after the Dhan broker layer is designed.

- [ ] Internal Execution implementation stack: benchmark architecture/software choices with execution latency as a first-class constraint; explicitly compare C, C++, Rust, Python orchestration, FFI boundaries, process topology, IPC/shared-memory options, and where low-level native code is actually justified.
- [ ] Internal Execution latency budget: define end-to-end latency targets and per-stage budgets for State Integrity, Margin Optimization, Execution Slicing, Optimal Execution, Command Commit Guard, broker transport, acknowledgement, and reconciliation.
- [ ] Internal Execution concurrency model: decide event loop/threading/process model, lock/ownership rules, timer model, and deterministic ordering under concurrent market/order events.
- [ ] Internal Execution production implementation: build the architecture from the canonical VIDs/contracts without leaking Dhan-specific logic into the core.
- [ ] Internal Execution exhaustive tests: unit tests for every node/contract plus integration tests across ordering, unconstrained execution, slicing, Passive Chase, interrupts, supersession, recovery, and State Integrity.
- [ ] Internal Execution property/invariant tests: prove/enforce no stale-intent execution, no quantity overfill, no ordering violation, no interrupt bypass, no duplicate broker mutation after ambiguity, and no new risk under invalid state.
- [ ] Internal Execution fault-injection tests: simulate timeouts, disconnects, duplicate/out-of-order broker events, partial fills, cancel/modify races, restart recovery, stale quotes, stale account state, and broker unavailability.
- [ ] Internal Execution large-scale simulator: simulate thousands to millions of execution scenarios over synthetic/replayed LOB paths, fills, slippage, queue behavior, partial fills, interrupts, supersessions, and recovery events.
- [ ] Internal Execution performance benchmarking: measure throughput, p50/p95/p99 latency, jitter, CPU/memory usage, lock contention, serialization overhead, and recovery latency under stress.
- [ ] Execution Slicing research: later design dynamic slice count/size/scheduling for large positions (e.g. 100-200 lots), while keeping default slice_count=1 and SEQUENTIAL until validated.
- [ ] Optimal Execution algorithm research: keep Passive Chase as default baseline, then compare more sophisticated plug-ins without changing the Execution Algorithm Port or workflow.
- [ ] Internal Execution paper-trading / shadow deployment: run against live market/broker state without live mutation first, compare intended versus hypothetical/actual fills, and validate reconciliation before enabling production execution.


### 2026-10-03 — Dhan provider boundary audit

**Scope:** Audited the live `services/dhan-chatgpt-mcp/` implementation against the now-frozen broker-neutral Internal Execution boundary and current official DhanHQ v2 capabilities.

**Keep as Dhan mechanics:** authentication/token renewal and private credential handling; static-IP/account observations; instrument-master acquisition and broker metadata; HTTP transport; order/correlation/trade/position/funds reads; single/basket margin APIs; quote APIs; order/trade identity-validation patterns; correlation-based investigation; provider-local process/auth/stream safety primitives.

**Move conceptually upstream:** butterfly leg roles and sequencing, hedge rules, session/deadline policy, quote/spread/depth acceptance policy, passive repricing/wait loops, automatic cancel/replace decisions, capital reserve/affordability policy, preview confirmation, and broker-neutral write-ahead/recovery policy. The current `ButterflyExecutor` is a mixed legacy implementation, not the future Broker Execution Port.

**Target provider shape:** unnumbered DhanProvider façade with auth/readiness, generic instrument catalog/resolver, transport, generic order gateway, broker-state reader, margin reader, market-data adapter, order-event adapter, normalization/error classification, and provider-local runtime state.

**Critical missing Dhan primitives:** generic placement instead of forced LIMIT/INTRADAY/DAY, modify-order, MARKET-order support, generic contract resolution, deterministic core-correlation -> Dhan-correlation projection, normalized ambiguity/provenance/timestamps, historical trade backfill, live market feed, live order updates, rate-limit/capability state, and separation of provider runtime state from the Volarb Execution Ledger.

**Composite Dhan actions:** do not use native `/orders/slicing` for the initial port because Volarb owns Execution Slicing. Do not use Dhan `DELETE /positions` as the default L3 `FLATTEN_ALL` because it is broker-wide and can touch unmanaged exposure. Dhan Kill Switch/P&L exits remain broker operations/control-plane features, not implementations of Volarb Interrupt Control.

**Recovery rule preserved:** no provider-side blind retry of an ambiguous mutation. Dhan exposes correlation/order/trade/position primitives; `[5,0,8,0,1] Execution Recovery` owns the decision to reconcile/resume.

**VID decision:** no new VID. Concrete Dhan provider internals remain outside the Volarb VID namespace.

Canonical detail: `docs/providers/dhan-execution.md`.


### 2026-10-03 — Dhan provider independence and speed

**Raw intent:** Dhan is a reusable broker box, not an execution or strategy box. It should do only what is asked: execute an explicitly requested broker operation or return explicitly requested broker information. The caller may be Internal Execution, a strategy/research component, monitoring, or another future workflow; Dhan itself does not care.

**Canonical Dhan jobs:** COMMAND, QUERY, and a non-decision-making STREAM transport for continuous facts. No strategy geometry, sequencing, slicing, repricing, hedging, timing, capital policy or decision logic belongs in the provider core.

**Current Volarb mutation safety:** production Internal Execution mutations still pass through Command Commit Guard / Execution Ledger before Broker Execution Port. This is a caller/core invariant, not a reason to couple Dhan to Internal Execution.

**Speed rule:** provider overhead must stay close to unavoidable broker/network latency. No LLM/MCP reasoning, policy loops, sleeps, strategy work or provider-owned fsync ledger in the hot path. Pre-resolve instruments, keep indexed metadata in memory, keep transport/process warm, prefer Dhan WebSocket market/order streams for live state, use REST for snapshots/reconciliation, parallelize independent reads when coherent, and benchmark p50/p95/p99 instead of inventing latency targets.

**Implementation:** added strategy-agnostic `src/dhan-provider.mjs`; added generic exact `placeOrder` and `modifyOrder` while retaining legacy `placeLimitOrder`; added indexed exact `InstrumentMaster.resolveInstrument`. Existing butterfly executor remains compatibility code, not the canonical Dhan provider contract.

**Errors (superseded below):** this was deliberately deferred until Aryan specified the broker-neutral error connector requirement.

**VID decision:** none. Dhan remains an external unnumbered provider.


### 2026-10-03 — Global provider error convention

**Raw intent:** Dhan has two jobs: provide requested information and perform requested broker actions. Failure to do either is an error. No caller should need to understand Dhan-specific errors because the active broker may later be ICICI Securities, Kotak, or another provider.

**Global invariant:** no provider-native error crosses into a Volarb box. Every provider adapter maps every native failure into `[0,0,1,7,1] Provider Error Envelope`.

**Stable categories:** CONFIGURATION, AUTHENTICATION, AUTHORIZATION, ACCOUNT_STATE, RATE_LIMIT, INVALID_REQUEST, ORDER_REJECTED, DATA_UNAVAILABLE, RESOURCE_NOT_FOUND, PROVIDER_INTERNAL, NETWORK, TIMEOUT, PROTOCOL, UNSUPPORTED, UNKNOWN.

**Total mapping rule:** documented native codes receive explicit mappings; every undocumented/new/uncategorized provider failure maps to UNKNOWN while retaining provider-native diagnostic provenance. Therefore there is no unmapped error path.

**Provenance:** preserve provider key, native error code/type/message, HTTP status, OMS rejection code/description and endpoint. Callers must branch on global category/code/outcome, never on Dhan-specific values.

**Mutation certainty:** error category is separate from whether a command may have taken effect. Query/stream failures use NOT_APPLICABLE; definitive command refusal uses KNOWN_NOT_APPLIED; timeout/network/protocol/provider-internal/unknown command failures use UNKNOWN when the mutation may have crossed the transport boundary. This is information only; recovery/retry policy remains upstream.

**Dhan implementation:** `provider-error.mjs` defines the global contract, `dhan-error-mapper.mjs` maps all currently documented Dhan Trading/Data codes and fallbacks, and every canonical `DhanProvider` method passes failures through that mapper. A 2xx order response with REJECTED status is normalized as ORDER_REJECTED. Raw Dhan exceptions remain internal.

**VID:** allocated `[0,0,1,7,1] Provider Error Envelope` under Master Architecture because the convention is global rather than owned by any one strategy, Position Management, Internal Execution, or broker.


### 2026-10-03 — Compositional identity architecture

**Decision:** Internal Execution is no longer strategy-owned. The existing `[5,0,...]` namespace is preserved without renumbering and is reinterpreted as the canonical VID namespace of reusable component `component.internal_execution`.

**Three identity levels:** CVID = immutable identity inside a reusable component; BVID = composition + mount + canonical identity for one mounted occurrence; RID = live intent/version/slice/action/correlation/provider identity. Mounting never changes a CVID.

**Volarb composition:** `composition.volarb` mounts Internal Execution at `mount.volarb.execution.main` and mounts `provider.dhan` below it at `mount.volarb.execution.main.broker.primary`. The strategy->execution intent, execution->strategy facts, strategy->interrupt and execution->broker relationships are explicit composition-owned bindings with stable binding IDs.

**Cross-edge migration:** legacy edges `[0,0,5,4,1]`, `[0,0,4,4,1]` and `[0,0,6,4,1]` remain for compatibility but now point to the authoritative bindings in `architecture/strategies/volarb/composition.json`.

**Dhan:** canonical component identity `provider.dhan`; no Volarb VID. A mount identity and binding identity describe where it is plugged in without contaminating provider identity.

**Runtime propagation:** Runtime Intent Identity, Execution Action Envelope and Execution Ledger now explicitly carry composition/mount/canonical execution context so simultaneous mounts cannot collide.

**Files:** canonical component manifests/registries and composition registries live under `architecture/`; `docs/workflows/vector-id-registry.json` is retained as an assembled compatibility view. `architecture/validate.mjs` and the architecture CI workflow enforce mirror, mount, binding and namespace invariants.


### 2026-10-03 — Dhan production Broker Execution Port implementation

**Call-site derivation:** Internal Execution needs Dhan for State Integrity facts, Margin Optimization facts, Optimal Execution market/order actions, Execution Recovery reconciliation, and Interrupt Control cancel/flatten actions. Execution Slicing has no Dhan dependency.

**Implemented connector:** `DhanBrokerPort.call({kind, operation, payload})` with a small broker-neutral operation vocabulary. Strategy legs are ordinary order requests; no butterfly/body/wing semantics exist in Dhan.

**Configuration:** added provider-owned configuration and readiness. Missing client/credential configuration emits global `PROVIDER.NOT_CONFIGURED`. Commands additionally require provider commands enabled, configured+confirmed static egress IP, live egress match, Dhan whitelist match and Dhan account identity match; failures emit `PROVIDER.MUTATION_NOT_READY` before transmission.

**Speed:** warm runtime, indexed instrument master, cached command readiness, concurrent account snapshot, no MCP/LLM/policy/ledger/sleep in the broker hot path, provider elapsed-microsecond instrumentation.

**Facts:** added broker-neutral normalizers for orders, trades, positions, funds, margin, instruments, quotes/LTP and mutation acknowledgements. Dhan-specific identifiers survive only inside provider reference/provenance fields.

**Recovery:** added historical trade backfill endpoint support.

**Margin boundary:** an indicative margin shortfall is returned as data, not raised as an error. Only an actual broker/RMS rejection becomes a Provider Error. This preserves Margin Optimization ownership.

**Streams:** live Dhan market and account-wide order-update WebSockets are now implemented behind the Broker Port. Market TICKER/QUOTE/FULL binary packets are normalized, subscriptions are batched to Dhan limits, and account-wide order updates are normalized into broker facts. REST remains the bootstrap/snapshot/reconciliation path.

**VID:** no new provider VID. Existing global `[0,0,1,7,1] Provider Error Envelope` remains the error contract.


**Broker-neutral translation:** Internal Execution no longer needs to construct Dhan-native order/margin/quote payloads. `dhan-translator.mjs` translates provider-neutral order fields and opaque provider instrument references into Dhan mechanics. Core correlation IDs are deterministically projected to stable 30-character Dhan correlation references and reused by correlation lookup/recovery.


### 2026-10-03 — Execution Engine rename and deterministic testbed

**Rename:** the reusable strategy-agnostic `[5,0,...]` component is canonically **Execution Engine** (`component.execution_engine`). All VIDs remain unchanged. `component.internal_execution` is a compatibility alias only.

**Strategy-specific boundary:** any execution logic that interprets butterfly/condor/recenter/strategy semantics belongs upstream in an optional Strategy Execution Adapter. Volarb may bind directly when Position Management already emits a broker-neutral economic execution requirement.

**Environment rule:** there is one Execution Engine implementation. No `test_mode` branch is permitted inside it. Broker, market, clock, ledger/persistence and randomness are injected dependencies.

**Testbed:** added `execution-testkit/` with deterministic VirtualClock, SeededRng, EventTrace, MemoryExecutionLedger, SimulatedMarket, SimulatedBroker, FaultInjector, ComponentHarness, scenario/mass runners and invariant checking.

**Test levels:** box-only, selected composition, whole-engine deterministic scenario, seed-addressable mass simulation, replay/shadow, then production.

**Production separation:** `environments/execution/production.json` explicitly mounts only real runtime classes and forbids `execution-testkit`; test/replay/shadow explicitly prohibit real broker mutations.

**Broker contract:** the provider-neutral Broker Operation vocabulary is now owned by `execution-engine/ports/broker-port.mjs`; Dhan and the simulator implement the same contract.

**Simulation semantics:** simulator supports partial fills, fill/cancel races, definitive rejection, acknowledgement loss after application, query/reconciliation, positions/trades, margin facts, market/order streams and injected faults on virtual time.

**Initial invariants:** no overfill; ledger before mutation; no blind retry after ambiguous broker outcome until reconciliation; no stale-intent mutation.

**VID:** no new execution VID allocated for the testkit. Test infrastructure is external tooling, not execution architecture.
