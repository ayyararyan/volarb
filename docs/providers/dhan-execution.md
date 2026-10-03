# Dhan Execution Provider Plug-in

Status: **provider boundary active; strategy-agnostic core and global error normalization implemented; low-latency path under active refinement.**

Last provider-boundary audit: **2026-10-03**, against repository `main` at `942003ede3c3ddb4836824e8e1dab97c58445847` and the current official DhanHQ v2 API documentation.

This document is intentionally **outside the numbered Volarb box hierarchy**.

Dhan is an **external reusable broker capability provider**. `[5,0,3,6,1] Broker Execution Port` is one important Volarb client of it, but Dhan is not owned by Internal Execution and does not know which strategy, workflow or execution engine called it. It does not receive a Box number or Volarb VID.

## Fundamental boundary

The provider translates, transmits, observes and reports. It does not think.

Conceptually:

    any authorized Volarb client
        |                 |
        | query           | broker action
        v                 v
        +---------- Dhan Provider ----------+
                       |
                       v
                 Dhan APIs / exchange

Internal Execution normally reaches Dhan through `[5,0,3,6,1] Broker Execution Port`. Strategy, research or monitoring components may also consume Dhan information through appropriate provider-facing interfaces. Dhan itself does not branch on caller identity or strategy meaning.

For **current production Volarb mutations**, the Command Commit Guard / Execution Ledger invariant remains upstream of the Broker Execution Port. Provider reusability must not be used as a shortcut around that safety path. The architectural point is that this rule belongs to the caller/core, not inside Dhan.

The Dhan implementation must be replaceable by another provider without changing Margin Optimization, Execution Slicing, Optimal Execution, Interrupt Control, State Integrity or Execution Recovery.

## Provider responsibilities

The Dhan provider owns:

- Dhan authentication and credential lifecycle;
- static-IP and Dhan account/readiness observations;
- Dhan REST/WebSocket transport and rate-limit mechanics;
- broker-neutral instrument identity to Dhan Security ID / segment translation;
- Dhan instrument metadata such as lot size, tick size, freeze quantity and tradability flags;
- place, modify, cancel and query mechanics;
- correlation projection between Volarb runtime correlation identity and Dhan correlation identity;
- Dhan order, trade, position, funds and margin retrieval;
- Dhan market quote/depth retrieval and streaming where supported;
- provider-specific normalization, provenance, timestamps and error/ambiguity reporting;
- provider-local operational state required for authentication, streams, caches and connection recovery.

The provider does **not** own:

- strategy interpretation;
- butterfly/condor/hedge/body/wing semantics;
- margin-aware execution sequencing;
- ORDERED versus UNCONSTRAINED decisions;
- execution slice count or scheduling;
- passive-chase or any other optimal-execution policy;
- decisions to wait, reprice, cancel, replace or cross the spread;
- hedge, recenter, reduction or exit policy;
- interrupt creation or priority;
- State Integrity policy;
- broker-neutral recovery policy;
- capital reserve policy or an affordability PASS/FAIL decision.

## Two canonical jobs

The provider has only two fundamental synchronous jobs:

1. **COMMAND** — perform the exact broker operation requested.
2. **QUERY** — return the exact broker information requested.

A third transport form, **STREAM**, continuously publishes broker/market facts but still makes no trading decision.

Examples:

```text
PLACE LIMIT BUY 65 <instrument> @ 12.50
        |
        v
Dhan translates -> transmits -> returns Dhan fact

GET positions
        |
        v
Dhan fetches -> normalizes -> returns positions
```

There is no butterfly method, hedge method, recenter method, execution-sequence method or strategy method in the canonical Dhan provider core.

## Caller independence

The Dhan provider is deliberately caller-agnostic.

Possible clients include:

- Broker Execution Port / Internal Execution;
- strategy and research modules that need broker or market facts;
- monitoring / reconciliation services;
- operator tooling;
- future workflows not yet designed.

The provider should not need to be modified merely because a new strategy or execution engine becomes a client.

