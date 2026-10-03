# [4,0,0,0,0] Box 4 — Shared Execution & Risk Management Graph

This graph is shared across all selected underlyings for the trading day.

Box 3 decides **what should be traded**. Box 4 owns the intelligent decisions about **how to establish, monitor, manage, modify, and close positions**.

## Graph

```mermaid
flowchart TD
    A["[4,0,1,7,1] TradeIntent input"]
    B["[4,0,2,1,1] Volarb Execution + Risk Management Engine"]
    C["[4,0,3,1,1] Build intended execution plan"]
    D["[4,0,4,1,1] Pre-trade Margin Feasibility Check"]
    E["[4,0,5,6,1] BrokerMarginFeasibilityPort"]
    F["[4,0,6,8,1] Active Broker Provider Plug-in"]
    G["[4,0,7,8,1] Dhan API / Broker"]
    H["[4,0,7,8,2] Kotak / ICICI / other broker"]
    I["[4,0,5,7,1] Canonical broker-neutral execution command"]
    J["[4,0,6,6,1] ExecutionPort / thin Broker Executor"]
    K["[4,0,3,1,2] Live execution / risk / monitoring policy"]
    L["[4,0,4,1,2] Hold / adjust / recenter / hedge / reduce / exit"]

    A -->|"[4,0,1,4,1]"| B
    B -->|"[4,0,2,4,1]"| C
    C -->|"[4,0,3,4,1]"| D
    D -->|"[4,0,4,4,1]"| E
    E -->|"[4,0,5,4,1]"| F
    F -->|"[4,0,6,4,1] DHAN TODAY"| G
    F -.->|"[4,0,6,4,2] REPLACEABLE"| H
    G -->|"[4,0,7,4,1] MARGIN / ACCOUNT FACTS"| F
    H -->|"[4,0,7,4,2] MARGIN / ACCOUNT FACTS"| F
    F -->|"[4,0,6,4,3] NORMALIZED MarginFeasibility"| D
    D -->|"[4,0,4,4,2] INFEASIBLE"| B
    D -->|"[4,0,4,4,3] FEASIBLE"| I
    I -->|"[4,0,5,4,2]"| J
    J -->|"[4,0,6,4,4]"| F
    G -->|"[4,0,7,4,3] ORDER / FILL / STATUS FACTS"| F
    H -->|"[4,0,7,4,4] ORDER / FILL / STATUS FACTS"| F
    F -->|"[4,0,6,4,5] NORMALIZED EXECUTION FACTS"| B
    B -->|"[4,0,2,4,2]"| K
    K -->|"[4,0,3,4,2]"| L
    L -->|"[4,0,4,4,4]"| B
```

## Architectural split

### [4,0,2,1,1] Volarb Execution + Risk Management Engine

This is the intelligent layer. It will own execution sequencing, responses to fills and partial fills, live position monitoring, risk decisions, adjustment/exit logic, and coordination across positions.

### [4,0,6,8,1] Broker Provider Plug-in

This is intentionally thin. It translates canonical commands, handles authentication, instrument/token mapping, IP whitelisting, order IDs, broker errors, and returns authoritative execution/account facts.

It must not independently choose strikes, alter structures, resize because it prefers another size, recenter, or alter strategy logic.

## Broker margin dependency

Broker-independence does not mean broker-blindness.

Before execution, Volarb queries `[4,0,5,6,1] BrokerMarginFeasibilityPort`.

Provider-specific implementations may include Dhan, Kotak, ICICI Securities, or another broker adapter.

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

If infeasible, control returns to `[4,0,2,1,1]`. The broker does not improvise.

## Provider-independence rule

The broker supplies authoritative facts and execution transport. **Volarb supplies the intelligence.**

## Still TBD

- internal execution-policy graph;
- canonical TradeIntent schema;
- canonical execution command/event schemas;
- behavior after margin infeasibility;
- adapter-local versus escalated failures;
- fill/partial-fill policy;
- position monitoring;
- risk thresholds;
- hold / recenter / hedge / reduce / exit logic;
- coordination across multiple live Box 3 positions.
