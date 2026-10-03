# Execution Engine

This directory is the implementation boundary for the reusable, strategy-agnostic **Execution Engine**.

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

Dhan implements the broker port. `execution-testkit/` implements deterministic test doubles for the same boundary.
