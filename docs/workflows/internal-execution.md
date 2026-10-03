# [5,0,0,0,0] Internal Execution

Internal Execution is the broker-neutral convergence module that turns outstanding instrument-level position requirements into authoritative broker positions.

It has exactly two ordered sub-boxes:

1. **[5,0,2,0,1] Margin Optimization**
2. **[5,0,3,0,1] Optimal Execution**

The second sub-box cannot work anything that the first has not explicitly sequenced and released.

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
    Q["[5,0,2,7,2] Execution Sequence Plan"]

    OE["[5,0,3,0,1] Optimal Execution"]
    G["[5,0,3,1,1] Sequence Enforcer"]
    W["[5,0,3,7,1] Eligible Execution Work Slice"]
    C["[5,0,4,1,1] Temporal Execution Controller"]
    P["[5,0,4,6,1] Execution Algorithm Port"]
    X["[5,0,5,5,1] Passive Chase\n(current default plug-in)"]
    O["[5,0,4,7,2] Temporal Execution Decision"]

    B["[5,0,3,6,1] Broker Execution Port"]
    F["[5,0,4,7,1] Normalized Broker Execution Facts"]
    E["External broker provider\nDhan / Kotak / ICICI / ..."]

    R --> MO
    M --> MO
    A --> MO
    MO --> H --> D --> S --> Q

    Q --> OE
    M --> OE
    OE --> G --> W --> C --> P --> X --> O --> B

    B --> E
    E --> B
    B --> F
    F --> R
    F --> M
    F --> A
~~~

Concrete broker providers are external plug-ins and do not receive Volarb VIDs.

# Inputs

## [5,0,1,9,1] Active Instrument Execution Registry

The registry contains outstanding required economic position deltas, not broker order tickets.

A registry item remains active until authoritative broker state shows that its required position effect has been achieved, Position Management changes or revokes the requirement, or execution enters a fail-safe state requiring escalation.

## [5,0,1,7,1] Live Market Execution State

Broker-neutral market microstructure used by execution, including as available:

- bid and ask;
- executable depth / LOB;
- spread;
- quote freshness;
- price bands and tradability.

## [5,0,1,7,2] Live Broker Account State

Authoritative execution-capacity state, including:

- available cash / collateral / margin;
- current positions;
- pending orders;
- resources already locked by working orders;
- other account facts required for execution feasibility.

These inputs are dynamically refreshed.

# [5,0,2,0,1] Margin Optimization

Margin Optimization is the first sub-box.

Its job is to decide the valid **execution ordering** and the quantity constraints required to preserve hedge dependencies and use account resources efficiently.

It does not choose order price, order type, or order timing.

## [5,0,2,1,2] Hedge / Offset Relationship Analyzer

This node infers structural protection relationships from instrument economics, current positions, pending orders, and desired position changes.

It does not use strategy labels such as butterfly, condor, wing, or body.

Coverage may be partial or quantity-dependent.

A protective order counts only when the relevant quantity is actually filled; submission alone does not establish protection.

## [5,0,2,7,1] Execution Dependency Graph

Hedge relationships become quantity-aware precedence constraints.

For risk-adding actions, protection required to avoid an unnecessary naked or high-margin intermediate state must be established before the dependent exposure may execute.

For reductions or exits, the dependency reverses when removing protection first would leave avoidable unhedged exposure.

## [5,0,2,1,3] Margin Sequence Optimizer

Among dependency-valid actions, this node constructs the required execution order across the outstanding work.

Its current objective component is:

1. preserve required protection;
2. avoid unnecessary high-margin intermediate states;
3. reduce peak cash / collateral / margin required;
4. use only broker-confirmed cash or margin effects from completed execution.

Structural hedge logic is broker-neutral. Actual rupee margin impact is broker-authoritative and may be queried through the Broker Execution Port.

## [5,0,2,7,2] Execution Sequence Plan

This is the mandatory output of Margin Optimization.

It is an explicit ordered plan describing the sequence in which instrument-level work is allowed to progress.

Conceptually:

~~~text
sequence_version = ...

steps:
  1. instrument A / side / quantity constraint
  2. instrument B / side / quantity constraint
  3. instrument C / side / quantity constraint
  ...
~~~

The plan is required even when only one item is present.

**There is no unsequenced execution path.**

