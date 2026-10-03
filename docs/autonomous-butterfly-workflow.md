# Volarb Strategy Composition — Autonomous Workflow Design

Status: **active architecture design, not an operational autonomous deployment**. The current research workflow remains human-executed under [WORKFLOW.md](WORKFLOW.md), the [butterfly controller](../skill/butterfly-market-outlook/SKILL.md), and the [personal covenant](PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md). No diagram authorizes orders, monitoring, broader structure families or overnight carry.

Volarb owns four strategy modules and mounts the independently reusable Execution Engine. Numeric values remain only inside immutable VIDs. The [composition manifest](../architecture/strategies/volarb/composition.json) owns mounts and bindings; [compositional identity](architecture/compositional-identity.md) owns identity rules.

~~~mermaid
flowchart TD
    S["[0,0,1,1,1] Start / Wake"]
    R["[1,0,0,0,0] Regime Gate"]
    U["[2,0,0,0,0] Underlying Allocation"]
    F["[0,0,2,1,1] Fan out one Trade Selection instance per selected X"]
    T["[3,I,0,0,0] Trade Selection"]
    P["[4,0,0,0,0] Position Management"]
    E["[5,0,0,0,0] Execution Engine"]

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

## [5,0,0,0,0] Execution Engine

Converges registry requirements into authoritative broker positions.

Execution Engine has three ordered normal-flow sub-boxes:

1. **[5,0,2,0,1] Margin Optimization**
2. **[5,0,7,0,1] Execution Slicing**
3. **[5,0,3,0,1] Optimal Execution**

It also contains cross-cutting **State Integrity**, **Execution Recovery**, and **Interrupt Control**. Interrupt Control can preempt the normal flow; all broker mutations still pass through durable recovery/commit safeguards.

Margin Optimization produces the mandatory Execution Ordering Plan, which is either ORDERED or UNCONSTRAINED. Optimal Execution must obey ORDERED precedence; when UNCONSTRAINED, it may choose order or concurrency among released work.

Detailed workflow: [workflows/execution-engine.md](workflows/execution-engine.md)

## Global rules

- Semantic names, not numeric "Box" labels, are used in prose.
- VIDs remain immutable and retain their numeric first coordinate.
- Broker providers such as Dhan are external plug-ins, not core modules.
- Interrupt Control has priority over normal Execution Engine and may bypass the plug-in execution algorithm for emergency cancellation/flattening.
- Strategy/risk logic remains in Position Management.
- Margin Optimization precedes micro-execution and supplies the mandatory ordering decision: ORDERED or UNCONSTRAINED.
- Execution Slicing defaults to one sequential slice; future large positions may be split into multiple slices without changing Optimal Execution.
- Runtime intents are versioned; stale superseded actions cannot reach the broker.
- Unknown or ambiguous broker truth blocks normal new mutations until reconciliation.
- Optimal Execution cannot exceed quantity released by Margin Optimization.
- Missing or invalid ordering decision means no Optimal Execution; an explicit UNCONSTRAINED decision is valid.
- Concrete execution algorithms are plug-and-play behind the Execution Algorithm Port.
- Broker execution must not independently alter strategy intent.
- New strategy-local or Execution Engine entities receive immutable VIDs in the owning namespace. Providers have component identities without Volarb VIDs; mounts/bindings have composition identities.
- Strategy-specific translation, if required, sits in an optional Strategy Execution Adapter upstream of the generic engine.
- The [implemented execution contracts/ports](../execution-engine/README.md) and [testkit](../execution-testkit/README.md) do not constitute an implemented full execution pipeline.
