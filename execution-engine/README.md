# Execution Engine

This directory is the implementation boundary for the reusable, strategy-agnostic **Execution Engine**.

Status: **shared contracts/ports and the production Command Commit Guard are implemented; the complete execution pipeline is not yet implemented**. The [active execution design](../docs/workflows/execution-engine.md) specifies Margin Optimization -> Execution Slicing -> Optimal Execution -> Execution Recovery / Command Commit Guard -> Broker Execution Port, with cross-cutting State Integrity, Recovery and Interrupt Control. The guard is the first executable production box: it validates injected authorities, writes the mutation intent to the injected Execution Ledger before broker release, rejects duplicate action/correlation identities, and records ambiguous broker outcomes without retrying them. Margin Optimization, Execution Slicing, Optimal Execution, reconciliation, State Integrity, Interrupt Control, a durable production ledger and an environment loader are still to be implemented. The retained strategy-specific butterfly executor in the Dhan service is not the generic engine implementation.

The canonical architecture remains the immutable `[5,0,...]` VID namespace. The canonical Execution Engine implementation language is now **Python 3.12+**, under `volarb_execution/`. Production and testing must use the same engine/component code. Environment behavior changes only by dependency injection; there must be no `if (test_mode)` branch inside the engine.

The JavaScript files under `compat/javascript/execution-contracts/` are transitional wire-contract compatibility for the existing Dhan provider and JavaScript testkit. They are not a second Execution Engine and must not contain execution policy.

Decision ownership is settled for the current design: **the engine and all active execution boxes/sub-boxes are `PURE_ALGORITHMIC`**. Follow the [decision-mode analysis](../docs/architecture/decision-modes.md) and [canonical inventory](../architecture/components/execution-engine/decision-modes.json). Contextual LLM proposals belong to the explicitly hybrid upstream strategy processes; only deterministic admission may release broker mutations.

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

## Python implementation

- `volarb_execution/ports/broker_port.py` — canonical provider-neutral QUERY / COMMAND / STREAM operation vocabulary.
- `volarb_execution/ports/runtime_ports.py` — structural contracts for injected broker, clock, ledger and market dependencies.
- `volarb_execution/contracts/provider_error.py` — canonical global Provider Error Envelope implementation.
- `volarb_execution/recovery/execution_action_envelope.py` — broker-neutral mutating action envelope and broker request identity injection.
- `volarb_execution/recovery/command_commit_guard.py` — production `[5,0,8,1,2]` write-ahead mutation choke point.

Dhan implements the broker port. [execution-testkit/](../execution-testkit/README.md) implements deterministic test doubles for the same boundary. Test doubles approximate broker mechanics; they do not establish exchange fidelity or implement production execution policy.

## Navigation and validation

- [Architecture identities and manifests](../architecture/README.md)
- [Execution design specifications](../docs/workflows/README.md)
- [Dhan provider implementation](../services/dhan-chatgpt-mcp/README.md)
- [Environment contracts](../environments/execution/README.md)
- [Execution Testbed architecture](../docs/testing/execution-testbed.md)

From the repository root, run `python3.12 -B -m unittest discover -s execution-engine/tests -p 'test_*.py' -v`, `node architecture/validate.mjs`, and `node --test architecture/lib/*.test.mjs architecture/*.test.mjs execution-testkit/test/*.test.mjs`. The Command Commit Guard standalone tests execute the canonical Python production class with injected deterministic fakes. These checks are offline; production must never import testkit code.
