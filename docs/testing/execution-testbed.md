# Execution Testbed

Status: **active test architecture**.

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

Mount exactly one box through `ComponentHarness`, supplying only its required ports. Margin Optimization, Execution Slicing, Optimal Execution, Recovery, State Integrity and Interrupt Control can therefore each be tested independently.

### 2. Composition test

Mount a selected subset, for example Optimal Execution -> Command Commit Guard -> Recovery -> Simulated Broker. Unrelated boxes stay absent.

### 3. Full-engine scenario

Run the complete engine against deterministic market/broker/clock/ledger implementations. Declarative scenario fixtures define fills, delays, acknowledgement loss, cancellation races, market changes and faults.

### 4. Mass simulation

Generate seed-addressable scenarios and enforce invariants. A failure carries its seed and generated scenario so it can be reproduced exactly.

### 5. Replay / shadow

Replay historical event streams under a virtual clock or consume live read-only market/account state while all mutations remain blocked/simulated. Production is entered only by mounting the real provider environment.

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

Production/test separation is configuration-level and dependency-level, not an internal execution branch.
