# Workflow design and ownership

These are **active architecture specifications**, not evidence that an autonomous strategy or the complete Execution Engine is deployed.

For today's human-executed research workflow, start with [WORKFLOW.md](../WORKFLOW.md), the [butterfly controller](../../skill/butterfly-market-outlook/SKILL.md), and the [personal covenant](../PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md). Design schedulers, broader structure families and interrupt commands do not authorize monitoring or orders, and do not replace the intraday-only / flat-by-15:00-IST covenant.

| Ownership | Documents |
|---|---|
| Volarb strategy design | [Composition overview](../autonomous-butterfly-workflow.md), [Regime Gate](regime-gate.md), [Underlying Allocation](underlying-allocation.md), [Trade Selection](trade-selection.md), [Position Management](position-management.md) |
| Reusable execution design | [Execution Engine](execution-engine.md), [Slicing](execution-slicing.md), [Recovery / Command Commit Guard](execution-recovery.md), [State Integrity](state-integrity.md), [Interrupt Control](interrupt-control.md), [Passive Chase](../execution-algorithms/passive-chase.md) |
| Identity | [Current identity guide](vector-id-system.md), [compositional identity](../architecture/compositional-identity.md), [assembled compatibility registry](vector-id-registry.json) |
| Implementation and tests | [Engine contracts/ports](../../execution-engine/README.md), [Execution Testkit](../../execution-testkit/README.md), [environment definitions](../../environments/execution/README.md) |

The generic engine must not interpret butterfly/condor/recenter semantics. An optional Strategy Execution Adapter translates those semantics when the strategy cannot already emit broker-neutral intent. Dhan remains a mechanical provider below the Broker Execution Port.

[internal-execution.md](internal-execution.md) is an explicit legacy redirect, not a second design.
