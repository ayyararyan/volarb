# Execution Testkit

Deterministic laboratory for the strategy-agnostic Execution Engine.

The testkit is **not** a second engine. Implemented primitives and harnesses accept caller-supplied component factories or scenario drivers. The complete production engine is not yet implemented; bundled tests use small fixture components and exercise broker/testkit mechanics, not a deployed trading pipeline.

The five-level [testing architecture](../docs/testing/execution-testbed.md) is:

1. **Box test** — mount one component with only its required dependencies.
2. **Composition test** — mount a selected subset of execution boxes.
3. **Full-engine scenario** — the scenario harness exists; mounting the complete engine awaits its implementation.
4. **Mass simulation** — generate thousands or millions of seed-addressable scenarios and check invariants.
5. **Replay / shadow** — defined by environment contracts; recorded-input/live-shadow runners are not yet implemented.

## Core primitives

- `VirtualClock` — deterministic timers with no wall-clock waiting.
- `SeededRng` — reproducible randomness.
- `EventTrace` — ordered causal trace.
- `MemoryExecutionLedger` — test persistence surface.
- `SimulatedMarket` — deterministic snapshots/stream.
- `SimulatedBroker` — the same Broker Port contract as Dhan, including fills, races and ambiguous acknowledgements.
- `FaultInjector` — operation/phase-specific failures.
- `ComponentHarness` — mount one box independently.
- `CompositionHarness` — mount selected caller-supplied boxes sharing injected dependencies.
- `runScenario` / `runMassScenarios` — deterministic campaigns driven by caller-supplied code.
- invariant checks for overfill, ledger-before-mutation, stale intents and blind retry after ambiguity.

`runMassScenarios` failures retain their reproduction seed and regenerated fixture. Reproduction assumes the caller's scenario factory and driver are deterministic; the harness cannot make external I/O deterministic.

The [environment contracts](../environments/execution/README.md) forbid testkit dependencies in production. They do not constitute a runtime environment loader. Offline tests check both these declarations and imports from engine/provider production sources.

## Offline tests and fixtures

From the repository root:

```sh
node --test execution-testkit/test/*.test.mjs
```

[Acknowledgement-loss](scenarios/ack-loss-reconcile.json) and [partial-fill/cancel-race](scenarios/partial-fill-cancel-race.json) fixtures are loaded by the regression tests. Their `expected_invariants` list documents the intended checks; `runScenario` applies its supplied invariant functions (all defaults unless overridden), not a fixture-name-based selector.

## Scope and limitations

`MemoryExecutionLedger` is intentionally in-memory, never production durability. The simulated broker uses scripted fills, simplified account/margin responses and a limited modification model; it is not exchange calibration. Invariants operate on trace events and their supplied action/intent identities. A passing primitive or generated smoke campaign is not proof of complete recovery, strategy, or production safety. Add component-specific tests as real execution boxes are implemented.
