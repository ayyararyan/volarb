# [5,0,0,0,0] External Dhan Execution Layer — Next-Chat Handoff

## Purpose

Design the **Dhan-specific external execution layer** that sits below the intelligent Volarb Execution + Risk Management Engine.

This is **not** the strategy execution/risk logic itself. Box 4 remains responsible for trading intelligence. The Dhan layer should be a thin provider-specific execution system that faithfully carries out canonical Volarb instructions and returns authoritative broker facts.

## Existing boundary

Upstream architecture:

```text
[3,I,8,7,1] TradeIntent
        ->
[4,0,0,0,0] Shared Execution + Risk Management
        ->
canonical broker-neutral commands / queries
        ->
[5,0,0,0,0] External Dhan Execution Layer
        ->
Dhan API / account / exchange
```

Box 4 currently owns:
- execution intelligence;
- margin-feasibility decision use;
- live risk decisions;
- future hold / adjust / recenter / hedge / reduce / exit logic.

The Dhan layer should **not** independently alter the strategy.

## What the Dhan layer must eventually handle

At minimum, investigate and design:

- authentication and session lifecycle;
- IP whitelisting requirements;
- Dhan API connectivity;
- instrument/security/token mapping;
- order placement;
- order modification;
- order cancellation;
- basket/multi-leg execution capabilities;
- order status;
- trade/fill status;
- partial fills;
- rejections;
- position retrieval;
- account/funds state;
- broker margin queries / feasibility;
- rate limits;
- retries and backoff;
- idempotency;
- duplicate-order prevention;
- reconnect/recovery;
- state reconciliation after restart;
- broker outages / stale status;
- normalized error taxonomy;
- normalized events returned to Box 4;
- audit logging.

## Architectural rule

**Dhan provides execution transport and authoritative broker facts. Volarb provides intelligence.**

The Dhan layer must not independently:
- choose a different structure;
- change strikes;
- resize for strategic reasons;
- decide to recenter;
- change exit rules;
- invent a substitute trade.

If a requested action is impossible, ambiguous, rejected, margin-infeasible, or otherwise unsafe to carry out mechanically, Dhan reports that state back to Box 4.

## Provider replaceability

Whatever contract is designed between Box 4 and Dhan should be generic enough that a future external executor such as Kotak or ICICI Securities can implement the same contract.

The goal is:

```text
Volarb Box 4
    |
generic broker contract
    |
+---+-------------------+
|                       |
Dhan executor       future broker executor
```

Replacing Dhan must not require rewriting strategy logic.

## Vector identity

Root VID reserved:

`[5,0,0,0,0] External Dhan Execution Layer`

All new Dhan-specific nodes, edges, workers, ports, adapters, states, schedulers, data contracts, and resources created in the next chat must receive immutable VIDs and be added to:

- `docs/workflows/vector-id-system.md`
- `docs/workflows/vector-id-registry.json`

Do not renumber existing VIDs.

## Files to inspect first in the next chat

- `notes.md`
- `docs/autonomous-butterfly-workflow.md`
- `docs/workflows/04-execution-risk.md`
- `docs/workflows/vector-id-system.md`
- `docs/workflows/vector-id-registry.json`

Then inspect the current repository for any existing Dhan connector, API wrapper, authentication code, market-data connector, execution code, or configuration before designing anything new.

## Working method for the next chat

Work bottom-up. First understand exactly what Dhan exposes and what already exists in `volarb`. Then define the external Dhan box and its contract to Box 4. Do not redesign unrelated upstream boxes.

The design should evolve in GitHub as the discussion proceeds, just like the current architecture.
