> **Portable kit update — 2026-09-29:** See [agent kit setup](../../docs/AGENT_KIT.md).
> Runtime state now defaults to `$VOLARB_DATA_DIR/dhan` (default data root
> `~/.local/share/volarb`), not this source directory. Set `DHAN_RUNTIME_DIR`
> explicitly to reuse an existing private MCP state directory. Browser recovery
> is opt-in/macOS-only, with `DHAN_PIN_FILE` supplied privately. Setup never starts
> the service or activates execution. Machine paths and deployment verification
> below are historical records, not portable installation instructions.

# Dhan ChatGPT MCP v0.3

MCP server with a read-only research endpoint connecting ChatGPT to DhanHQ API v2, with index-symbol resolution and option-surface analytics for NIFTY, BANKNIFTY and SENSEX.

## What changed in v0.2

You no longer need to supply Dhan security IDs for the main index-option workflows. The server downloads Dhan's detailed instrument master, resolves the index, selects active expiries and can analyze the entire chain server-side.

New tools:

- `dhan_resolve_underlying`
- `dhan_get_option_expiries_by_symbol`
- `dhan_get_option_chain_by_symbol`
- `dhan_analyze_option_surface`
- `dhan_get_butterfly_state`

The original v0.1 tools remain available for backwards compatibility.

`dhan_get_butterfly_state` is designed for the Butterfly Market Outlook workflow. It reads current positions, recognizes a standard carried iron butterfly when possible, pulls the full Dhan chain for the position expiry, maps every leg to live IV/Greeks/OI/bid-ask, computes net Greeks, and returns option-surface diagnostics and risk-neutral distribution mapping.

The original `/mcp` endpoint remains read-only. A separate authenticated `/execution/mcp` endpoint now provides the opt-in iron-butterfly executor described below; it is disabled for live trading by default.

## Install / upgrade

```bash
npm ci --ignore-scripts
cp .env.example .env
```

Keep your existing real `.env` if upgrading from v0.1. Do not overwrite your Dhan credentials.

Start:

```bash
npm start
```

Health check:

```bash
curl http://127.0.0.1:3000/healthz
```

Expected version:

```json
{"ok":true,"service":"dhan-chatgpt-mcp","version":"0.3.0"}
```

## ngrok development setup

If you expose the server through ngrok, use:

```dotenv
MCP_HOST=0.0.0.0
MCP_ALLOWED_HOSTS=YOUR-NGROK-HOST.ngrok-free.dev,127.0.0.1,localhost
```

Then:

```bash
ngrok http 3000 --url https://YOUR-NGROK-HOST.ngrok-free.dev
```

After upgrading the running server, rescan/refresh the Dhan app in ChatGPT so the five new tools are discovered.

## Examples

No security IDs:

```text
@Dhan resolve NIFTY
@Dhan get the nearest NIFTY expiry
@Dhan get the NIFTY option chain for the nearest expiry
@Dhan analyze the BANKNIFTY option surface
@Dhan get my current NIFTY butterfly state
```

### Surface analytics

`dhan_analyze_option_surface` calculates, from the full chain:

- underlying spot and parity-implied forward;
- ATM strike, ATM IV and ATM straddle;
- local smile slope and curvature;
- approximately 25-delta call/put IV, risk reversal and butterfly;
- a discrete option-implied risk-neutral distribution;
- q10/median/q90 and modal bucket;
- 1% and 1.5% tail probabilities;
- call/put OI concentration and change-OI;
- near-ATM quote coverage and median relative spread;
- optional mapping of a butterfly's body/wings onto the distribution.

The distribution is a **risk-neutral option-implied distribution**, not a real-world forecast.

## Dhan data sources

- Account/positions/orders/trades/funds: DhanHQ API v2
- Quotes and market depth: DhanHQ Market Quote API
- Full option chain: DhanHQ Option Chain API
- Symbol/security-ID resolution and lot size: Dhan detailed instrument master

The instrument master is cached for six hours by default.

## Security

1. Dhan credentials remain in `.env` and are never returned by MCP tools.
2. `/mcp` remains read-only. `/execution/mcp` requires authentication and a separately enabled live-trading configuration.
3. The server defaults to loopback-only (`127.0.0.1`).
4. If using public ngrok with `No authentication`, treat the URL as temporary development infrastructure and stop ngrok when not in use.
5. Trading tools require an approved, unexpired plan, authenticated access and a verified Dhan-whitelisted static outbound IP. Do not expose trading with No authentication.

## Local Mac deployment — migrated 2026-09-29

Active project: `/Users/maheit/dhan-chatgpt-mcp` on the OpenClaw Mac.

