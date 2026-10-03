# [5,0,0,0,0] Execution Engine

Status: **active reusable execution design**. The complete pipeline is not yet implemented; see [current contracts/ports](../../execution-engine/README.md). These rules specify required behavior, not a live trading service.

Execution Engine is the reusable, strategy-agnostic convergence component that turns broker-neutral economic execution requirements into authoritative broker positions. Strategy-specific interpretation, when needed, sits upstream in a Strategy Execution Adapter.

## Canonical structure

Normal execution has three ordered sub-boxes:

1. **[5,0,2,0,1] Margin Optimization**
2. **[5,0,7,0,1] Execution Slicing**
3. **[5,0,3,0,1] Optimal Execution**

Three cross-cutting supervisory sub-boxes protect the normal path:

- **[5,0,9,0,1] State Integrity**
- **[5,0,8,0,1] Execution Recovery**
- **[5,0,6,0,1] Interrupt Control**

Conceptually:

~~~text
Registry
   |
   v
Margin Optimization
   |
Execution Ordering Plan
   |
   v
Execution Slicing
   |
Execution Slice Plan
   |
   v
Optimal Execution
   |
Temporal Execution Decision
   |
   v
Command Commit Guard + Execution Ledger
   |
   v
Broker Execution Port
   |
   v
external broker provider
~~~

State Integrity and Execution Recovery gate this flow. Interrupt Control can preempt it.

## Architecture

~~~mermaid
flowchart TD
    R["[5,0,1,9,1] Active Instrument Execution Registry"]
    RI["[5,0,1,7,3] Runtime Intent Identity"]
    M["[5,0,1,7,1] Live Market Execution State"]
    A["[5,0,1,7,2] Live Broker Account State"]

    SI["[5,0,9,0,1] State Integrity"]
    SIG["[5,0,9,1,1] State Integrity Guard"]
    SIA["[5,0,9,7,1] Integrity Assessment"]

    MO["[5,0,2,0,1] Margin Optimization"]
    H["[5,0,2,1,2] Hedge / Offset Relationship Analyzer"]
    D["[5,0,2,7,1] Execution Dependency Graph"]
    S["[5,0,2,1,3] Margin Sequence Optimizer"]
    Q["[5,0,2,7,2] Execution Ordering Plan"]

    SL["[5,0,7,0,1] Execution Slicing"]
    SP["[5,0,7,1,1] Slice Planner"]
    SLP["[5,0,7,7,1] Execution Slice Plan"]
    SPS["[5,0,7,2,1] Slice Progress State"]

    OE["[5,0,3,0,1] Optimal Execution"]
    G["[5,0,3,1,1] Ordering Constraint Enforcer"]
    W["[5,0,3,7,1] Eligible Execution Work Set"]
    C["[5,0,4,1,1] Temporal Execution Controller"]
    P["[5,0,4,6,1] Execution Algorithm Port"]
    X["[5,0,5,5,1] Passive Chase"]
    O["[5,0,4,7,2] Temporal Execution Decision"]

    ER["[5,0,8,0,1] Execution Recovery"]
    CG["[5,0,8,1,2] Command Commit Guard"]
    L["[5,0,8,9,1] Execution Ledger"]
    RE["[5,0,8,1,1] Reconciliation Engine"]
    RS["[5,0,8,2,1] Recovery State"]

    IC["[5,0,6,0,1] Interrupt Control"]
    ID["[5,0,6,7,1] Interrupt Directive"]
    IA["[5,0,6,1,1] Interrupt Arbiter"]
    IP["[5,0,6,7,2] Interrupt Action Plan"]

    B["[5,0,3,6,1] Broker Execution Port"]
    F["[5,0,4,7,1] Normalized Broker Execution Facts"]
    E["External broker provider"]

    RI --> R
    R --> MO
    M --> SIG
    A --> SIG
    F --> SIG
    RS --> SIG
    SIG --> SIA
    SIA -. permission .-> MO
    SIA -. permission .-> OE
    SIA -. permission .-> CG

    M --> MO
    A --> MO
    MO --> H --> D --> S --> Q
    Q --> SL --> SP --> SLP
    F --> SPS
    SPS --> SP

    SLP --> G --> W --> C --> P --> X --> O
    M --> OE

    O --> CG
    ID --> IA --> IP --> CG

    R -. current version .-> CG
    CG --> L
    CG --> B

    B --> E
    E --> B
    B --> F

    F --> RE
    L --> RE
    RE --> L
    RE --> RS

    F --> R
    F --> M
    F --> A

    IA -. preempt .-> MO
    IA -. preempt .-> SL
    IA -. preempt .-> OE
