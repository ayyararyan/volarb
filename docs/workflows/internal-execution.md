# [5,0,0,0,0] Internal Execution

Internal Execution is the broker-neutral convergence module that turns outstanding instrument-level position requirements into authoritative broker positions.

It has exactly two ordered sub-boxes:

1. **[5,0,2,0,1] Margin Optimization**
2. **[5,0,3,0,1] Optimal Execution**

Margin Optimization decides both **whether ordering constraints exist** and, if they do, what those constraints are. Optimal Execution must obey that decision.

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
    Q["[5,0,2,7,2] Execution Ordering Plan"]

    OE["[5,0,3,0,1] Optimal Execution"]
    G["[5,0,3,1,1] Ordering Constraint Enforcer"]
    W["[5,0,3,7,1] Eligible Execution Work Set"]
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

Its job is to determine whether execution ordering matters and to impose ordering only when needed to preserve hedge dependencies or account-resource feasibility.

It does not choose order price, order type, or order timing.

## [5,0,2,1,2] Hedge / Offset Relationship Analyzer

This node infers structural protection relationships from instrument economics, current positions, pending orders, and desired position changes.

It does not use strategy labels such as butterfly, condor, wing, or body.

Coverage may be partial or quantity-dependent.

A protective order counts only when the relevant quantity is actually filled; submission alone does not establish protection.

## [5,0,2,7,1] Execution Dependency Graph

Hedge relationships become quantity-aware precedence constraints only where such constraints genuinely exist.

For risk-adding actions, protection required to avoid an unnecessary naked or high-margin intermediate state must be established before the dependent exposure may execute.

For reductions or exits, the dependency reverses when removing protection first would leave avoidable unhedged exposure.

If the dependency analysis finds that several instruments are independent from a margin/hedge perspective, no artificial ordering is created among them.

## [5,0,2,1,3] Margin Sequence Optimizer

This node converts the dependency graph and live account state into an execution-ordering decision.

Its output has two valid modes:

~~~text
ORDERED
UNCONSTRAINED
~~~

**ORDERED** means one or more precedence constraints genuinely matter.

**UNCONSTRAINED** means Margin Optimization has explicitly determined that no sequencing constraint is needed among the eligible items.

Its objective component remains:

1. preserve required protection;
2. avoid unnecessary high-margin intermediate states;
3. reduce peak cash / collateral / margin required;
4. use only broker-confirmed cash or margin effects from completed execution;
5. avoid inventing sequence constraints when none are necessary.

Structural hedge logic is broker-neutral. Actual rupee margin impact is broker-authoritative and may be queried through the Broker Execution Port.

## [5,0,2,7,2] Execution Ordering Plan

This is the mandatory output of Margin Optimization.

It records the **ordering decision**, not necessarily a sequence.

### ORDERED mode

Conceptually:

~~~text
ordering_mode = ORDERED
ordering_version = ...

steps:
  1. instrument A / side / quantity constraint
  2. instrument B / side / quantity constraint
  3. instrument C / side / quantity constraint
  ...
~~~

Optimal Execution must obey the supplied precedence.

### UNCONSTRAINED mode

Conceptually:

~~~text
ordering_mode = UNCONSTRAINED
ordering_version = ...

eligible_items:
  - instrument A / side / quantity constraint
  - instrument B / side / quantity constraint
  - instrument C / side / quantity constraint
  - instrument D / side / quantity constraint
~~~

This explicitly means there is **no sequencing constraint among those items**.

Optimal Execution may then work them in any order, or concurrently, according to the active execution algorithm and other execution constraints.

For example, four independent long option purchases may legitimately receive an UNCONSTRAINED plan if none depends on another for margin or hedge feasibility.

A valid ordering decision is always required. The decision may be ORDERED or UNCONSTRAINED.

**Missing / invalid ordering decision -> no execution.**

Only Margin Optimization may decide or revise the ordering mode and constraints.

# [5,0,3,0,1] Optimal Execution

Optimal Execution is the second sub-box.

Its first responsibility is to obey the Execution Ordering Plan.

Its second responsibility is to optimize the permitted work through time and the LOB.

When the plan is ORDERED, the ordering constraint is binding.

When the plan is UNCONSTRAINED, Optimal Execution receives no sequencing constraint from Margin Optimization.

## [5,0,3,1,1] Ordering Constraint Enforcer

This is an algorithm-independent gate inside Optimal Execution.

It interprets the ordering mode.

### ORDERED

It:

- identifies the currently permitted sequence step or steps;
- blocks later dependent work from being selected early;
- prevents plug-ins from violating supplied precedence;
- advances only when authoritative broker state satisfies the relevant completion condition.

