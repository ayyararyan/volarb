# [5,0,0,0,0] External Dhan Execution Layer — Active Design Notebook

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


## Discovery baseline — 2026-10-03

The repository already contains a reusable Dhan integration at `services/dhan-chatgpt-mcp/`. Box 5 therefore starts from an implemented substrate rather than a blank adapter.

### Existing reusable pieces

- `src/dhan-client.mjs`: Dhan API v2 client for account facts, orders/trades, funds, positions, margin, quotes, option-chain calls, static-IP lookup, LIMIT order placement and cancellation.
- `src/instrument-master.mjs`: live detailed instrument-master download, caching and NIFTY/BANKNIFTY/SENSEX resolution to Dhan Security IDs and contract metadata.
- `src/margin-preflight.mjs`: fail-closed, sequence-bound multi-order margin feasibility using current funds/positions/orders and fresh executable quotes.
- `src/butterfly-executor.mjs`: durable four-leg ENTRY/EXIT executor with exact-plan confirmation, limit pricing, partial-fill handling, position/trade reconciliation, write-ahead intent, correlation-ID recovery, restart fail-closed behavior and duplicate-execution protection.
- `src/execution-mcp.mjs` and `src/execution-oauth.mjs`: separate authenticated execution surface, static-IP/account readiness checks, OAuth/PKCE and single-process execution lock.
- `src/web-token*.mjs`: local token lifecycle/recovery machinery with explicit human-stop behavior for OTP/CAPTCHA/manual verification.

### Current implementation is not the final architecture

The current `ButterflyExecutor` contains logic that is too strategy/execution-policy-specific to automatically classify as Box 5. Examples include butterfly leg ordering, ENTRY versus EXIT semantics, the 14:55/15:00 timing policy, repricing rules and hedge-coverage sequencing.

During the Box 5 design we will classify each such behavior into one of two buckets:

1. **Box 4 intelligence/policy** — what Volarb decides should happen.
2. **Box 5 mechanical safety/provider behavior** — what any Dhan command must satisfy to be transmitted and authoritatively reconciled.

Nothing is moved or deleted yet.

### Dhan broker capabilities verified

Current DhanHQ v2 documentation confirms:

- place / modify / cancel pending orders;
- order status, order book, trade book and trade lookup;
- order lookup by caller-supplied correlation ID;
- order slicing above freeze quantities;
- live order-update WebSocket plus access-token-level postback/webhook;
- positions and funds/account state;
- single-order and multi-order margin calculators;
- static-IP requirement for order mutations;
- 24-hour access tokens for individual traders;
- published order-API rate limits;
- instrument master with Security IDs and derivative metadata.

Dhan also exposes Super Orders, Kill Switch, P&L-based exit and Exit All. These are **capabilities only**. They are not adopted as Box 5 responsibilities because doing so prematurely could leak risk/strategy decisions into the broker layer.

No official atomic arbitrary multi-leg iron-butterfly placement endpoint has been identified. The multi-order endpoint currently used by Volarb is a **margin calculator**, not a basket execution primitive.

### Known implementation gaps for later design

- generic Box-4 <-> broker-provider contracts;
- generalized command translation beyond the current butterfly plan;
- order modification support in the local Dhan client;
- push-based order/fill ingestion;
- explicit rate-limit governance and retry/backoff policy;
- normalized Dhan error taxonomy;
- authoritative freshness/staleness model for broker state;
- restart/reconciliation state machine at the generic provider layer;
- classification of current executor safeguards between Box 4 and Box 5;
- audit/event contract returned upstream.

### VID status

No internal Box 5 VIDs are created by this inspection. `[5,0,0,0,0]` remains the only allocated Box 5 identity until an internal object is actually decided.