## Speed is a first-class requirement

The Dhan provider is part of the latency-sensitive trading path. Provider overhead should be kept close to the irreducible Dhan/network latency rather than adding policy, orchestration or storage work.

### Hot-path rules

- **No LLM/MCP reasoning in the execution hot path.** MCP can remain an operator/ChatGPT façade, but machine execution should call the provider library/service directly.
- **No strategy computation inside Dhan.** Translation and transport only.
- **No artificial waits, repricing timers or sequencing sleeps inside Dhan.**
- **No provider-owned write-ahead execution ledger or fsync on each order.** Core durability happens before the provider call.
- **Pre-resolve instruments.** Runtime order submission should normally already have a resolved Dhan Security ID/segment and cached lot/tick/freeze metadata.
- **Keep the instrument master indexed in memory.** Exact Security-ID/trading-symbol/option identities use indexed lookup rather than repeated full-CSV scans.
- **Keep the provider process warm and connections reusable.** The transport is injectable so a tuned persistent HTTP client can be used without changing provider semantics.
- **Prefer streaming state for the live path.** Dhan live market WebSocket and live order updates should feed in-memory current state; REST remains available for bootstrap, snapshots and reconciliation.
- **Do independent reads concurrently where coherence permits.**
- **Respect broker rate limits mechanically without turning throttling into trading policy.**
- **Measure provider latency separately from upstream decision latency.**

Dhan currently documents Order API limits of 10 requests/second, 250/minute, 1000/hour and 7000/day, plus a 25-modification cap per order. Quote REST is limited to one request/second, which reinforces the WebSocket-first design for latency-sensitive market state.

No arbitrary Volarb latency target is frozen yet. End-to-end and per-provider p50/p95/p99 targets will be benchmarked rather than invented.

## Initial code implementation

The canonical provider core now starts with:

- `src/dhan-provider.mjs` — strategy-agnostic provider façade;
- `DhanClient.placeOrder(...)` — exact generic placement;
- `DhanClient.modifyOrder(...)` — exact generic modification;
- `DhanClient.cancelOrder(...)` — generic cancellation;
- `InstrumentMaster.resolveInstrument(...)` — exact deterministic resolution with in-memory indexes for Security ID, trading symbol and complete option identity.

The existing `placeLimitOrder(...)` and `ButterflyExecutor` remain temporarily as compatibility clients. They are not the canonical provider contract and can be retired only after their callers migrate safely.

## Existing repository substrate: classification

| Current code | Keep as Dhan mechanics | Move conceptually upstream / separate |
|---|---|---|
| `src/dhan-client.mjs` | REST transport; profile; IP; funds; positions; holdings; orders; trades; order/correlation lookup; order trades; quotes; option chain; margin calculators | Replace forced LIMIT/INTRADAY/DAY placement with a generic mechanical order translator; add modify and market-order support; classify mutation ambiguity |
| `src/instrument-master.mjs` | CSV acquisition/cache; field parsing; Security-ID and broker metadata extraction | Replace index-only/butterfly resolution with a generic economic-instrument resolver; no strike substitution or strategy choice |
| `src/web-token.mjs` / browser token modules | Token validation, renewal, private atomic storage, account verification, fail-closed recovery | Browser/UI recovery remains deployment-specific and sits behind provider authentication; it is not a Broker Execution Port semantic |
| `src/execution-mcp.mjs` | Endpoint authentication, static-IP/account observations, process ownership primitive | Butterfly preview/execute/stop/reconcile tools are not the Broker Execution Port; readiness becomes dimensional provider facts rather than a single trading-policy gate |
| `src/execution-oauth.mjs` | OAuth/PKCE can remain as service-access security when the MCP surface is retained | Decouple from `ButterflyExecutor`, `ExecutionStore` and `butterfly:execute`; this authenticates clients to the service, not Dhan brokerage semantics |
| `src/margin-preflight.mjs` | Raw single/basket Dhan margin calls and response normalization | Butterfly geometry, sequence prefixes, reserve policy, quote-age/depth policy, session timing and PASS/FAIL affordability belong upstream |
| `src/butterfly-executor.mjs` | Order/trade identity validation, correlation lookup, fill reconciliation patterns, broker status normalization, restart-safety lessons | Butterfly sequencing, hedge checks, passive pricing/repricing, waits, session policy, margin gating, preview confirmation, automatic cancellation/settlement and job execution loop belong upstream |
| `src/server.mjs` | Can remain a deployment façade over Dhan provider capabilities | Research analytics and butterfly-specific tools stay separate from provider core and must not define the Broker Execution Port |