- Public MCP URL (unchanged): `https://YOUR-NGROK-HOST.ngrok-free.dev/mcp`
- Local MCP: `http://127.0.0.1:3000/mcp`; health: `/healthz`.
- LaunchAgents: `com.aryanayyar.dhan-mcp` and `com.aryanayyar.dhan-mcp-tunnel` under `~/Library/LaunchAgents`. They start at user login and restart on exit; the Mac must be awake and online.
- Dhan credentials are in mode-600 `.env`; tunnel credentials are in mode-600 `.private/ngrok.yml`. No secrets are stored in plists. `.private/` is excluded from Git.
- The Dhan token was copied unchanged and verified live. It still requires normal web-token renewal/replacement; migration does not extend its expiry. After updating `.env`, restart the server.
- Source code, package lock and original credentials matched the personal Mac by SHA-256. Dependencies were installed with `npm ci --ignore-scripts`; all five existing tests passed.
- Verified local/public MCP initialization and discovery of all 15 read-only tools, plus live profile, positions, orders, quotes and NIFTY chain calls. These were connectivity tests, not a trading review.
- The original personal-Mac server and ngrok processes were stopped. Its project was retained intact at `/Users/aryanayyar/dhan-chatgpt-mcp` for rollback.
- Existing ChatGPT connector URL does not need changing; connector UI state was not inspected. No OpenClaw tool registration or unrelated VolArb SSH adapter was changed.

Check/restart services:

```bash
launchctl print "gui/$(id -u)/com.aryanayyar.dhan-mcp"
launchctl print "gui/$(id -u)/com.aryanayyar.dhan-mcp-tunnel"
launchctl kickstart -k "gui/$(id -u)/com.aryanayyar.dhan-mcp"
launchctl kickstart -k "gui/$(id -u)/com.aryanayyar.dhan-mcp-tunnel"
```

Rollback must stay on the office Mac: restore a verified local source/dependency backup after stopping the local services. Do not restart the personal-Mac deployment. Keep credentials, browser profiles and operational state local. Set `NGROK_DOMAIN` privately when using the repository launcher; the deployed launcher may retain its local hostname.

## Entry-margin preflight — 2026-09-29

The research `/mcp` now adds two **read-only** tools:

- `dhan_calculate_basket_margin({legs})`: Dhan multi-order calculator including current positions/orders. Raw indicative requirement, never an affordability approval.
- `dhan_check_butterfly_margin({symbol,expiry,lower,center,upper,lots,reserveRupees?,reservePercent?})`: resolves current contracts/lot sizes, checks funds/positions/orders and executable-side quote depth/time, then calls the calculator for all four wings-first prefixes. Returns `PASS`, `FAIL` or `UNVERIFIED`, peak vs final requirement, reserve and headroom. Omitted reserve means UNVERIFIED. If both reserve forms are supplied, the larger wins; percentage applies to available funds.

No order endpoints are called. Entry-only; recenter/exit transitions are not simulated. The default WINGS_FIRST sequence is put wing buy, call wing buy, put body sell, call body sell. A different sequence needs a new explicitly sequence-bound preflight; see PAIRED_HEDGES below. Complete-stage estimates are indicative, not a guarantee against partial fills or RMS changes. The controller must still enforce strategy/liquidity/event gates and the 15:00 flat deadline.

**Source update, 29 September 2026 (not yet deployed):** optional
`entrySequence: "PAIRED_HEDGES"` computes put wing → put body → call wing → call
body prefixes, matching the executor. Omission retains `"WINGS_FIRST"` for existing
callers. The returned `entrySequence`, `sequence` and `stages` bind the result to
that path; a caller must verify them. Supply `reserveRupees: 1000` for the adopted
cash reserve. This adds no orders, scheduler, risk-budget enforcement or live
authorization. Refresh the MCP tool schema only after deliberate deployment.

Account-inclusive reported totals are compared conservatively against free funds (utilised margin is **not** subtracted); existing positions may overstate the incremental requirement. Premium is not added again to Dhan's total. Pending orders, changed account state, stale/insufficient quote depth, zero/malformed margin, unavailable APIs or missing reserve all prevent PASS. Results expire after 30 seconds or immediately on account/price/quantity/sequence changes. No account credentials are returned by these tools.

Verified REST contract: `/margincalculator/multi` with `scripList`, `includePosition`, `includeOrder`, matching the official Dhan Python SDK. Live response uses `totalMargin`; documented `total_margin` also supported. Calculator and funds calls were tested with the existing Dhan Web token, without orders. Refresh the ChatGPT connector tool list if the two new tools are not visible after server reload.


