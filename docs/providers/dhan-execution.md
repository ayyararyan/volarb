# Dhan Execution Provider Plug-in

Status: active provider discovery / implementation substrate.

This document is intentionally **outside the numbered Volarb box hierarchy**.

Dhan is a concrete provider implementation beneath `[5,0,3,6,1] Broker Execution Port`. It does not receive a Box number or Volarb VID.

## Responsibility

Dhan provides broker-specific translation, order transport, and authoritative broker facts.

It does not own the broker-neutral optimal-execution algorithm.

Conceptually:

```text
[5,0,2,1,1] Optimal Execution Engine
        |
[5,0,3,6,1] Broker Execution Port
        |
        v
Dhan provider plug-in
        |
        v
Dhan API / account / exchange
```

## Existing repository substrate

`services/dhan-chatgpt-mcp/` already contains substantial reusable Dhan functionality:

- `src/dhan-client.mjs`
  - Dhan API v2 transport;
  - profile/funds/positions/holdings/orders/trades;
  - order lookup by ID and correlation ID;
  - order trade lookup;
  - quote/LTP/option-chain calls;
  - single and multi-order margin calculation;
  - LIMIT order placement;
  - cancellation;
  - whitelisted-IP lookup.

- `src/instrument-master.mjs`
  - detailed Dhan instrument master;
  - NIFTY/BANKNIFTY/SENSEX resolution;
  - Security ID;
  - lot size;
  - tick size;
  - freeze quantity;
  - tradability metadata.

- `src/execution-mcp.mjs` / `src/execution-oauth.mjs`
  - authenticated execution surface;
  - static-IP/account readiness;
  - OAuth/PKCE;
  - single-process execution lock.

- `src/butterfly-executor.mjs`
  - durable write-ahead execution state;
  - correlation-ID recovery;
  - fill/trade reconciliation;
  - partial-fill handling;
  - restart fail-closed behavior;
  - duplicate-execution protection;
  - quote/spread/depth/tick/freeze checks;
  - current butterfly-specific sequencing and repricing logic.

- `src/margin-preflight.mjs`
  - sequence-bound margin feasibility using current Dhan account/order state.

## Architectural reclassification

The current `ButterflyExecutor` mixes two categories of behavior:

1. **Dhan-provider mechanics**, which can remain in this plug-in.
2. **Broker-neutral optimal-execution policy**, which should migrate conceptually into Box 5.

Nothing is moved in code merely by this architecture decision. Classification and refactoring will happen only after the optimal-execution design is explicit.

## Provider-only rule

The Dhan plug-in must not:
- choose an alternative strategy;
- change the desired economic instrument;
- choose substitute strikes;
- resize for strategic reasons;
- decide to recenter;
- invent a hedge;
- own a Dhan-specific duplicate of the reusable optimal-execution algorithm.

It may enforce mechanical broker validity and report that an operation is impossible, rejected, ambiguous, stale, unavailable, or otherwise not safely transmittable.

## Provider identity

Concrete provider implementations use provider metadata rather than Volarb VIDs, for example:

```text
provider_key: dhan
implementation: services/dhan-chatgpt-mcp
provider_version: ...
```

Future providers can use keys such as `kotak` or `icici` while implementing the same broker execution port.