## Safety behavior to preserve while moving ownership

The current executor has several strong invariants that must survive the refactor even though their broker-neutral ownership moves upstream:

- write intent durably before a mutation;
- never blindly retry an ambiguous placement/modification/cancellation;
- use correlation lookup to investigate an acknowledgement timeout;
- reconcile order status with actual trades/fills;
- account for fills that race with cancellation;
- block duplicate mutation while outcome is unknown;
- fail closed after restart until broker truth is reconstructed;
- verify broker order identity before mutating an order handle.

The first, fifth, sixth and restart policy are broker-neutral Execution Recovery responsibilities. Dhan supplies the provider-specific primitives and validated facts needed to implement them.

## Clean Dhan provider architecture

These are provider-internal responsibilities, not new Volarb boxes and not VID allocations. They do not have to map one-to-one to source files.

| Provider component | Mechanical responsibility |
|---|---|
| **DhanProvider façade** | Strategy-agnostic command/query façade used by the Broker Execution Port and other authorized provider clients |
| **DhanAuth / Readiness** | Access-token lifecycle, account identity, token expiry, current egress IP, Dhan whitelist observation, API/data connectivity |
| **DhanInstrumentCatalog** | Detailed/segment instrument master, deterministic contract resolution, Security ID, segment, lot/tick/freeze/tradability metadata |
| **DhanTransport** | HTTP/WebSocket transport, deadlines, safe read retries if later adopted, response parsing, rate-limit handling; never blind-retries an ambiguous mutation |
| **DhanOrderGateway** | Generic place/modify/cancel/query translation and validation, including LIMIT and MARKET requests explicitly selected upstream |
| **DhanBrokerStateReader** | Order book, trade book, order trades, positions, holdings where needed, funds/account state, historical trade backfill |
| **DhanMarginReader** | Single-order and multi-order/basket margin calculator calls; returns broker facts without affordability policy |
| **DhanMarketDataAdapter** | REST quote snapshots plus live market-feed/full-depth streams where supported; reports capability and provenance |
| **DhanOrderEventAdapter** | Account-wide live order-update stream and/or postback ingestion as low-latency observations |
| **DhanNormalizer / Error Classifier** | Maps Dhan enums/fields/errors into normalized Broker Execution Facts and explicit mutation ambiguity |
| **DhanRuntimeState** | Provider-local auth/stream/cache/capability state only; never a second Volarb execution ledger |

## Broker Execution Port capabilities Dhan must implement

The exact language-level interface remains an Internal Execution implementation task, but the Dhan provider needs mechanical support for the following broker-neutral operations:

1. Resolve a complete economic instrument identity to an opaque provider instrument reference plus normalized metadata.
2. Place an explicitly requested order without silently changing side, quantity, order type, product profile, validity or price.
3. Modify an explicitly identified live order using only changes requested upstream.
4. Cancel an explicitly identified live order.
5. Query an order by opaque broker order reference.
6. Query by runtime correlation identity through deterministic provider correlation projection.
7. Retrieve the current-day order book and trade book.
8. Retrieve trades for a specific order and historical trades needed for restart/backfill reconciliation.
9. Retrieve authoritative position snapshots.
10. Retrieve funds/collateral/account state.
11. Calculate single-order margin and multi-order/basket margin.
12. Retrieve quote/depth snapshots and, where configured, subscribe to live market data.
13. Subscribe to or ingest live order updates as an acceleration path.
14. Report provider readiness and capabilities without deciding whether Volarb should trade.

