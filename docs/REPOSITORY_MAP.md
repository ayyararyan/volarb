# Canonical repository map

Updated 2026-10-04. This map describes source ownership and implementation status, not a running deployment. Start at the [root README](../README.md); [validation commands](VALIDATION.md) cover the source tree.

## Architecture and execution

| Location | Ownership and canonical entrypoint |
|---|---|
| [`architecture/`](../architecture/README.md) | Component and composition catalogs, immutable identities, manifests and validators. [Compositional identity](architecture/compositional-identity.md) is the identity specification. |
| [`architecture/components/execution-engine/`](../architecture/components/execution-engine/manifest.json) | Canonical `component.execution_engine` and `[5,0,...]` registry. Old `internal-execution/` paths are compatibility mirrors/aliases, not another component. |
| [`architecture/strategies/volarb/`](../architecture/strategies/volarb/composition.json) | Volarb mounts and bindings. [Strategy master graph](autonomous-butterfly-workflow.md) links regime/allocation/selection/position-management designs. |
| [`execution-engine/`](../execution-engine/README.md) | Generic runtime ports and global provider errors. The full policy/convergence pipeline is designed in [execution-engine.md](workflows/execution-engine.md), not yet implemented here. |
| [`execution-testkit/`](../execution-testkit/README.md) | Virtual clock, seeded randomness, simulated broker/market, memory ledger, faults, composition harness and invariant tests. Not production code. |
| [`environments/execution/`](../environments/execution/README.md) | Test/replay/shadow/production dependency declarations. Not an environment loader or authorization to send broker commands. |

The boundary is **Strategy → optional Strategy Execution Adapter → Execution Engine → Broker Execution Port → Broker Provider**. Strategy semantics are never moved into the generic engine, and Dhan never chooses execution policy. Production must not depend on `execution-testkit`.

## Providers, services and installation

| Location | Purpose |
|---|---|
| [`services/dhan-chatgpt-mcp/`](../services/dhan-chatgpt-mcp/README.md) | Reusable Dhan Provider/Broker Execution Port implementation, read-only MCP facade and separately gated legacy butterfly executor. [Call map](providers/dhan-execution-engine-call-map.md) distinguishes generic operations from compatibility tools. |
| [`services/day-workflow/`](../services/day-workflow/README.md) | Existing strategy-specific SHADOW orchestration, read-only acquisition and explicit accounting tooling. Not the generic Execution Engine and not an end-to-end live bot. |
| [`services/essvi-dashboard/`](../services/essvi-dashboard/README.md) | Optional eSSVI/IV/HAR dashboard, external data/package requirements and local launch procedure. |
| [`agent-kit/`](AGENT_KIT.md), [`tools/volarb.py`](../tools/volarb.py) | Portable source/profile/workspace packaging and offline diagnostics. Not the research laboratory itself; credentials and private runtime remain separate. |

## Research and strategy operation

| Location | Purpose |
|---|---|
| [`agent/`](../agent/README.md) | Offline Butterfly Research Laboratory, datasets, campaigns, evaluators, scientific contracts and tests. Frozen controller copies/evidence are versioned scientific baselines, not duplicate live controllers. |
| [`skill/`](../skill/README.md) | Current-observation research modules: Butterfly Market Outlook v2.6, HF realized-volatility forecast and news filter. |
| [`docs/DAILY_OPERATING_ALGORITHM.md`](DAILY_OPERATING_ALGORITHM.md) | Current manual daily sequence; [standing workflow](WORKFLOW.md) and [covenant](PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md) supply operating constraints. |
| [`prompts/`](../prompts/README.md) | Bounded user-invoked workflow prompts, not schedules or order authority. |
| [`market-outlook/`](../market-outlook/README.md) | Public navigation notice only. Dated market/position reviews belong in a configured private journal outside source. |
| [`trade-log/`](../trade-log/README.md) | Public navigation notice and private schema reference. Personal executions, account snapshots and calibration episodes are intentionally excluded. |

## Maintenance and history

- [Validation guide](VALIDATION.md), `.github/workflows/` and `tests/` explain practical offline checks.
- [Current notes](../notes.md) route decisions to canonical documents; [tasks](../tasks.md) distinguish outstanding implementation from completed design.
- [Development history](DEVELOPMENT_HISTORY.md) records changes; [file classification](audits/2026-10-03-file-classification.tsv) accounts for every cleanup-baseline tracked file; its historical financial-record dispositions were superseded by the public-release privacy boundary.
- [Archive](../archive/README.md) separates superseded architecture, research reports and retired deployment policy. Archived content is historical evidence, never a runtime dependency or current instruction.