## Iron-butterfly executor (2026-09-29)

Implemented in `src/butterfly-executor.mjs`. This is a four-leg **short iron butterfly**, not a three-strike all-call/all-put 1:-2:1 butterfly. Same underlying/expiry; equal requested unit quantities; put and call bodies share the centre. No strategy selection or risk recommendation is performed.

**ENTRY:** buy lower put wing → fully verify fill/owned units → sell put body → verify fill → buy upper call wing → fully verify fill/owned units → sell call body.

**EXIT:** buy back call body → verify it is fully closed → sell call wing → buy back put body → verify it is fully closed → sell put wing.

### Endpoints and connection

- Existing research endpoint remains `https://YOUR-NGROK-HOST.ngrok-free.dev/mcp` (no trading tools).
- Authenticated executor: `https://YOUR-NGROK-HOST.ngrok-free.dev/execution/mcp`.
- OAuth authorization-server metadata: `/.well-known/oauth-authorization-server`.
- OAuth protected-resource metadata: `/.well-known/oauth-protected-resource/execution/mcp`.
- Add a **separate OAuth-authenticated MCP connection** in ChatGPT using the executor URL; retain the existing research connection. OAuth supports DCR, S256 PKCE, one-hour access tokens, rotating seven-day refresh tokens, and revocation. Protocol handling uses the official MCP SDK. ChatGPT UI completion is not established by endpoint tests.
- The browser consent form requires the local executor passphrase in `.private/execution-token` (mode 600). Retrieve locally; **never paste it or Dhan credentials into chat/tool arguments**. This is a newly generated MCP credential, not the Dhan access token. Owner-capable CLI clients may use it directly as an HTTP Bearer token.
- Only recognized `https://chatgpt.com` callback paths are accepted by default. Other clients require exact trusted redirect URIs in `MCP_OAUTH_REDIRECT_URIS`. Registered clients/tokens persist privately across restarts. Rotating the owner passphrase and restarting invalidates issued OAuth credentials.

### Activation (not performed)

1. Obtain/confirm a **static outbound public IP** for this Mac. Ngrok's inbound URL/IP is not the Dhan API egress IP. The observed egress on 2026-09-29 was `125.22.155.122`; permanence was not verified, and it did not match the broker whitelist. Do not whitelist a changing address based only on this observation.
2. Register that verified static IP through Dhan Web's DhanHQ settings. No IP-setting mutation is exposed by this MCP. Dhan limits how often a whitelist can be changed; inspect existing primary/secondary entries before replacing either.
3. Complete the authenticated client connection. Configure `.env` with `DHAN_EXECUTION_EGRESS_IP=<verified static IP>`, `DHAN_EXECUTION_STATIC_IP_CONFIRMED=true`, then `DHAN_EXECUTION_ENABLED=true`. Preserve the existing Dhan credentials and `MCP_EXECUTION_TOKEN_FILE`; restart the server. Defaults remain disabled.
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
- Execution is serialized across MCP clients, with a process lock and fsynced write-ahead intent. State lives under `.private/execution/`. Keep it across restarts. A crash while a DAY order is live may leave that order at the exchange; inspect Dhan immediately. Normal shutdown requests a stop and attempts confirmed cancellation.
- Intraday only: entries must fit before 14:55 IST, reserving time before the 15:00 flat deadline. Exits are separately requested; late risk-reducing exits are permitted until exchange close. **No automatic 15:00 square-off, stop-loss, position monitoring or guaranteed fill/flatness is installed.** Host sleep/network/broker failure can prevent cancellation and exits. Regular weekdays plus live quote validation are enforced; no special-session calendar is assumed.
- Operational order/fill evidence is not a new P&L ledger. Existing VolArb canonical accounting remains authoritative and must be reconciled through its shared writer; no financial ledger, invented fill or profit was created by this development task.

### Verification and rollback

Run `npm test`. Tests use synthetic brokers only; they cannot place Dhan orders. Coverage includes sequence/hedge checks, partial fills, cancel/fill races, timeouts, duplicate calls, stops, recovery, prices/units/freeze limits, insufficient funds, authentication, PKCE, callback restrictions, refresh/revocation and process locking.

Private pre-change source/dependency backups are in `.private/executor-backup-*`; the pre-change `.env` backup is `.private/env-before-executor-*`. To roll back, stop the server, first reconcile any real pending orders if live trading was ever enabled, restore the relevant source/package files and run `npm ci --ignore-scripts`, then restart. Never discard execution state to bypass a recovery blocker.