## Dhan-specific identity mapping

Volarb runtime identities remain core-owned:

    intent_id
    intent_version
    slice_id
    action_id
    correlation_id

Dhan identities remain provider-owned:

    securityId
    exchangeSegment
    orderId
    exchangeOrderId
    exchangeTradeId
    Dhan correlationId

`securityId` and other Dhan identifiers must not leak into strategy or execution-policy logic. The Broker Execution Port may carry an opaque provider instrument/order handle, but only the provider interprets its Dhan fields.

Dhan correlation IDs are limited by the broker contract. The new adapter must therefore project the core `correlation_id` deterministically into a Dhan-valid correlation value before transmission. It must not generate a fresh random butterfly correlation ID. The projection must be stable across restart and collision-checked so an ambiguous POST can be reconciled by correlation after process loss.

## Error connector: Dhan -> global Provider Error Envelope

The error layer is now frozen around one invariant:

> **No Dhan-native error crosses the provider boundary.**

Every failure from the canonical `DhanProvider` is translated into the Volarb-global `[0,0,1,7,1] Provider Error Envelope`. The caller therefore never needs to know whether the active broker is Dhan, ICICI Securities, Kotak, or another provider.

The provider preserves Dhan provenance for diagnosis — native error code/type/message, HTTP status, OMS rejection code/description and endpoint — but caller control flow keys only off global category/code/outcome.

### Global categories

`AUTHENTICATION`, `AUTHORIZATION`, `ACCOUNT_STATE`, `RATE_LIMIT`, `INVALID_REQUEST`, `ORDER_REJECTED`, `DATA_UNAVAILABLE`, `RESOURCE_NOT_FOUND`, `PROVIDER_INTERNAL`, `NETWORK`, `TIMEOUT`, `PROTOCOL`, `UNSUPPORTED`, `UNKNOWN`.

`UNKNOWN` makes the mapping total: a newly introduced or undocumented Dhan error is still converted into the global convention rather than leaking a raw broker exception.

### Current DhanHQ v2 mappings

| Dhan native code | Global category |
|---|---|
| `DH-901` | `AUTHENTICATION` |
| `DH-902` | `AUTHORIZATION` |
| `DH-903` | `ACCOUNT_STATE` |
| `DH-904` | `RATE_LIMIT` |
| `DH-905` | `INVALID_REQUEST` |
| `DH-906` | `ORDER_REJECTED` |
| `DH-907` | `DATA_UNAVAILABLE` |
| `DH-908` | `PROVIDER_INTERNAL` |
| `DH-909` | `NETWORK` |
| `DH-910` | `UNKNOWN` |
| Data `800` | `PROVIDER_INTERNAL` |
| Data `804` | `INVALID_REQUEST` |
| Data `805` | `RATE_LIMIT` |
| Data `806` | `AUTHORIZATION` |
| Data `807`-`810` | `AUTHENTICATION` |
| Data `811`-`814` | `INVALID_REQUEST` |

Transport timeout/network/protocol errors are normalized even when Dhan supplies no native code.

A successful HTTP response carrying `orderStatus=REJECTED` is also converted into `ORDER_REJECTED`; querying an already-rejected historical order remains a normal broker fact, not a failed query.

### Mutation certainty is separate from category

The envelope also carries `outcome`:

- `KNOWN_NOT_APPLIED` for definitive command rejection/refusal;
- `UNKNOWN` when a mutating command may have crossed the transport boundary but its effect cannot be proven;
- `NOT_APPLICABLE` for query/stream failures.

The Dhan mapper does not decide retry/recovery policy. It only tells the caller what failed and how certain the command outcome is.

## Normalized fact metadata

Provider results should carry enough metadata for State Integrity and Execution Recovery without embedding their policy. Where available this includes:

- provider key/version;
- observation source, e.g. Dhan REST, market WebSocket, order-update WebSocket or postback;
- local request start/completion/receive timestamps;
- Dhan/exchange timestamps present in the payload;
- snapshot scope and whether data was absent, partial or malformed;
- raw Dhan status/error code plus safe normalized error class;
- connection/authentication state;
- the core correlation identity plus opaque provider correlation/order/trade references;
- normalized quantities, prices and order states alongside raw Dhan enum values when useful.

The provider reports provenance and uncertainty. `[5,0,9,0,1] State Integrity` decides whether that evidence is sufficiently trustworthy for a requested action.

## Readiness is dimensional, not a single policy boolean

The current executor readiness check combines several useful Dhan facts. The provider should expose them separately, for example:

- authentication/token valid and expiry time;
- account identity verified;
- REST read connectivity;
- mutation connectivity;
- current outbound IP known;
- outbound IP present in Dhan's primary/secondary whitelist;
- market-data entitlement/connectivity;
- order-update stream connectivity;
- rate-limit/capability state.

Dhan documents static-IP whitelisting as mandatory for order placement/modification/cancellation, while read-only order/trade retrieval does not require it. Therefore stale/missing mutation readiness must not make all provider reads unavailable.

## Market-data architecture

The existing REST quote endpoint is useful for snapshots but Dhan documents it at one request per second. Production temporal execution should therefore be able to consume the Dhan live market WebSocket rather than continuously polling REST.

Dhan also offers deeper 20/200-level feeds only for NSE Equity and Derivatives. The provider contract must advertise market-depth capability by segment instead of pretending every exchange has identical depth.

REST snapshots remain useful for bootstrap/reconciliation and as independently timestamped observations. Stream disconnection is reported as provider state; State Integrity decides whether a given action can continue.

## Order-event architecture

Dhan's live order-update WebSocket reports account-wide order changes, including orders placed through other platforms. It is useful for low-latency observation and detecting external/manual account activity.

It is an acceleration path, not the sole recovery authority. After ambiguity or restart, the provider must still support REST order/correlation/trade/position reads. The upstream Reconciliation Engine decides when those facts are sufficient.

## Rate-limit boundary

Dhan currently publishes separate limits for Order, Data, Quote and Non-Trading APIs and caps modifications per order.

The adapter may enforce mechanical throttling needed to avoid violating Dhan limits, but it must not silently turn throttling into an execution policy. In particular it must not choose a different order action, reorder actions, or hold a time-sensitive command beyond an upstream deadline without reporting that condition.

Provider capability/readiness should make rate constraints observable to Internal Execution.

## Dhan-native composite actions deliberately excluded from the core port

### Native order slicing

Dhan offers `/orders/slicing` for orders above freeze quantity. Volarb already owns `[5,0,7,0,1] Execution Slicing`, including slice identity, scheduling and recovery. Dhan native slicing is therefore **not used by the initial Broker Execution Port implementation**. The provider may advertise that the broker has the capability, but Internal Execution remains the owner of slicing.

### Exit All Positions

Dhan's `DELETE /positions` exits all active positions and cancels all open orders for the trading day. It is too broad to be the default implementation of Volarb L3 `FLATTEN_ALL`, whose scope is all **controlled** exposure and whose mutations must remain individually attributable through the Execution Ledger.

Therefore L3 should normally resolve controlled positions/orders upstream and send explicit cancel/market actions through the Broker Execution Port. Dhan Exit All may be considered later only as a separately governed broker-wide emergency/operations escape hatch.

### Kill Switch and P&L Exit

Dhan's Kill Switch and P&L based auto-exit are broker account control-plane features. They are not implementations of Volarb Interrupt Control and are excluded from the standard Broker Execution Port for now.

## Existing behaviors that must be removed from provider-core semantics

The following current `ButterflyExecutor`/preflight behavior is explicitly not part of the future Dhan provider core:

