# Execution Testbed

Status: **active test architecture**.

Implemented today: deterministic dependencies, `ComponentHarness`, `CompositionHarness`, scenario/mass drivers and trace invariants. The complete Execution Engine policy pipeline, recorded-input runner and live shadow runner are **not yet implemented**. The diagram and five levels below describe the required architecture, not completed end-to-end production validation. See [implementation scope and test commands](../../execution-testkit/README.md).

The Execution Testbed is external infrastructure around `component.execution_engine`. It is not a second implementation of the engine and has no Execution Engine VID.

## Fundamental rule

```text
                         SAME EXECUTION ENGINE

TEST / REPLAY / SHADOW                         PRODUCTION
Scenario or strategy input                     Strategy input
          |                                         |
          v                                         v
     Execution Engine                          Execution Engine
          |                                         |
          v                                         v
  Simulated Broker / Market                         Dhan
  Virtual Clock / Test Ledger                    Real clock/ledger
```

The engine never checks a `test_mode` flag. Environment differences are dependency injection only.

## Five test levels

### 1. Box test

Mount one implemented box through `ComponentHarness`, consuming only its required ports from the supplied dependencies. Margin Optimization, Execution Slicing, Optimal Execution, Recovery, State Integrity and Interrupt Control are designed to be tested this way once implemented; current tests mount fixture components.

### 2. Composition test

Mount a selected subset, for example Optimal Execution -> Command Commit Guard -> Recovery -> Simulated Broker. Unrelated boxes stay absent.

### 3. Full-engine scenario

The target is to run the complete engine against deterministic market/broker/clock/ledger implementations. The existing `runScenario` accepts a caller-supplied driver; declarative fixtures configure fills, delays, acknowledgement loss, cancellation races, market changes and faults. Current fixtures test the simulator boundary, not a complete engine.

### 4. Mass simulation

Generate seed-addressable scenarios and enforce invariants. A failure carries its seed and generated scenario so it can be reproduced exactly.

### 5. Replay / shadow

The planned runners will replay recorded event streams under a virtual clock or consume live read-only market/account state while mutations remain blocked/simulated. Only the environment contracts exist today. A real provider mount would still require separately configured authorization/readiness; selecting or reading a manifest alone does not enable production.

## Current invariant library

- **NO_OVERFILL** — total fills cannot exceed requested quantity.
- **LEDGER_BEFORE_MUTATION** — an action must exist in the ledger before broker application.
- **NO_BLIND_RETRY_AFTER_AMBIGUITY** — ambiguous placement cannot be placed again before reconciliation.
- **NO_STALE_INTENT_MUTATION** — broker mutations cannot use a superseded intent version.

More component-specific invariants should be added as the Execution Engine implementation is built.

## Environment manifests

| Environment | Market | Broker mutations | Clock | Testkit allowed |
|---|---|---|---|---|
| test | simulated | simulated only | virtual | yes |
| replay | historical | simulated only | virtual | yes |
| shadow | live read-only | none | real | yes |
| production | live | real mounted provider | real | **no** |

Production/test separation is configuration-level and dependency-level, not an internal execution branch. The [environment guide](../../environments/execution/README.md) explains the declarative contract and current implementation limits.
