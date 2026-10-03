# [5,0,0,0,0] Internal Execution

Internal Execution is the broker-neutral convergence module that turns outstanding instrument-level position requirements into authoritative broker positions.

It has exactly two ordered sub-boxes:

1. **[5,0,2,0,1] Margin Optimization**
2. **[5,0,3,0,1] Optimal Execution**

The second cannot work quantity that the first has not released.

## Architecture

~~~mermaid
flowchart TD
    R["[5,0,1,9,1] Active Instrument Execution Registry"]
    M["[5,0,1,7,1] Live Market Execution State"]
    A["[5,0,1,7,2] Live Broker Account State"]

    MO["[5,0,2,0,1] Margin Optimization"]
    H["[5,0,2,1,2] Hedge / Offset Relationship Analyzer"]
    D["[5,0,2,7,1] Execution Dependency Graph"]
    S["[5,0,2,1,3] Margin Sequence Optimizer"]

    W["[5,0,3,7,1] Eligible Execution Work Slice"]

    OE["[5,0,3,0,1] Optimal Execution"]
    C["[5,0,4,1,1] Temporal Execution Controller"]
    P["[5,0,4,6,1] Execution Algorithm Port"]
    X["Plug-and-play execution algorithm"]
    O["[5,0,4,7,2] Temporal Execution Decision"]

    B["[5,0,3,6,1] Broker Execution Port"]
    F["[5,0,4,7,1] Normalized Broker Execution Facts"]
    E["External broker provider\nDhan / Kotak / ICICI / ..."]

    R --> MO
    M --> MO
    A --> MO
    MO --> H --> D --> S --> W

    W --> OE
    M --> OE
    OE --> C --> P --> X --> O --> B
    B --> E
    E --> B
    B --> F
    F --> R
    F --> M
    F --> A
~~~

Concrete broker providers are external plug-ins and do not receive Volarb VIDs.

## Inputs

### [5,0,1,9,1] Active Instrument Execution Registry

The registry contains outstanding required economic position deltas, not broker order tickets.

A registry item remains active until authoritative broker state shows that its required position effect has been achieved, Position Management changes or revokes the requirement, or execution enters a fail-safe state requiring escalation.

### [5,0,1,7,1] Live Market Execution State

Broker-neutral market microstructure used by execution, including as available:

- bid and ask;
- executable depth / LOB;
- spread;
- quote freshness;
- price bands and tradability.

### [5,0,1,7,2] Live Broker Account State

Authoritative execution-capacity state, including:

- available cash / collateral / margin;
- current positions;
- pending orders;
- resources already locked by working orders;
- other account facts required for execution feasibility.

These inputs are dynamically refreshed.

# [5,0,2,0,1] Margin Optimization

Margin Optimization is the first sub-box.

Its job is to decide **which instrument and how much quantity may be worked now** while preserving hedge dependencies and using account resources efficiently.

It does not choose order price, order type, or order timing.

## [5,0,2,1,2] Hedge / Offset Relationship Analyzer

This node infers structural protection relationships from instrument economics, current positions, pending orders, and desired position changes.

It does not use strategy labels such as butterfly, condor, wing, or body.

Coverage may be partial or quantity-dependent.

A protective order counts only when the relevant quantity is actually filled; submission alone does not establish protection.

## [5,0,2,7,1] Execution Dependency Graph

Hedge relationships become quantity-aware precedence constraints.

For risk-adding actions, protection that is required to avoid an unnecessary naked or high-margin intermediate state must be established before the dependent exposure is allowed to execute.

For reductions or exits, the dependency reverses when removing protection first would leave avoidable unhedged exposure.

## [5,0,2,1,3] Margin Sequence Optimizer

Among dependency-valid actions, this node chooses the next instrument and maximum quantity that may be worked.

Its current objective component is:

1. preserve required protection;
2. avoid unnecessary high-margin intermediate states;
3. reduce peak cash / collateral / margin required;
4. use only broker-confirmed cash or margin effects from completed execution.

Structural hedge logic is broker-neutral. Actual rupee margin impact is broker-authoritative and may be queried through the Broker Execution Port.

## [5,0,3,7,1] Eligible Execution Work Slice

This is the only output passed from Margin Optimization into Optimal Execution.

Conceptually it contains:

~~~text
instrument
side
remaining registry quantity
maximum quantity currently eligible to work
execution constraints inherited from upstream
~~~

It says **what may be worked now**. It does not say how.

# [5,0,3,0,1] Optimal Execution

Optimal Execution is the second sub-box.

Its job is to decide **how to work the currently eligible quantity through time and the LOB**.

It does not reason about hedge construction, margin sequencing, butterflies, iron condors, or strategy intent.

## Time-indexed state

At decision time t:

~~~text
state_t
  = eligible work
  + LOB / quote state
  + own live orders
  + fills / partial fills
  + remaining eligible quantity
  + inherited execution constraints
~~~

The execution loop is:

~~~text
S_t -> A_t -> broker facts -> S_(t+1) -> A_(t+1) -> ...
~~~

The exact clock remains open: fixed interval, event-driven, or hybrid.

## [5,0,4,1,1] Temporal Execution Controller

The controller:

- assembles the current execution state;
- invokes the active execution algorithm;
- validates the returned action against the eligible work slice;
- sends the broker-neutral action to the Broker Execution Port;
- consumes authoritative order/fill feedback;
- updates remaining quantity;
- invokes the algorithm again when required.

The controller is orchestration. Execution policy is plug-and-play.

## [5,0,4,6,1] Execution Algorithm Port

Interchangeable execution algorithms implement this interface:

~~~text
execution_state_at_t
        |
        v
selected execution algorithm
        |
        v
execution_decision_at_t
~~~

Specific algorithms will be designed later and receive identities only when actually introduced.

Changing the selected algorithm must not require changes to Margin Optimization, Position Management, the Broker Execution Port, or the broker provider.

## [5,0,4,7,2] Temporal Execution Decision

Current broker-neutral action vocabulary:

~~~text
WAIT

PLACE_LIMIT
  quantity
  limit_price

REPRICE_LIMIT
  existing_order_reference
  new_limit_price
  optional new_quantity

CANCEL_LIMIT
  existing_order_reference

PLACE_MARKET
  quantity
~~~

Limit orders are expected to be the normal case. Market orders remain an explicit action when allowed by the selected algorithm and inherited constraints.

The execution algorithm may choose timing, order type, price, and quantity up to the released amount.

It may not:
- make an ineligible instrument eligible;
- exceed the quantity released by Margin Optimization;
- reinterpret hedge relationships;
- bypass margin constraints;
- change the economic instrument;
- change strategy intent.

# Broker boundary

## [5,0,3,6,1] Broker Execution Port

This is the broker-neutral interface to external providers.

Provider implementations handle:
- broker authentication;
- instrument/security identifier translation;
- place / modify / cancel / query operations;
- broker-specific connectivity and operational requirements;
- authoritative order, fill, position, funds and margin facts.

Dhan, Kotak, ICICI Securities, and future providers sit below this port.

## [5,0,4,7,1] Normalized Broker Execution Facts

Provider facts are normalized before they update Internal Execution state.

These facts include authoritative order acknowledgement, fills, partial fills, rejection, cancellation, positions, and relevant account/margin state.

# Completion invariant

Internal Execution optimizes toward **position-state convergence**, not API acknowledgement.

Broker orders are transient attempts used to satisfy persistent registry requirements.

A registry item completes only when authoritative broker state shows that the required economic position delta has been realized.