If Margin Optimization cannot produce a valid sequence, Optimal Execution receives no executable work and must fail closed rather than choose an item itself.

Only Margin Optimization may create or revise the ordering.

# [5,0,3,0,1] Optimal Execution

Optimal Execution is the second sub-box.

Its first responsibility is to obey the Execution Sequence Plan.

Its second responsibility is to optimize the currently permitted sequence step through time and the LOB.

It does not decide which sequence step should come next.

## [5,0,3,1,1] Sequence Enforcer

Sequence Enforcer is a hard constraint inside Optimal Execution and is independent of whichever execution algorithm plug-in is active.

It:

- requires a valid Execution Sequence Plan;
- identifies the currently active sequence step;
- prevents later steps from being selected early;
- prevents a plug-in from skipping or reordering steps;
- releases only the instrument and quantity currently permitted by the plan;
- advances only when authoritative broker state satisfies the completion condition for the current step;
- stops execution if the sequence is missing, invalid, stale, or cannot be reconciled with authoritative broker state.

A different execution algorithm may change **how** the current step is worked, but never **which step** is current.

## [5,0,3,7,1] Eligible Execution Work Slice

This is the current sequence step released by Sequence Enforcer to the micro-execution layer.

Conceptually it contains:

~~~text
sequence_version
sequence_step
instrument
side
remaining step quantity
maximum quantity currently eligible to work
execution constraints inherited from upstream
~~~

It says **what may be worked now**. It does not say how to price or time the order.

## Time-indexed state

At decision time t:

~~~text
state_t
  = current eligible sequence step
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

The exact clock may be fixed interval, event-driven, or hybrid depending on the selected algorithm.

## [5,0,4,1,1] Temporal Execution Controller

The controller:

- assembles the current time-t execution state;
- invokes the active execution algorithm;
- validates the returned action against both the active sequence step and the eligible work slice;
- sends the broker-neutral action to the Broker Execution Port;
- consumes authoritative order/fill feedback;
- updates remaining quantity;
- invokes the algorithm again when required.

The controller is orchestration. Execution policy is plug-and-play.

## [5,0,4,6,1] Execution Algorithm Port

Interchangeable execution algorithms implement this interface:

~~~text
current sequence-constrained execution state
        |
        v
selected execution algorithm
        |
        v
execution decision at time t
~~~

The current default implementation is [5,0,5,5,1] Passive Chase.

Changing the selected algorithm must not require changes to Margin Optimization, Sequence Enforcer, Position Management, the Broker Execution Port, or the broker provider.

**Every algorithm is constrained by the same active sequence.**

## Current default: [5,0,5,5,1] Passive Chase

Passive Chase works only the current sequence step handed to it by Sequence Enforcer.

Its deliberately simple policy is:

1. BUY -> place a limit order at the current best bid.
2. SELL -> place a limit order at the current best ask.
3. Do not deliberately cross the spread during the passive phase.
4. Wait parameter T.
5. If quantity remains, refresh the LOB and reprice the remaining quantity to the current passive touch when that touch has changed.
6. Repeat for up to N passive refresh cycles.
7. After the passive phase is exhausted, cancel the working limit, confirm/reconcile that cancellation, and use a market order for the exact confirmed remainder.
8. Partial fills always reduce the quantity worked by subsequent actions.

T and N remain configuration parameters.

Detailed plug-in specification: [../execution-algorithms/passive-chase.md](../execution-algorithms/passive-chase.md)

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

The execution algorithm may choose timing, order type, price, and quantity up to the released amount.

It may not:

- choose a different sequence step;
- reorder or skip the Execution Sequence Plan;
- make an ineligible instrument eligible;
- exceed the quantity released by Sequence Enforcer;
- reinterpret hedge relationships;
- bypass margin constraints;
- change the economic instrument;
- change strategy intent.

# Sequence invariant

For every Optimal Execution algorithm:

~~~text
Margin Optimization decides ORDER
Optimal Execution algorithm decides HOW TO EXECUTE THE CURRENT STEP
~~~

Therefore:

~~~text
Execution Sequence Plan
        |
        v
Sequence Enforcer
        |
        v
Current Eligible Execution Work Slice
        |
        v
Execution Algorithm
~~~

The execution algorithm never receives permission to select freely among future sequence steps.

**No valid sequence -> no execution.**

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