~~~

Concrete broker providers are external plug-ins and do not receive Volarb VIDs.

# Runtime execution identity

## [5,0,1,7,3] Runtime Intent Identity

Architectural VIDs identify components. Live execution requirements use separate runtime identity.

Each registry requirement carries at least:

~~~text
intent_id
intent_version
supersedes_version
created_at
status
~~~

A new intent version supersedes stale downstream decisions generated under an older version.

## [5,0,1,9,1] Active Instrument Execution Registry

The registry contains outstanding economic position requirements, not broker order tickets.

It is version-aware and tracks what remains required after authoritative fills and supersession.

# [5,0,9,0,1] State Integrity

State Integrity determines whether current broker-neutral state is trustworthy enough for the requested action.

Normal risk-adding execution requires sufficiently fresh and consistent market/account/order state.

Emergency actions have separate minimum-integrity requirements. For example, cancellation does not require a fresh LOB, while emergency flattening requires sufficiently authoritative position/order state and broker connectivity.

Possible assessments include:

~~~text
VALID
STALE
INCOMPLETE
INCONSISTENT
UNKNOWN
~~~

Unknown broker truth must not create new exposure.

Detailed workflow: [state-integrity.md](state-integrity.md)

# [5,0,2,0,1] Margin Optimization

Margin Optimization decides:

1. what instrument quantities are currently feasible;
2. whether ordering constraints exist;
3. if ordering matters, what the precedence is.

Its output is [5,0,2,7,2] Execution Ordering Plan.

Valid modes:

~~~text
ORDERED
UNCONSTRAINED
~~~

ORDERED carries binding precedence.

UNCONSTRAINED explicitly means no ordering constraint exists among the eligible items.

Margin Optimization does not choose order price, order type, micro-execution timing, or slice count.

# [5,0,7,0,1] Execution Slicing

Execution Slicing decides how many execution chunks are used for each permitted instrument quantity.

This is the "leg layer" in execution terms. To avoid confusion with option-strategy legs, the canonical name is **execution slice**.

## Current default

~~~text
slice_count = 1
scheduling_mode = SEQUENTIAL
~~~

This is the specified baseline for small size; no runtime slicer implementation is shipped yet.

If future scale requires five slices:

~~~text
permitted quantity
   |
   +-> slice 1 -> Optimal Execution -> reconcile
   +-> slice 2 -> Optimal Execution -> reconcile
   +-> slice 3 -> Optimal Execution -> reconcile
   +-> slice 4 -> Optimal Execution -> reconcile
   +-> slice 5 -> Optimal Execution -> reconcile
~~~

Under the default sequential policy, the next slice is released only after the previous slice is authoritatively resolved.

Future slice planners may dynamically choose count, sizes, or scheduling without changing Optimal Execution.

Detailed workflow: [execution-slicing.md](execution-slicing.md)

# [5,0,3,0,1] Optimal Execution

Optimal Execution operates on the currently released execution slice(s).

It does not decide total position size or slice count.

It receives:

- runtime intent/version;
- inherited ORDERED or UNCONSTRAINED constraints;
- slice identity and quantity;
- live market state;
- own working-order/fill state.

## [5,0,3,1,1] Ordering Constraint Enforcer

The enforcer applies the ordering metadata carried through the Execution Slice Plan.

In ORDERED mode it prevents a later dependent item from being worked early.

In UNCONSTRAINED mode it imposes no artificial ordering among otherwise released work.

## [5,0,3,7,1] Eligible Execution Work Set

This is the exact slice-level work the selected algorithm may touch.

Conceptually:

~~~text
intent_id
intent_version
ordering_mode
slice_id
slice_index
instrument
side
remaining_slice_quantity
maximum_quantity_currently_allowed
execution_constraints
~~~

## [5,0,4,6,1] Execution Algorithm Port