- put-wing/body/call-wing/body roles and ordering;
- entry/exit butterfly geometry;
- hedge-deficit checks;
- personal 14:55/15:00 timing rules;
- passive quote improvement and repricing loops;
- spread/depth acceptance policy;
- automatic cancel after wait/exception;
- automatic replacement after confirmed cancellation;
- margin-affordability PASS/FAIL;
- cash-reserve policy;
- preview/confirmation as the execution control mechanism;
- automatic account serialization because unrelated orders exist.

The provider should report the relevant broker facts; upstream Volarb decides what those facts mean.

## Existing code gaps relative to the target provider

The current substrate is strong but incomplete for the Broker Execution Port. The important missing/refactor items are:

- wire the new generic `DhanProvider` into production callers while retiring legacy butterfly-only surfaces safely;
- complete generic instrument normalization across all Dhan segments beyond the currently indexed exact option/security/trading-symbol paths;
- deterministic core-to-Dhan correlation projection;
- normalized order/trade/position/funds/quote fact envelopes with provenance/timestamps;
- historical trade retrieval for restart/backfill recovery;
- live market feed integration;
- live order-update integration;
- dimensional readiness/capability reporting;
- provider rate-limit accounting;
- separation of provider-local runtime state from the core Execution Ledger;
- separation of the Broker Execution Port implementation from research/MCP butterfly façades.

## Implementation migration principle

Do not rewrite the working Dhan substrate wholesale.

Refactor by extraction:

1. preserve and test Dhan authentication, transport, master-data, API calls and validation logic;
2. extract generic Dhan order/state primitives from the butterfly executor;
3. move broker-neutral policy callers above the Broker Execution Port;
4. add the missing Dhan primitives;
5. retain the current butterfly executor only as a legacy/test harness until the broker-neutral path supersedes it;
6. delete or retire duplicated policy only after equivalent upstream tests exist.

## Official Dhan capabilities verified for this audit

Current DhanHQ v2 documentation confirms:

- place, modify, cancel, query-by-order-ID, query-by-correlation-ID, order book, trade book and per-order trade APIs;
- LIMIT, MARKET and stop-order variants plus DAY/IOC validity;
- native order slicing;
- static-IP requirement for order placement/modification/cancellation;
- single-order and multi-order margin calculators plus fund limits;
- REST quote/depth snapshots;
- live market WebSocket feeds;
- account-wide live order-update WebSocket;
- position snapshots and broker-wide Exit All;
- historical trade retrieval;
- broker account Kill Switch/P&L-exit controls;
- published API rate limits and per-order modification caps.

References:

- https://dhanhq.co/docs/v2/orders/
- https://dhanhq.co/docs/v2/authentication/
- https://dhanhq.co/docs/v2/funds/
- https://dhanhq.co/docs/v2/instruments/
- https://dhanhq.co/docs/v2/market-quote/
- https://dhanhq.co/docs/v2/live-market-feed/
- https://dhanhq.co/docs/v2/order-update/
- https://dhanhq.co/docs/v2/full-market-depth/
- https://dhanhq.co/docs/v2/portfolio/
- https://dhanhq.co/docs/v2/statements/
- https://dhanhq.co/docs/v2/traders-control/

## VID decision

No new VID is allocated by this audit.

The existing Volarb-owned `[5,0,3,6,1] Broker Execution Port`, `[5,0,4,7,1] Normalized Broker Execution Facts`, runtime identity and Execution Recovery contracts are sufficient. Dhan and its provider-internal components remain unnumbered external implementation details.


## Error implementation files

- `src/provider-error.mjs` — broker-neutral Provider Error Envelope and stable categories/codes.
- `src/dhan-error-mapper.mjs` — exhaustive Dhan-native -> global mapping with total UNKNOWN fallback.
- `src/dhan-provider.mjs` — catches every canonical provider failure and exposes only ProviderError to callers.
- `src/dhan-client.mjs` — preserves Dhan transport context (HTTP/path/method/timeout/network/protocol) for the mapper.

Canonical global contract: `docs/providers/provider-error-contract.md`.