References: [Dhan orders](https://dhanhq.co/docs/v2/orders/), [Dhan funds/margin](https://dhanhq.co/docs/v2/funds/), [Dhan IP setup](https://dhanhq.co/docs/v2/authentication/), [OpenAI MCP authentication](https://developers.openai.com/plugins/build/auth).


## Office-Mac browser token recovery — 2026-09-29

Authentication now runs on demand before the MCP Dhan client sends requests. No scheduler was added. The server rereads the local `.env` token through its provider; future rotations need no server restart. Missing/expired/rejected tokens, or tokens expiring by the required session end plus a five-minute buffer, open a dedicated local Chrome profile. Healthy tokens are reused, with a live account-identity probe cached for at most 60 seconds.

```sh
npm run auth:check
npm run auth:recover
npm run auth:setup
# Explicit future/special-session horizon (supply the actual date):
node src/token-cli.mjs --recover --session-end '2026-09-30T15:30:00+05:30'
```

`auth:setup` opens a private native Mac dialog for the login mobile number (never paste it in chat). PIN is read privately from `/Users/maheit/Projects/VolArb/.env`. Browser state and optional login-number configuration remain under this project's mode-700 `.private/`; the target credentials file is `.env`, not `.environment`. Nothing in this workflow uses SSH or the personal Mac. The separate legacy VolArb SSH account adapters were not migrated by this change and must not be used for this workflow.

The default horizon is today's 15:30 IST regular NSE/BSE session close plus five minutes; after close it requires ten minutes of current validity and does not infer the next trading date. This does not change the strategy's 15:00 exit deadline. Explicit session horizons require a timezone.

Browser steps: verify displayed account ID → DhanHQ Trading APIs → capture an existing suitable Dusty web token, or Generate → Dusty → 24 Hours → Generate Access Token. Capture stays in process memory/private pending journal, not the clipboard or logs. Verify `/profile` and account identity before merging only token fields into `.env` using mode-600 atomic replacement and concurrent-change detection.

After verified installation, revoke expired web tokens and older Dusty tokens. Keep the installed token, newer concurrent Dusty tokens and unrelated active applications. Confirm the retained token still works. Cleanup failure is reported separately and recorded in `.private/token-cleanup.json`; it does not roll back a working new token. No token-generation TOTP API, enrollment, order operations or cloud credential storage is used.

OTP/CAPTCHA/manual verification stops automation and leaves the browser available. Unknown UI, network/rate-limit errors and account mismatch do not trigger blind regeneration. One PIN submission per attempt, a five-minute recovery cooldown and a cross-process lock prevent login loops. An interrupted successful generation can be recaptured from the web table. A pending `.private/pending-web-token.json` is validated/imported before any new generation. Never print that file or raw browser token tables. Inspect a stale `.private/token-recovery.lock/owner` locally and verify its process is dead before removing a crash-left lock.

Validation on 2026-09-29: live browser web-token generation and private installation verified; previous Dusty token revoked, replacement alone retained and `/profile` verified. A fresh signed-out browser test automatically switched QR to mobile login and submitted the privately saved mobile number, then correctly stopped at Dhan OTP verification before PIN. Saved-session browser restart/recapture/cleanup and live MCP profile access passed. PIN entry after the human OTP step remains unverified end-to-end; no claim of unattended OTP bypass.

## Repository publication boundary

This is the source snapshot of the office-Mac service. Publishing it does not deploy, restart, enable execution, or change the live account. Dhandho remains research-only; Aryan executes. Credentials, private profiles, token captures, logs and operational execution state are intentionally excluded. The browser/PIN integration is office-Mac-specific; Linux CI runs synthetic tests, not live browser authentication.

## Follow-up publication verification — 2026-09-29

Local `/healthz` returned HTTP 200 and version 0.3.0. Read-only MCP tool discovery did **not** expose `entrySequence` in the running margin tool schema, so the paired-hedge patch is published source, not verified deployed functionality. No broker tool was called and no service restarted during this check. See [shadow day workflow](../day-workflow/README.md) for the new offline orchestrator and tests.


## Fixes — 2026-09-30

- `dhan_get_butterfly_state` normalizes Dhan's timestamped position expiry (`YYYY-MM-DD HH:MM:SS`) to `YYYY-MM-DD` before the option-chain call. Previously every open-position review failed with `Invalid Expiry Date`. Covered by `test/core.test.mjs`.
- The five-minute HF sampler (`node src/workflow-data-cli.mjs --scope hf`) must be started as a local process on the office Mac. Launching it through a remote node exec is refused before sampling begins. Convert its evidence for the RV forecaster with the RV skill's `scripts/build_rv_input.py`.