The algorithm is plug-and-play.

The current default is [5,0,5,5,1] Passive Chase.

A replacement may change how the active slice is executed through time and the LOB, but it may not:

- change the instrument or side;
- exceed slice quantity;
- violate upstream ordering;
- bypass interrupts;
- bypass State Integrity;
- bypass runtime-version validation.

# [5,0,5,5,1] Passive Chase

For each active slice:

1. BUY -> passive limit at best bid.
2. SELL -> passive limit at best ask.
3. wait T;
4. reprice remaining quantity to the current passive touch when required;
5. repeat for up to N passive waiting/evaluation intervals (at most N − 1 refresh opportunities before fallback);
6. cancel/reconcile the resting limit;
7. market the exact confirmed remainder.

T and N remain configuration parameters.

Detailed plug-in specification: [../execution-algorithms/passive-chase.md](../execution-algorithms/passive-chase.md)

# [5,0,8,0,1] Execution Recovery

Every broker mutation, whether produced by normal Optimal Execution or Interrupt Control, passes through Execution Recovery before the Broker Execution Port.

## [5,0,8,1,2] Command Commit Guard

The guard:

1. verifies the action still belongs to the current runtime intent/version when applicable;
2. rejects stale/superseded actions;
3. checks interrupt compatibility;
4. checks State Integrity permission for the action class;
5. assigns/validates durable action and correlation identity;
6. writes the intended mutation to the Execution Ledger;
7. only then releases it to the broker.

## [5,0,8,9,1] Execution Ledger

Durably links:

~~~text
intent/version
-> slice
-> action
-> broker correlation/order
-> trades/fills
-> position effect
~~~

## [5,0,8,1,1] Reconciliation Engine

After timeout, disconnect, ambiguity or restart, Execution Engine reconciles authoritative broker truth before issuing another mutation in the affected scope.

There is no blind retry of an unknown mutation.

Detailed workflow: [execution-recovery.md](execution-recovery.md)

# [5,0,6,0,1] Interrupt Control

Interrupt Control preempts the normal path.

Current levels:

| Level | Action |
|---|---|
| L1 | CANCEL_WORK |
| L2 | FLATTEN_SCOPE |
| L3 | FLATTEN_ALL |

Interrupt actions bypass Margin Optimization, Execution Slicing, and the plug-in Optimal Execution algorithm as required.

They do **not** bypass Execution Recovery, Command Commit Guard, Broker Execution Port, or authoritative reconciliation.

Detailed workflow: [interrupt-control.md](interrupt-control.md)

# Broker boundary

## [5,0,3,6,1] Broker Execution Port

The Broker Execution Port is the only core interface for provider-specific order/account operations.

Provider implementations handle broker mechanics such as:

- authentication;
- broker instrument identifiers;
- place / modify / cancel / query;
- broker-specific rate/security/connectivity requirements;
- authoritative orders, trades, positions, funds and margin queries.

## [5,0,4,7,1] Normalized Broker Execution Facts

Broker facts are normalized before returning to Execution Engine.

They feed:

- registry convergence;
- slice progress;
- State Integrity;
- Execution Recovery;
- Interrupt Control.

# Completion invariant

Execution Engine optimizes toward authoritative position-state convergence, not API acknowledgement.

A registry requirement completes only when broker truth demonstrates that the required economic effect has been realized or the requirement has been superseded/cancelled by an authorized upstream state transition.


# Environment separation

The Execution Engine must have **one shared implementation** with no production/test switch. The current repository implements shared contracts and ports, not the complete pipeline.

Its external dependencies are injected through ports:

- strategy execution requirement ingress;
- broker port;
- market state/feed;
- clock/timer source;
- execution ledger/persistence;
- randomness only where an algorithm explicitly requires it.

The [environment manifests](../../environments/execution/README.md) specify how production will mount real implementations and test/replay/shadow will inject controlled substitutes. They are declarative contracts, not implemented environment loaders.

The architecture permits the same implemented component to be exercised by the existing box/composition/scenario harnesses. Complete-engine, replay and shadow validation require the corresponding runtime components/runners; current tests do not certify an implemented production engine.

See [Execution Testbed](../testing/execution-testbed.md).
