# Execution Engine

This directory is the implementation boundary for the reusable, strategy-agnostic **Execution Engine**.

Status: **shared contracts and structural ports implemented; complete execution pipeline not yet implemented**. The [active execution design](../docs/workflows/execution-engine.md) specifies Margin Optimization -> Execution Slicing -> Optimal Execution -> Execution Recovery / Command Commit Guard -> Broker Execution Port, with cross-cutting State Integrity, Recovery and Interrupt Control. Those policy boxes, a durable production ledger and an environment loader are not shipped here yet. The retained strategy-specific butterfly executor in the Dhan service is not the generic engine implementation.

The canonical architecture remains the immutable `[5,0,...]` VID namespace. Production and testing must use the same engine/component code. Environment behavior changes only by dependency injection; there must be no `if (test_mode)` branch inside the engine.

```text
Strategy
   |
optional Strategy Execution Adapter
   |
Execution Engine
   |
Broker Execution Port
   |
Dhan / another broker provider
```

A Strategy Execution Adapter may understand strategy semantics such as butterfly legs or recentering. The Execution Engine must not.

## Ports

- `ports/broker-port.mjs` — canonical provider-neutral QUERY / COMMAND / STREAM operation vocabulary.
- `ports/runtime-ports.mjs` — structural contracts for injected broker, clock, ledger and market dependencies.
- `contracts/provider-error.mjs` — canonical global Provider Error Envelope implementation, shared by real providers and test doubles.

Dhan implements the broker port. [execution-testkit/](../execution-testkit/README.md) implements deterministic test doubles for the same boundary. Test doubles approximate broker mechanics; they do not establish exchange fidelity or implement production execution policy.

## Navigation and validation

- [Architecture identities and manifests](../architecture/README.md)
- [Execution design specifications](../docs/workflows/README.md)
- [Dhan provider implementation](../services/dhan-chatgpt-mcp/README.md)
- [Environment contracts](../environments/execution/README.md)
- [Execution Testbed architecture](../docs/testing/execution-testbed.md)

From the repository root, run `node architecture/validate.mjs` and `node --test architecture/lib/*.test.mjs architecture/*.test.mjs execution-testkit/test/*.test.mjs`. These checks are offline; production must never import `execution-testkit`.
