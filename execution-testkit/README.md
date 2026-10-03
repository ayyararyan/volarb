# Execution Testkit

Deterministic laboratory for the strategy-agnostic Execution Engine.

The testkit is **not** a second engine. It supplies alternate implementations of external ports so the same production component code can be tested at five levels:

1. **Box test** — mount one component with only its required dependencies.
2. **Composition test** — mount a selected subset of execution boxes.
3. **Full-engine scenario** — mount the complete Execution Engine against simulated broker/market/clock/ledger.
4. **Mass simulation** — generate thousands or millions of seed-addressable scenarios and check invariants.
5. **Replay / shadow** — replay recorded markets or observe live read-only state while broker mutations remain simulated/disabled.

## Core primitives

- `VirtualClock` — deterministic timers with no wall-clock waiting.
- `SeededRng` — reproducible randomness.
- `EventTrace` — ordered causal trace.
- `MemoryExecutionLedger` — test persistence surface.
- `SimulatedMarket` — deterministic snapshots/stream.
- `SimulatedBroker` — the same Broker Port contract as Dhan, including fills, races and ambiguous acknowledgements.
- `FaultInjector` — operation/phase-specific failures.
- `ComponentHarness` — mount one box independently.
- `runScenario` / `runMassScenarios` — deterministic composition/full-engine campaigns.
- invariant checks for overfill, ledger-before-mutation, stale intents and blind retry after ambiguity.

Scenario failures retain their reproduction seed so generated failures can be replayed exactly.

Production is guarded separately by `environments/execution/production.json`, which explicitly forbids the execution testkit.
