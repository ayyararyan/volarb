# Dhan legacy butterfly executor — compatibility surface

Status: **compatibility-active; disabled for live trading by default**. This is not
`component.execution_engine` or the Broker Execution Port. The authenticated MCP
endpoint and synthetic regression tests still depend on this implementation; its
source and import paths are retained until callers are deliberately migrated.

Implemented in [`butterfly-executor.mjs`](../../services/dhan-chatgpt-mcp/src/butterfly-executor.mjs). This is a four-leg **short iron butterfly**, not a three-strike all-call/all-put 1:-2:1 butterfly. Same underlying/expiry; equal requested unit quantities; put and call bodies share the centre. No strategy selection or risk recommendation is performed.

**ENTRY:** buy lower put wing → fully verify fill/owned units → sell put body → verify fill → buy upper call wing → fully verify fill/owned units → sell call body.

**EXIT:** buy back call body → verify it is fully closed → sell call wing → buy back put body → verify it is fully closed → sell put wing.

### Endpoints and connection

- Existing research endpoint remains `https://YOUR-NGROK-HOST.ngrok-free.dev/mcp` (no trading tools).
- Authenticated executor: `https://YOUR-NGROK-HOST.ngrok-free.dev/execution/mcp`.
- OAuth authorization-server metadata: `/.well-known/oauth-authorization-server`.
- OAuth protected-resource metadata: `/.well-known/oauth-protected-resource/execution/mcp`.
- Add a **separate OAuth-authenticated MCP connection** in ChatGPT using the executor URL; retain the existing research connection. OAuth supports DCR, S256 PKCE, one-hour access tokens, rotating seven-day refresh tokens, and revocation. Protocol handling uses the official MCP SDK. ChatGPT UI completion is not established by endpoint tests.
- The browser consent form requires the local executor passphrase in `$DHAN_RUNTIME_DIR/.private/execution-token` (mode 600). Retrieve locally; **never paste it or Dhan credentials into chat/tool arguments**. This is a newly generated MCP credential, not the Dhan access token. Owner-capable CLI clients may use it directly as an HTTP Bearer token.
- Only recognized `https://chatgpt.com` callback paths are accepted by default. Other clients require exact trusted redirect URIs in `MCP_OAUTH_REDIRECT_URIS`. Registered clients/tokens persist privately across restarts. Rotating the owner passphrase and restarting invalidates issued OAuth credentials.

### Activation prerequisites — reference only, not performed by setup

1. Obtain/confirm a **static outbound public IP** for this Mac. Ngrok's inbound URL/IP is not the Dhan API egress IP. A previous one-time egress observation is not proof of a static address or current whitelist state.
2. Register that verified static IP through Dhan Web's DhanHQ settings. No IP-setting mutation is exposed by this MCP. Dhan limits how often a whitelist can be changed; inspect existing primary/secondary entries before replacing either.
3. Complete the authenticated client connection. Configure the private runtime `.env` with `DHAN_EXECUTION_EGRESS_IP=<verified static IP>`, `DHAN_EXECUTION_STATIC_IP_CONFIRMED=true`, then `DHAN_EXECUTION_ENABLED=true`. Preserve the existing Dhan credentials and `MCP_EXECUTION_TOKEN_FILE`; restart the server. Defaults remain disabled.
4. Call `dhan_executor_readiness`. It checks current outbound IP, Dhan's primary/secondary whitelist and account identity without submitting orders. An IP-check outage blocks execution. Whitelisting the machine does not authenticate callers; OAuth is separately required.
5. For each trade, approve a fresh preview specifying exact strikes, expiry, lots and all four price bounds. No test/live order was submitted during this implementation.

### Tools and usage

| Tool | Purpose |
|---|---|
| `dhan_executor_readiness` | Verify configuration/IP/account; no orders. |
| `dhan_preview_butterfly` | Resolve contracts, inspect fresh account/depth, persist a 60-second plan; no orders. |
| `dhan_execute_butterfly` | Start exactly the approved plan with its `planId` and `confirmation`; returns immediately. |
| `dhan_butterfly_execution_status` | Read operational progress and verified fills; not a fresh broker snapshot. |
| `dhan_stop_butterfly_execution` | Stop new legs and cancel this job's pending order; **does not flatten fills**. |
| `dhan_reconcile_butterfly_execution` | Read-only order/trade/position recovery; never automatically resubmits. |

Preview input (synthetic illustration only; NOT a recommendation or current contract):

```json
{
  "action": "ENTRY",
  "symbol": "NIFTY",
  "expiry": "2026-10-01",
  "lower": 25000,
  "center": 25500,
  "upper": 26000,
  "lots": 1,
  "limits": {"putWing": 20, "putBody": 10, "callWing": 20, "callBody": 10},
  "waitSeconds": 8,
  "maxReprices": 3,
  "stepTicks": 1,
  "improveTicks": 1,
  "maxDurationSeconds": 180
}
```

