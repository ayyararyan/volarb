# Dhan Provider and MCP service

Status: **active source; deployment is separate**. Package version: `0.3.0`.
This directory contains the reusable Dhan Provider (`provider.dhan`), a read-only
research MCP façade, and an explicitly retained legacy butterfly executor. It does
not implement the generic Execution Engine or authorize live trading.

## Boundaries and entrypoints

```text
Strategy → optional Strategy Execution Adapter → Execution Engine
                                                  ↓
                                          Broker Execution Port
                                                  ↓
                                            Dhan Provider → Dhan
```

| Surface | Canonical entrypoint | Responsibility |
|---|---|---|
| Reusable provider | [`src/dhan-runtime.mjs`](src/dhan-runtime.mjs), package export `dhan-chatgpt-mcp/runtime` | Creates configured provider, translator, readiness and Broker Execution Port |
| Broker Execution Port | [`src/dhan-broker-port.mjs`](src/dhan-broker-port.mjs), export `dhan-chatgpt-mcp/broker-port` | Broker-neutral QUERY / COMMAND / STREAM interface |
| Translation and facts | [`src/dhan-translator.mjs`](src/dhan-translator.mjs), [`src/dhan-normalizer.mjs`](src/dhan-normalizer.mjs) | Dhan payloads, deterministic correlation projection and normalized facts |
| Error mapping | [`src/dhan-error-mapper.mjs`](src/dhan-error-mapper.mjs) | Dhan failures → global Provider Error Envelope |
| Shared contracts | [canonical Python contracts](../../execution-engine/volarb_execution/), [JavaScript compatibility](../../compat/javascript/execution-contracts/README.md) | Python owns the Execution Engine contracts; the Node provider consumes a transitional JS-compatible wire vocabulary |
| Research MCP | [`src/server.mjs`](src/server.mjs), `npm start` | `/mcp`: read-only account, market, option-surface and margin tools |
| Research capture | [`src/workflow-data-cli.mjs`](src/workflow-data-cli.mjs) | Explicit read-only evidence for [`day-workflow`](../day-workflow/README.md) |
| Compatibility execution | [`src/butterfly-executor.mjs`](src/butterfly-executor.mjs), [`src/execution-mcp.mjs`](src/execution-mcp.mjs) | Opt-in authenticated `/execution/mcp`; strategy-specific legacy behavior, not the generic engine |

Use the [provider boundary](../../docs/providers/dhan-execution.md) for ownership,
the [call map](../../docs/providers/dhan-execution-engine-call-map.md) for connector
operations, and the [global error contract](../../docs/providers/provider-error-contract.md)
for failure semantics. The pipeline implementation status is documented in
[Execution Engine](../../execution-engine/README.md).

Programmatic callers import `createDhanRuntime` and use `runtime.port.call(...)`
or `runtime.port.openStream(...)`; MCP and an LLM are not required. Keep the runtime
warm. Provider-native payload construction stays in the translator. Dhan reports
broker facts; strategy sequencing, slicing, affordability, repricing, interrupts
and recovery decisions belong upstream.

## Install and run explicitly

Use the runtime pins in [`package.json`](package.json) and the
[portable kit guide](../../docs/AGENT_KIT.md). Run these from this service directory:

```sh
npm ci --ignore-scripts
```

Provision credentials privately in `$DHAN_RUNTIME_DIR/.env`, where
`DHAN_RUNTIME_DIR` defaults to `${VOLARB_DATA_DIR:-$HOME/.local/share/volarb}/dhan`.
The blank [`.env.example`](.env.example) is a template, not live configuration.
Preserve existing credentials; a source-local `.env` is not the runtime default.
For a new private directory/template only:

```sh
export DHAN_RUNTIME_DIR="${VOLARB_DATA_DIR:-$HOME/.local/share/volarb}/dhan"
mkdir -p "$DHAN_RUNTIME_DIR"
chmod 700 "$DHAN_RUNTIME_DIR"
# Only if no runtime .env exists; shell noclobber refuses an overwrite:
(umask 077; set -C; cat .env.example > "$DHAN_RUNTIME_DIR/.env")
```

After separate private provisioning, explicit research MCP operation requires
`VOLARB_OBSERVE_ENABLED=true`. Canonical library configuration is independent of
this research-capture flag. Both canonical `DHAN_PROVIDER_COMMANDS_ENABLED` and
legacy `DHAN_EXECUTION_ENABLED` default false; setup enables neither.

```sh
npm start
curl http://127.0.0.1:3000/healthz
```

Health reports `dhan-chatgpt-mcp` version `0.3.0`; it is not broker authentication,
account flatness or trading readiness. Default host is loopback. The optional
[`start-dhan-mcp.sh`](start-dhan-mcp.sh) launcher also starts ngrok and requires a
privately supplied `NGROK_DOMAIN` and runtime `.private/ngrok.yml`. Setup never
runs it. A public research endpoint exposes private account data to its callers;
keep the intended access boundary explicit.

