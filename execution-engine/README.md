# Execution Engine

This directory is the implementation boundary for the reusable, strategy-agnostic **Execution Engine**.

Status: **shared contracts, the Command Commit Guard, local durable ledger admission and conservative account-scoped reconciliation are implemented; the complete execution pipeline is not yet implemented**. The guard now requires an atomic admission ledger and a trusted broker-account binding. SQLite transactions and OS account locks preserve action/correlation uniqueness and unresolved-command blocks across processes and restart. Read-only reconciliation uses normalized broker orders, trades and positions. See the [durable recovery implementation and limits](../docs/architecture/durable-execution-recovery.md), including the current limitation on live order modifications. Margin Optimization, Execution Slicing, Optimal Execution, full State Integrity, Interrupt Control, the Python/live-provider bridge and an environment loader remain outstanding.

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
- `volarb_execution/recovery/command_commit_guard.py` — production `[5,0,8,1,2]` fenced write-ahead mutation admission.
- `volarb_execution/recovery/sqlite_ledger.py` — `[5,0,8,9,1]` local durable ledger, atomic identity admission and durable intent authority.
- `volarb_execution/recovery/scoped_reconciliation.py` — `[5,0,8,1,1]` read-only broker-evidence reconciliation and persistent account release.
- `volarb_execution/recovery/execution_scope.py` — trusted provider/account binding shared across strategy mounts.

Dhan implements the broker port. [execution-testkit/](../execution-testkit/README.md) implements deterministic test doubles for the same boundary. Test doubles approximate broker mechanics; they do not establish exchange fidelity or implement production execution policy.

## Navigation and validation

- [Architecture identities and manifests](../architecture/README.md)
- [Execution design specifications](../docs/workflows/README.md)
- [Dhan provider implementation](../services/dhan-chatgpt-mcp/README.md)
- [Environment contracts](../environments/execution/README.md)
- [Execution Testbed architecture](../docs/testing/execution-testbed.md)

From the repository root, run `python3.12 -B -m unittest discover -s execution-engine/tests -p 'test_*.py' -v`, `node architecture/validate.mjs`, and `node --test architecture/lib/*.test.mjs architecture/*.test.mjs execution-testkit/test/*.test.mjs`. The Command Commit Guard standalone tests execute the canonical Python production class with real temporary ledger files and synthetic broker observations, including separate-process admission and crash recovery. These checks are offline; production must never import testkit code.
