# Broker provider documentation

| Document | Authority |
|---|---|
| [Dhan Provider](dhan-execution.md) | Canonical mechanical provider ownership and implementation boundaries |
| [Dhan ↔ Execution Engine call map](dhan-execution-engine-call-map.md) | Broker-neutral operations, readiness, request/stream contracts |
| [Provider Error Envelope](provider-error-contract.md) | Broker-neutral failure categories and mutation-outcome certainty |
| [Dhan service guide](../../services/dhan-chatgpt-mcp/README.md) | Source entrypoints, setup, research/authentication and verification |
| [Legacy butterfly executor](dhan-legacy-butterfly-executor.md) | Compatibility-active strategy-specific MCP API; not the generic engine |

[`dhan-internal-execution-call-map.md`](dhan-internal-execution-call-map.md) is a
legacy-path redirect only. Canonical execution identity is `component.execution_engine`
with unchanged `[5,0,...]` VIDs. Dhan is `provider.dhan`, an unnumbered external
provider. Archived host observations live in the
[deployment archive](../../archive/deployment/dhan-office-mac/README.md).
