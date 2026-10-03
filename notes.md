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
- How should shared capital and risk be reserved across multiple underlying graphs launched in parallel?
- Should the regime gate output only eligible/ineligible/uncertain, or also a confidence score and risk-intensity recommendation?
- How should the research laboratory feed evidence into the live trading system without creating look-ahead or uncontrolled adaptation?
- What are the hard portfolio, loss, margin, liquidity, and execution-risk limits?
- What should trigger hold, recenter, hedge, scale, or square-off actions?
- What broker/execution infrastructure should the bot eventually control?
- Should research data and decision-time historical data share one canonical market-data schema while retaining separate provider capabilities?
- Which broker-neutral identifiers should Volarb own for underlyings, expiries, strikes, option types and contracts, and where should broker token mapping live?
- How should the system express provider capability differences without contaminating strategy logic?