For BUY legs each `limits` value is the **maximum rupees/unit**; for SELL legs it is the **minimum rupees/unit**. For EXIT the directions reverse, so supply new bounds. No capital, size or price bound is inferred for the user.

### Pricing and completion semantics

- Only `LIMIT`, `DAY`, `INTRADAY` orders; AMO and market fallback are impossible through the executor adapter.
- Buy starts at bid + 1 tick, sell at ask − 1 tick, capped by the opposite best quote and user bound. It need not beat LTP: LTP may be stale or outside the current spread. Tick size/lot/freeze limit come from the current Dhan contract master (tick field in paise, converted to rupees).
- Default waits 8 seconds, then cancels, verifies terminal status and actual fills, and replaces **only the remaining quantity**. Up to three reprices (four attempts) per leg; fresh book re-anchoring and a 180-second total submission window. Cancellation/reconciliation may extend beyond that window; no new order is submitted after it.
- Quote polls are spaced at least 1.1 seconds. Depth, spread, circuit bands and recent same-session trade timestamps are checked. REST does not provide a separate exchange timestamp for book freshness; request latency and last-trade age are conservative proxies, not an exchange book-clock guarantee.
- Before every placement, refresh broker positions/orders, available funds and the single-order margin calculator. Sale proceeds are **never** synthetically added to cash; funds must actually be available. Margin is indicative and conservative; broker RMS decides the actual hedge benefit/acceptance. This does not promise that the four-leg strategy can be funded from premium alone.
- No wings shared with pre-existing selected-contract positions; unrelated outstanding account orders block the job. Do not manually trade these contracts or run another executor during a job. Broker APIs cannot atomically lock out other clients; external account changes cause a stop when detected.
- A body is never started until its entire requested wing is filled and positions reconciled. Partial body fills remain covered. A wing exit waits until its corresponding body is fully closed. Fills, not order acceptance, advance the sequence.
- Rejected/unfilled/partial jobs stop as `PAUSED`, retaining filled exposure and wings. No unrequested rollback trades. To unwind, create an `EXIT` plan for the same geometry; it reads actual residual quantities, including incomplete entries. Do not retry ENTRY over partially owned contracts.
- Ambiguous placement/cancellation, mismatched positions, missing trade evidence or process interruption produces `RECOVERY_REQUIRED`. No second POST after a timeout. Correlation IDs are lookup aids, not assumed broker idempotency keys. Resolve remaining pending/unknown orders in Dhan, then call reconcile. An absent correlation lookup is not proof that the order never existed; truly ambiguous cases require operator investigation, not deleting state and retrying.
- Execution is serialized across MCP clients, with a process lock and fsynced write-ahead intent. State lives under `$DHAN_RUNTIME_DIR/.private/execution/` (default runtime root: `$VOLARB_DATA_DIR/dhan`). Keep it across restarts. A crash while a DAY order is live may leave that order at the exchange; inspect Dhan immediately. Normal shutdown requests a stop and attempts confirmed cancellation.
- Intraday only: entries must fit before 14:55 IST, reserving time before the 15:00 flat deadline. Exits are separately requested; late risk-reducing exits are permitted until exchange close. **No automatic 15:00 square-off, stop-loss, position monitoring or guaranteed fill/flatness is installed.** Host sleep/network/broker failure can prevent cancellation and exits. Regular weekdays plus live quote validation are enforced; no special-session calendar is assumed.
- Operational order/fill evidence is not a new P&L ledger. Existing VolArb canonical accounting remains authoritative and must be reconciled through its shared writer; no financial ledger, invented fill or profit was created by this development task.

### Verification and rollback

From `services/dhan-chatgpt-mcp/`, run `npm test`. Tests use synthetic brokers only; they cannot place Dhan orders. Coverage includes sequence/hedge checks, partial fills, cancel/fill races, timeouts, duplicate calls, stops, recovery, prices/units/freeze limits, insufficient funds, authentication, PKCE, callback restrictions, refresh/revocation and process locking.

Historical deployment backup locations are recorded in the [September service notes](../../archive/deployment/dhan-office-mac/README.md); their current presence is not assumed. To roll back, stop the server, first reconcile any real pending orders if live trading was ever enabled, restore the relevant source/package files and run `npm ci --ignore-scripts`, then restart. Never discard execution state to bypass a recovery blocker.

References: [Dhan orders](https://dhanhq.co/docs/v2/orders/), [Dhan funds/margin](https://dhanhq.co/docs/v2/funds/), [Dhan IP setup](https://dhanhq.co/docs/v2/authentication/), [OpenAI MCP authentication](https://developers.openai.com/plugins/build/auth).
