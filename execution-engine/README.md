# Execution Engine

This directory is the implementation boundary for the reusable, strategy-agnostic **Execution Engine**.

Status: **shared contracts/ports and the production Command Commit Guard are implemented; the complete execution pipeline is not yet implemented**. The [active execution design](../docs/workflows/execution-engine.md) specifies Margin Optimization -> Execution Slicing -> Optimal Execution -> Execution Recovery / Command Commit Guard -> Broker Execution Port, with cross-cutting State Integrity, Recovery and Interrupt Control. The guard is the first executable production box: it validates injected authorities, writes the mutation intent to the injected Execution Ledger before broker release, rejects duplicate action/correlation identities, and records ambiguous broker outcomes without retrying them. Margin Optimization, Execution Slicing, Optimal Execution, reconciliation, State Integrity, Interrupt Control, a durable production ledger and an environment loader are still to be implemented. The retained strategy-specific butterfly executor in the Dhan service is not the generic engine implementation.

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
- `recovery/execution-action-envelope.mjs` — broker-neutral mutating action envelope and broker request identity injection.
- `recovery/command-commit-guard.mjs` — production `[5,0,8,1,2]` write-ahead mutation choke point.

Dhan implements the broker port. [execution-testkit/](../execution-testkit/README.md) implements deterministic test doubles for the same boundary. Test doubles approximate broker mechanics; they do not establish exchange fidelity or implement production execution policy.

## Navigation and validation

- [Architecture identities and manifests](../architecture/README.md)
- [Execution design specifications](../docs/workflows/README.md)
- [Dhan provider implementation](../services/dhan-chatgpt-mcp/README.md)
- [Environment contracts](../environments/execution/README.md)
- [Execution Testbed architecture](../docs/testing/execution-testbed.md)

From the repository root, run `node architecture/validate.mjs` and `node --test architecture/lib/*.test.mjs architecture/*.test.mjs execution-testkit/test/*.test.mjs`. The Command Commit Guard standalone box tests live in `execution-testkit/test/command-commit-guard.test.mjs` so production source never imports testkit code. These checks are offline; production must never import `execution-testkit`.
