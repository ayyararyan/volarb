# [5,0,0,0,0] Box 5 — Broker-Neutral Optimal Execution Layer

## Purpose

Box 5 is Volarb's reusable **optimal execution layer**.

It receives already-decided, broker-neutral instrument execution intentions from Box 4, maintains the current execution registry, and determines how the registered instructions should be executed optimally.

It is **not Dhan-specific**.

A migration from Dhan to Kotak, ICICI Securities, or another broker should replace the provider plug-in rather than require a new optimal-execution engine.

## Core principle

Box 5 does not need to know whether an order belongs to a butterfly, caterpillar, mouse, hedge, recenter, exit, or another strategy.

It sees instrument-level execution work.

For example, Box 4 may concurrently hand down four intents that happen to be the four legs of a butterfly. Box 5 sees four registry entries requiring execution.

```text
BOX 4
strategy/risk meaning
        |
        | one or more atomic instrument execution intents
        v
+--------------------------------------------------+
| [5,0,0,0,0] BROKER-NEUTRAL OPTIMAL EXECUTION   |
|                                                  |
| [5,0,1,9,1] Active Instrument Execution Registry|
|                    |                             |
|                    v                             |
| [5,0,2,1,1] Optimal Execution Engine            |
|                    |                             |
|                    v                             |
| [5,0,3,6,1] Broker Execution Port               |
|                    |                             |
|                    v                             |
| [5,0,4,7,1] Normalized Broker Execution Facts   |
+--------------------------------------------------+
                     |
                     v
       external broker provider plug-in
        Dhan / Kotak / ICICI / ...
              (no Volarb VID)
```

## Minimal graph fixed so far

```mermaid
flowchart TD
    R["[5,0,1,9,1] Active Instrument Execution Registry"]
    O["[5,0,2,1,1] Broker-Neutral Optimal Execution Engine"]
    P["[5,0,3,6,1] Broker Execution Port"]
    X["External broker provider plug-in\nDhan / Kotak / ICICI / ...\n(no Volarb VID)"]
    F["[5,0,4,7,1] Normalized Broker Execution Facts"]

    R -->|"[5,0,1,4,1]"| O
    O -->|"[5,0,2,4,1]"| P
    P -. "broker-specific operation" .-> X
    X -. "authoritative broker response / state" .-> P
    P -->|"[5,0,3,4,1]"| F
    F -->|"[5,0,4,4,1]"| R
```

The external plug-in boundary itself is not a numbered Volarb architectural object.

## [5,0,1,9,1] Active Instrument Execution Registry

At any moment Box 5 maintains the set of instrument executions currently required or in progress.

A strategy may generate one entry or many entries simultaneously.

Example:

```text
registry
  - BUY  instrument A  ...
  - SELL instrument B  ...
  - BUY  instrument C  ...
  - SELL instrument D  ...
```

Box 5 does not need the higher-level statement "A/B/C/D form a butterfly."

The exact registry schema, states, priorities, constraints, timestamps, dependencies and lifecycle fields remain TBD.

## [5,0,2,1,1] Broker-Neutral Optimal Execution Engine

This is the reusable execution algorithm.

Its job is to inspect the current registry and determine how to execute the outstanding instrument intentions optimally.

The word **optimal** is intentional, but its objective function and algorithm are not yet defined.

We have not yet decided:
- how it prioritizes simultaneous entries;
- whether it sequences, parallelizes, or groups orders;
- how it reacts to fills and partial fills;
- how it sets or changes prices;
- how it handles urgency;
- how it handles liquidity and spread;
- how it balances execution quality against exposure while legs are incomplete.

Those decisions will be designed bottom-up.

## [5,0,3,6,1] Broker Execution Port

The optimal execution engine does not call Dhan-specific APIs.

It sends generic broker operations through this port.

Conceptually these may later include operations such as:
- place;
- modify;
- cancel;
- query order;
- query fills;
- query positions;
- query account/broker state.

The exact port contract remains TBD.

## External broker provider plug-ins — no Volarb VID

Concrete broker implementations sit beneath the Broker Execution Port.

Examples:

```text
provider = dhan
provider = kotak
provider = icici
```

They do not receive Box numbers or Volarb VIDs.

Their responsibility is deliberately mechanical:
- resolve broker-specific instrument identifiers;
- translate canonical operations into broker payloads;
- authenticate;
- satisfy broker-specific connectivity/security requirements;
- place/modify/cancel/query through the broker API;
- return authoritative broker facts;
- surface provider-specific failures in normalized form.