### Container

Build from the **repository root**, not this service directory, because exported
provider modules import the transitional JavaScript execution-contract compatibility layer:

```sh
docker build -f services/dhan-chatgpt-mcp/Dockerfile -t volarb-dhan-mcp .
```

The Dockerfile-specific context whitelist includes only service source/package
locks and the JavaScript compatibility contracts required by the Node provider. It excludes credentials and `execution-testkit`.
The image uses a non-root user, external `/data`, no browser, and disabled mutation
flags. Building it starts no service and performs no broker calls.

## Research interface

`/mcp` remains read-only. Symbol-based tools resolve NIFTY, BANKNIFTY and SENSEX
through the cached Dhan instrument master; original security-ID tools remain for
compatibility. Main symbol tools are `dhan_resolve_underlying`,
`dhan_get_option_expiries_by_symbol`, `dhan_get_option_chain_by_symbol`,
`dhan_analyze_option_surface` and `dhan_get_butterfly_state`.

Surface analytics report forwards, IV/smile metrics, OI/liquidity coverage,
Greeks and an **option-implied risk-neutral distribution**, not a real-world
forecast. Position expiry timestamps are normalized to `YYYY-MM-DD` before chain
requests. The full instrument master is cached for six hours by default.

### Entry-margin preflight is strategy-specific research

- `dhan_calculate_basket_margin({legs})` reports indicative Dhan account-inclusive
  margin facts, not affordability approval.
- `dhan_check_butterfly_margin(...)` checks the four entry prefixes, account state,
  executable-side quote depth/time, funds and an explicit reserve. It returns
  `PASS`, `FAIL` or `UNVERIFIED`; omitted reserve prevents PASS.
- `entrySequence: "PAIRED_HEDGES"` means put wing → put body → call wing → call body.
  Omission retains `"WINGS_FIRST"` for existing callers. A result is sequence-bound;
  always verify `entrySequence`, `sequence` and `stages`. The adopted cash reserve
  is supplied explicitly as `reserveRupees: 1000`.
- Account-inclusive reported totals are conservatively compared with free funds;
  utilised margin is not subtracted and premium is not added again. Pending orders,
  stale/insufficient depth, malformed margin, missing reserve or API failure block
  PASS. Results expire after 30 seconds or an account/price/quantity/sequence change.

These tools submit no orders, do not model exit/recenter transitions and do not
replace upstream controller/liquidity/event/deadline gates. Their policy is not
part of `runtime.port`'s raw `GET_MARGIN`/`GET_BASKET_MARGIN` facts. Published source
features are not evidence that a separately running MCP deployment was refreshed.

### Explicit evidence collection

`workflow-data-cli.mjs --scope account|market|position|hf` writes private read-only
evidence; it does not write the financial ledger. HF collection is a bounded local
process; remote node execution is refused. Convert HF evidence using the RV skill's
[`build_rv_input.py`](../../skill/intraday-realized-volatility-forecast/scripts/build_rv_input.py).

## Authentication and runtime state

Credentials, browser profiles, OAuth tokens, logs and execution state belong in the
external private runtime directory. Never discard execution state to bypass an
ambiguous-order/recovery blocker. The MCP token provider rereads validated tokens;
normal token rotation does not require a source change or restart.

```sh
npm run auth:check
npm run auth:recover
npm run auth:setup
```

These are explicit credential operations, not setup/test effects. Browser recovery
is opt-in and **macOS-only**. `DHAN_PIN_FILE`, `DHAN_BROWSER_EXECUTABLE` and
`DHAN_BROWSER_PORT` are configured privately; no hard-coded office-Mac PIN path is
required. `auth:setup` stores the mobile number through a native local dialog.
Linux/WSL needs a privately supplied valid Web token. OTP/CAPTCHA may require a
human; unattended bypass is not claimed. Recovery validates account identity,
uses private atomic replacement and stops on ambiguity/concurrent edits.

## Compatibility and verification

Detailed legacy tool APIs, sequencing, safeguards and recovery are in the
[compatibility executor guide](../../docs/providers/dhan-legacy-butterfly-executor.md).
Keep its implementation and OAuth endpoint until callers are deliberately migrated.
No generic-engine or production-readiness claim is made for this older strategy
executor. No automatic 15:00 square-off or monitoring is installed.

```sh
npm test
```

Tests use synthetic brokers, credentials and WebSockets; no broker orders or live
authentication are required. Repository publication does not deploy/restart a
service, change credentials or enable execution. Dated host migration, token
verification and prior deployment observations are preserved in the
[September deployment archive](../../archive/deployment/dhan-office-mac/README.md).