### UNCONSTRAINED

It:

- imposes no artificial sequence;
- releases all otherwise eligible items;
- allows the active execution algorithm to choose order or concurrency among them.

### Invalid state

It stops execution if the ordering decision is missing, invalid, stale, or cannot be reconciled with authoritative broker state.

A different execution algorithm may change **how** released work is executed, but it cannot override an ORDERED plan or manufacture ordering constraints upstream did not impose.

## [5,0,3,7,1] Eligible Execution Work Set

This is the work released by Ordering Constraint Enforcer to the micro-execution layer.

In ORDERED mode it contains only the currently permitted step or steps.

In UNCONSTRAINED mode it may contain all otherwise eligible items.

Conceptually:

~~~text
ordering_mode
ordering_version
eligible_items:
  - instrument
    side
    remaining quantity
    maximum quantity currently eligible to work
    ordering metadata if applicable
    execution constraints inherited from upstream
~~~

The execution algorithm may act only within this set.

## Time-indexed state

At decision time t:

~~~text
state_t
  = eligible execution work set
  + ordering mode / constraints
  + LOB / quote state
  + own live orders
  + fills / partial fills
  + remaining eligible quantities
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
- validates returned actions against the Eligible Execution Work Set;
- enforces ORDERED precedence when present;
- sends broker-neutral actions to the Broker Execution Port;
- consumes authoritative order/fill feedback;
- updates remaining quantities;
- invokes the algorithm again when required.

The controller is orchestration. Execution policy is plug-and-play.

## [5,0,4,6,1] Execution Algorithm Port

Interchangeable execution algorithms implement this interface:

~~~text
ordering-aware eligible execution state
        |
        v
selected execution algorithm
        |
        v
execution decision(s) at time t
~~~

The current default implementation is [5,0,5,5,1] Passive Chase.

Changing the selected algorithm must not require changes to Margin Optimization, Ordering Constraint Enforcer, Position Management, the Broker Execution Port, or the broker provider.

Every algorithm must obey ORDERED constraints.

In UNCONSTRAINED mode, an algorithm may choose execution order or concurrency among the released items.

## Current default: [5,0,5,5,1] Passive Chase

Passive Chase applies its simple passive-limit policy to the work released by Ordering Constraint Enforcer.

- In ORDERED mode, it works only the currently permitted ordered step or steps.
- In UNCONSTRAINED mode, it may work all released items independently; the default behavior is to place passive limits for each released item at its own same-side best quote.

For each active item:

1. BUY -> place a limit order at the current best bid.
2. SELL -> place a limit order at the current best ask.
3. Do not deliberately cross the spread during the passive phase.
4. Wait parameter T.
5. If quantity remains, refresh the LOB and reprice the remaining quantity to the current passive touch when that touch has changed.
6. Repeat for up to N passive refresh cycles.
7. After the passive phase is exhausted, cancel the working limit, confirm/reconcile that cancellation, and use a market order for the exact confirmed remainder.
8. Partial fills always reduce the quantity worked by subsequent actions.

In UNCONSTRAINED mode, each released item maintains its own Passive Chase state and timer.

T and N remain configuration parameters.

Detailed plug-in specification: [../execution-algorithms/passive-chase.md](../execution-algorithms/passive-chase.md)

## [5,0,4,7,2] Temporal Execution Decision

Current broker-neutral action vocabulary:

~~~text
WAIT
PLACE_LIMIT
REPRICE_LIMIT
CANCEL_LIMIT
PLACE_MARKET
~~~

A decision applies to one or more items within the released work set, subject to the active ordering mode.

The execution algorithm may choose timing, order type, price, and quantity up to the released amount.

It may not:

- violate an ORDERED precedence constraint;
- act outside the Eligible Execution Work Set;
- make an ineligible instrument eligible;
- exceed released quantity;
- reinterpret hedge relationships;
- bypass margin constraints;
- change the economic instrument;
- change strategy intent.

# Ordering invariant

For every Optimal Execution algorithm:

~~~text
Margin Optimization decides WHETHER ORDER MATTERS.

If ORDERED:
    Margin Optimization decides the precedence.
    Optimal Execution decides how to execute the permitted step(s).

If UNCONSTRAINED:
    Margin Optimization explicitly declares no sequencing constraint.
    Optimal Execution may choose order or concurrency among released items.
~~~

Therefore:

~~~text
Execution Ordering Plan
        |
        v
Ordering Constraint Enforcer
        |
        v
Eligible Execution Work Set
        |
        v
Execution Algorithm
~~~

**No valid ordering decision -> no execution.**

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