They do **not** own the reusable optimal-execution algorithm.

## Dhan implementation

The existing `services/dhan-chatgpt-mcp/` code is the current Dhan substrate.

Reusable provider-specific pieces include:
- Dhan authentication/session handling;
- IP-whitelist/readiness checks;
- Dhan instrument-master and Security-ID mapping;
- Dhan API client;
- order/fill/position/funds queries;
- broker margin calls;
- durable correlation/reconciliation primitives;
- broker-specific error handling that can be normalized.

The existing `ButterflyExecutor` also contains execution-policy and optimization behavior. That logic must be classified before reuse. Broker-neutral optimal-execution behavior belongs in Box 5 rather than the Dhan provider merely because the first implementation happened to be written there.

See: [Dhan execution provider notes](../providers/dhan-execution.md).

## [5,0,4,7,1] Normalized Broker Execution Facts

Broker facts returned through the provider are normalized before they are used by Box 5 or returned upstream to Box 4.

The exact event taxonomy is still TBD, but this boundary will eventually represent authoritative facts such as order acknowledgement, pending state, fills, partial fills, rejection, cancellation, ambiguity, and broker/account state.

## Cross-box behavior

Box 4 can send multiple `[4,0,5,7,1]` atomic instrument execution intents into Box 5.

Cross-box edges:

- `[0,0,5,4,1]` Box 4 instrument execution intents -> Box 5 execution registry.
- `[0,0,4,4,1]` Box 5 normalized execution facts -> Box 4 execution/risk engine.

This is a feedback loop. Strategy/risk decisions remain in Box 4 while execution optimization remains in Box 5.

## Provider-replaceability acceptance test

A broker migration should require:
- a new provider implementation beneath `[5,0,3,6,1]`;
- provider configuration/capability mapping;
- broker-specific validation/tests.

It should **not** require rewriting:
- the strategy;
- butterfly construction;
- Box 4 risk logic;
- the Box 5 optimal-execution algorithm merely because the broker changed.

## Still unresolved

Everything inside the actual optimization algorithm beyond the registry/engine/port boundary remains open.

The next design step is to specify how the optimal execution engine should operate on several simultaneous instrument entries.


## Margin-aware dependency sequencing

Box 5 now has three continuously refreshed input classes:

- `[5,0,1,9,1]` Active Instrument Execution Registry.
- `[5,0,1,7,1]` Live Market Execution State: normalized quotes, executable depth/order book, spread, freshness and tradability.
- `[5,0,1,7,2]` Live Broker Account State: available cash/collateral/margin, current positions, pending orders and other account-capacity facts required for execution.

The optimizer must infer hedge/offset relationships from instrument economics and current account state rather than from strategy names.

### [5,0,2,1,2] Hedge / Offset Relationship Analyzer

This node identifies whether one current or intended position reduces, caps or offsets the risk and margin footprint of another. The representation may be quantity-aware and may include partial coverage, existing-position coverage and many-to-one relationships.

### [5,0,2,7,1] Execution Dependency Graph

The inferred hedge relationships become precedence constraints.

If action A establishes protection required to avoid an unnecessary unhedged or high-margin intermediate state before action B, confirmed execution of A is a prerequisite for B up to the covered quantity.

When reducing an existing paired position, the dependency reverses when necessary: risk-creating exposure is reduced before the protection that keeps it bounded is removed.

A submitted but unfilled protective order does not count as established protection.

### [5,0,2,1,3] Margin-Aware Sequence Optimizer

Among actions allowed by the dependency graph, Box 5 chooses the next step using live account capacity.

This component seeks to:
1. preserve required hedge coverage;
2. avoid unnecessary high-margin intermediate states;
3. reduce peak cash/collateral/margin required by the outstanding registry;
4. use only actually realized cash or margin effects from completed execution before committing further resources.

The sequence is dynamically recomputed after fills, partial fills, rejections, cancellations or material account-state changes.

Structural hedge relationships are broker-neutral. Actual rupee margin impact is not. The Broker Execution Port must therefore expose authoritative current account capacity and, where supported, hypothetical margin impact for candidate intermediate states.

This fixes one component of the eventual execution objective: **capital- and margin-efficient sequencing subject to hedge-preservation constraints**. Price improvement, urgency, fill probability, adverse selection and market impact remain separate unresolved objectives.
