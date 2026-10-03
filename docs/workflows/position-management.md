# [4,0,0,0,0] Position Management

This graph is shared across all selected underlyings for the trading day.

Trade Selection decides **what should be traded**. Position Management owns the strategy/risk intelligence about **what economic instrument actions are required** to establish, monitor, modify, hedge, recenter, reduce, or close positions.

Position Management does **not** own the reusable broker-neutral optimal-execution algorithm. That responsibility now belongs to Internal Execution.

## Graph

```mermaid
flowchart TD
    A["[4,0,1,7,1] TradeIntent input"]
    B["[4,0,2,1,1] Volarb Execution + Risk Management Engine"]
    C["[4,0,3,1,1] Build intended execution plan"]
    D["[4,0,4,1,1] Pre-trade Margin Feasibility Check"]
    E["[4,0,5,6,1] BrokerMarginFeasibilityPort"]
    P["External broker provider plug-in\nDhan / Kotak / ICICI / ...\n(no Volarb VID)"]
    I["[4,0,5,7,1] Atomic broker-neutral instrument execution intent"]
    J["[4,0,6,6,1] OptimalExecutionPort"]
    B5["[5,0,0,0,0] Broker-Neutral Optimal Execution Layer"]
    K["[4,0,3,1,2] Live strategy / risk / monitoring policy"]
    L["[4,0,4,1,2] Hold / adjust / recenter / hedge / reduce / exit"]

    A -->|"[4,0,1,4,1]"| B
    B -->|"[4,0,2,4,1]"| C
    C -->|"[4,0,3,4,1]"| D
    D -->|"[4,0,4,4,1]"| E
    E -. "provider implementation" .-> P
    P -. "authoritative margin/account facts" .-> E
    E -->|"[4,0,5,4,3] NORMALIZED MarginFeasibility"| D
    D -->|"[4,0,4,4,2] INFEASIBLE"| B
    D -->|"[4,0,4,4,3] FEASIBLE"| I
    I -->|"[4,0,5,4,2]"| J
    J -->|"[0,0,5,4,1] EXECUTION INTENTS"| B5
    B5 -->|"[0,0,4,4,1] EXECUTION FACTS"| B
    B -->|"[4,0,2,4,2]"| K
    K -->|"[4,0,3,4,2]"| L
    L -->|"[4,0,4,4,4]"| B
```

External provider plug-ins are deliberately shown without VIDs. The Volarb-owned interfaces have VIDs; concrete broker implementations do not.

## Architectural split

### [4,0,2,1,1] Volarb Execution + Risk Management Engine

This is the strategy/risk intelligence layer.

It decides the desired economic actions: which exact instruments should be bought or sold, in what target quantity, because of entry, hold, adjustment, recentering, hedging, risk reduction, or exit decisions.

It does not need to decide the broker-specific mechanics of achieving those executions optimally.

### [4,0,5,7,1] Atomic broker-neutral instrument execution intent

The atomic unit leaving Position Management is one desired instrument action.

A butterfly can therefore generate four separate instances of this contract at the same time. The contract does not need to identify them as butterfly legs.

Conceptually:

```text
side
economic instrument identity
quantity
[future execution constraints still TBD]
```

The economic identity is broker-neutral. Dhan Security IDs, Kotak identifiers, exchange-specific payload fields, and similar provider vocabulary do not cross this boundary.

### [4,0,6,6,1] OptimalExecutionPort

This is the handoff from Position Management into Internal Execution.

Position Management can hand Internal Execution one or more atomic instrument execution intentions. Internal Execution registers them, applies Margin Optimization, then passes eligible work to Optimal Execution.

The previous interpretation of this interface as a thin broker executor is superseded.

## Broker margin dependency

Broker-independence does not mean broker-blindness.

Before execution, Volarb queries `[4,0,5,6,1] BrokerMarginFeasibilityPort`.

The port is implemented through the active external broker provider and returns normalized authoritative margin/account facts. The concrete provider implementation is outside the Volarb VID namespace.

Conceptual normalized result:

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

If infeasible, control returns to `[4,0,2,1,1]`. Neither Internal Execution nor the broker plug-in invents an alternative strategy.

## Responsibility boundary

**Position Management:** what economic action is required.

**Internal Execution:** how the current set of desired instrument executions should be executed optimally.

**Broker plug-in:** broker-specific translation, transport, and authoritative facts.

Replacing Dhan should not require rebuilding Internal Execution.

## Still TBD

- exact atomic execution-intent schema;
- quantity representation;
- execution constraints Position Management may attach;
- internal optimal-execution objective and algorithm;
- sequencing across several simultaneous registry entries;
- fill/partial-fill response policy;
- pricing and repricing logic;
- modification versus cancel/replace logic;
- interaction between execution progress and Position Management risk decisions;
- behavior after margin infeasibility;
- portfolio coordination across multiple live positions.


## Execution interrupts

Position Management may raise an emergency interrupt into Internal Execution when strategy/risk logic determines that normal execution should be preempted.

The current interrupt levels are:

- **L1 CANCEL_WORK** — cancel unfinished orders in the specified scope and suppress further normal execution there.
- **L2 FLATTEN_SCOPE** — immediately flatten a specified affected economic scope using emergency market actions.
- **L3 FLATTEN_ALL** — highest-priority emergency request to flatten all controlled positions immediately.

Position Management supplies the economic scope and intent. Internal Execution's Interrupt Control owns preemption, cancellation/reconciliation, and broker-neutral emergency order transport.

Interrupt Control does not rely on Passive Chase or any other plug-in execution algorithm for emergency flattening.
