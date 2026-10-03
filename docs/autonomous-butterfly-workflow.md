# Volarb Autonomous Workflow

The autonomous architecture is organized into five named modules. Numeric values remain only inside immutable VIDs.

~~~mermaid
flowchart TD
    S["[0,0,1,1,1] Start / Wake"]
    R["[1,0,0,0,0] Regime Gate"]
    U["[2,0,0,0,0] Underlying Allocation"]
    F["[0,0,2,1,1] Fan out one Trade Selection instance per selected X"]
    T["[3,I,0,0,0] Trade Selection"]
    P["[4,0,0,0,0] Position Management"]
    E["[5,0,0,0,0] Internal Execution"]

    S -->|"[0,0,1,4,1]"| R
    R -->|"[0,0,1,4,2] favorable"| U
    U -->|"[0,0,1,4,3] selected set + W_X"| F
    F -->|"[0,0,2,4,1]"| T
    T -->|"[0,0,2,4,2] TradeIntent"| P
    P -->|"[0,0,5,4,1] instrument intents"| E
    E -->|"[0,0,4,4,1] execution facts"| P
~~~

## [1,0,0,0,0] Regime Gate

Determines whether the broader multi-day environment permits new short-gamma deployment.

Detailed workflow: [workflows/regime-gate.md](workflows/regime-gate.md)

## [2,0,0,0,0] Underlying Allocation

Selects the eligible underlying set and reserves capital across NIFTY, BANKNIFTY, and SENSEX when the regime is favorable.

Detailed workflow: [workflows/underlying-allocation.md](workflows/underlying-allocation.md)

## [3,0,0,0,0] Trade Selection

Runs independently per selected underlying and chooses an admissible structure. Runtime instances keep the same local VID coordinates and use the instance coordinate for the underlying.

Detailed workflow: [workflows/trade-selection.md](workflows/trade-selection.md)

## [4,0,0,0,0] Position Management

Owns strategy/risk intelligence for establishing, supervising, adjusting, hedging, recentering, reducing, and closing positions. It emits broker-neutral instrument execution intents.

Detailed workflow: [workflows/position-management.md](workflows/position-management.md)

## [5,0,0,0,0] Internal Execution

Converges registry requirements into authoritative broker positions.

Internal Execution has exactly two ordered sub-boxes:

1. **[5,0,2,0,1] Margin Optimization**
2. **[5,0,3,0,1] Optimal Execution**

Margin Optimization produces the mandatory ordered Execution Sequence Plan. Optimal Execution must follow that sequence and decides only how to work the current released step through time and the LOB.

Detailed workflow: [workflows/internal-execution.md](workflows/internal-execution.md)

## Global rules

- Semantic names, not numeric "Box" labels, are used in prose.
- VIDs remain immutable and retain their numeric first coordinate.
- Broker providers such as Dhan are external plug-ins, not core modules.
- Strategy/risk logic remains in Position Management.
- Margin Optimization precedes micro-execution and supplies the mandatory execution sequence.
- Optimal Execution cannot exceed quantity released by Margin Optimization.
- No valid execution sequence means no Optimal Execution.
- Concrete execution algorithms are plug-and-play behind the Execution Algorithm Port.
- Broker execution must not independently alter strategy intent.
- Every new architectural entity receives an immutable VID.
