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

**Future design task:** Define how the regime box is built, calibrated, validated, refreshed intraday, and how quickly it can change state. This remains open and should be designed separately rather than prematurely embedded in another module.


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

## Open questions / unresolved design choices

- What decisions should be fully autonomous versus require human approval?
- What exact instruments, expiries, entry windows, and butterfly constructions are in scope?
- What market-regime conditions should permit or forbid short-gamma deployment?
- How should the regime detector be built, calibrated and validated?
- Should regime state be market-wide, underlying-specific, expiry-specific, or a hierarchy of all three?
- How frequently should regime state be recomputed, and what evidence is required before switching states?
- Should the regime gate output only eligible/ineligible/uncertain, or also a confidence score and risk-intensity recommendation?
- How should the research laboratory feed evidence into the live trading system without creating look-ahead or uncontrolled adaptation?
- What are the hard portfolio, loss, margin, liquidity, and execution-risk limits?
- What should trigger hold, recenter, hedge, scale, or square-off actions?
- What broker/execution infrastructure should the bot eventually control?
- Should research data and decision-time historical data share one canonical market-data schema while retaining separate provider capabilities?
- Which broker-neutral identifiers should Volarb own for underlyings, expiries, strikes, option types and contracts, and where should broker token mapping live?
- How should the system express provider capability differences without contaminating strategy logic?
