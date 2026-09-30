# Dhan MCP Workflow

Use this reference whenever the connected **Dhan** app is available. Dhan is the preferred live source for the user's actual positions and for the full option-chain snapshot because it exposes IV, Greeks, OI, volume and top bid/ask in one structured response. Official NSE/BSE pages remain useful for validation, market-status checks and fallback.

## 1. Tool priority

Prefer the highest-level available Dhan tool:

1. `dhan_get_butterfly_state(symbol)` — preferred for an existing NIFTY/BANKNIFTY/SENSEX position. It reconstructs the carried iron butterfly when possible, fetches the correct expiry surface and returns live leg state, net Greeks and surface analytics.
2. `dhan_analyze_option_surface(symbol, expiry?)` — preferred for candidate search or a surface-only check.
3. `dhan_get_option_chain_by_symbol(symbol, expiry?)` — full normalized chain without asking the user for a security ID.
4. `dhan_get_option_expiries_by_symbol(symbol)` and `dhan_resolve_underlying(symbol)` — use when expiry selection/resolution must be explicit.
5. Legacy fallback: `dhan_get_positions`, `dhan_get_option_expiries`, `dhan_get_option_chain`, `dhan_get_market_quote`.

Never ask the user for a Dhan security ID when the symbol-aware tools are available.

## 2. Existing-position fast path

For an open butterfly:

1. Call `dhan_get_butterfly_state` for the requested index.
2. Use Dhan positions as the authoritative position source: expiry, option type, strikes, quantities, entry averages and current unrealized P&L.
3. Verify the leg ratio and widths. If the high-level tool cannot recognize the structure, use `dhan_get_positions` and reconstruct it manually.
4. Use the returned full-surface diagnostics and live leg state as the option layer for the decision.
5. If the position is a standard symmetric iron butterfly, its expiry payoff is equivalent to a long call butterfly with:
   - `entry credit = short CE premium + short PE premium - long put premium - long call premium`;
   - `equivalent long-fly debit = wing width - entry credit`;
   - lower/upper break-even = `center ± entry credit`.
6. For broken-wing, ratio or non-standard structures, use `scripts/analyze_position.py` rather than forcing the symmetric shortcut.

Screenshots become a fallback/cross-check, not the default position source, when Dhan is connected.

## 3. Surface-only / candidate path

For candidate search:

1. Call `dhan_analyze_option_surface(symbol)` for the nearest active expiry unless the user specifies another expiry.
2. When term structure matters, obtain the next expiry as well.
3. If deterministic optimizer input is needed, call `dhan_get_option_chain_by_symbol`, save the structured payload, normalize it if needed with `scripts/normalize_dhan_option_chain.py`, then run `scripts/analyze_option_surface.py` and `scripts/optimize_butterflies.py`.
4. Keep the **entire expiry**. Do not trim the chain to a handful of strikes before estimating skew, curvature or the risk-neutral distribution.

## 3A. Engine v2 connector-failure fallback

If a symbol-aware SENSEX surface call fails with a connector-level `Invalid SecurityId` even though `dhan_resolve_underlying("SENSEX")` succeeds, do not abandon Dhan immediately. Retry the **legacy** expiry/chain route using only the resolver-confirmed security ID. In the current connector implementation, SENSEX may require the `BSE_FNO` segment on this legacy route even when the resolver metadata labels the underlying as `IDX_I`. Treat this as a connector compatibility fallback, not as a universal exchange rule.

After fallback:
- run the same parity-forward and data-health diagnostics as any other chain;
- cross-check the SENSEX reference with BSE;
- never guess an ID; use only the resolver result;
- if the fallback also fails, use BSE official data and mark Dhan surface availability degraded.


## 3B. High-frequency intraday RV acquisition

The ordinary Dhan option-surface and market-quote tools are snapshot interfaces. A single quote or session OHLC is **not** a five-minute HF block.

For `CANDIDATE_INTRADAY`, the v2.5 controller requires a genuine fresh observation block for `intraday-realized-volatility-forecast`:

- prefer a supported streaming/polling source for liquid index futures at roughly 1-2 second cadence;
- the child skill will aggregate to roughly 5-second efficient-price observations;
- if the available connector cannot provide enough observations across about five minutes, return the RV gate as insufficient and block a new entry rather than substituting whole-session OHLC;
- continue to use Dhan for position truth and option-surface/IV/forward state.

Do not repeatedly hammer the option-chain endpoint for HF sampling. The HF block is a futures/price feed problem; the option surface needs only start/end or decision-time snapshots.

## 3C. Mandatory entry affordability

Use `dhan_check_butterfly_margin(symbol, expiry, lower, center, upper, lots, reserveRupees?, reservePercent?)` for each exact finalist. It resolves contract IDs/lot sizes and checks account, executable quotes and all wings-first margin prefixes. Only fresh PASS is actionable for affordability; it is not strategy-risk approval or an execution guarantee. `dhan_calculate_basket_margin(legs)` exposes the raw indicative combined requirement but never approves affordability by itself. Both tools are read-only and include current positions/orders. Read `margin-affordability.md` for integration, conservative comparison semantics and recenter limitations.

If only old tools exist, margin is UNVERIFIED. Do not substitute payoff maximum loss or sum standalone short-leg margins. Use verified Dhan basket UI evidence as a disclosed manual fallback, otherwise block entry.

## 4. Legacy v0.1 fallback

If only the original Dhan tools exist:

- NIFTY underlying security ID `13` on `IDX_I` is documented by Dhan and may be used directly.
- For BANKNIFTY or SENSEX, do **not** guess a security ID. Use the Dhan instrument master / symbol-resolver upgrade or fall back to official exchange data.
- Get the active expiry list before requesting a chain.
- Convert the raw Dhan response with `scripts/normalize_dhan_option_chain.py` before running the Python surface analyzer.

## 5. Dhan chain normalization

Dhan raw option-chain fields map as follows:

- `data.last_price` -> `underlying_value`
- strike key -> `strike`
- `ce` / `pe` -> `call` / `put`
- `implied_volatility` -> `iv`
- `last_price` -> `ltp`
- `top_bid_price` / `top_ask_price` -> `bid` / `ask`
- top bid/ask quantities -> `bid_qty` / `ask_qty`
- `oi` and `previous_oi` -> current OI and `change_oi = oi - previous_oi`
- `volume` -> `volume`
- Dhan `greeks` -> per-leg delta/theta/gamma/vega

Ignore zero/stale deep-wing quotes when constructing parity curves. Prefer two-sided bid/ask mids to LTP.

## 6. Surface diagnostics to use

The Dhan-backed surface layer should provide or derive:

- spot and parity-consistent forward estimate;
- ATM strike, ATM IV and ATM straddle;
- local skew and smile curvature;
- approximately 25-delta put/call IV, 25-delta risk reversal and butterfly;
- risk-neutral terminal distribution, including q10/median/q90 and modal bucket;
- lower/upper wing probabilities and `P(loss)` when the fly debit is known;
- OI/change-OI and volume concentrations;
- bid/ask spread and depth at the actual legs;
- net position Greeks when all open legs can be matched to the chain.

Treat Dhan-provided Greeks as snapshot model outputs, not immutable truths. Reconcile them with the position geometry and surface rather than using one Greek in isolation.

## 7. Freshness

Dhan option-chain data are live only while the relevant Indian derivatives market is trading and quotes are populated. After close, retain the last tradable Dhan surface but apply the same stale-to-price-discovery / stale-to-news rules used elsewhere in the skill.

The Dhan option-chain endpoint has a request-frequency constraint. Avoid repeated duplicate calls within a few seconds. Reuse a fresh chain snapshot during one decision pass instead of refetching it for every sub-calculation.

## 8. Validation hierarchy

When Dhan is connected:

- **Position/account truth:** Dhan first.
- **Structured live option surface:** Dhan first.
- **Exchange status, official reference and anomaly check:** NSE/BSE first.
- **GIFT Nifty:** NSE IX.
- **Overnight news:** delegate raw-news interpretation to `market-news-signal-filter` via `news-signal-integration.md`; use cross-assets as live confirmation.

If Dhan and an official exchange page materially disagree, check timestamps and market status before trusting either. Do not average contradictory stale/live values.


## Expiry normalization — 2026-09-30

Dhan position rows report `drvExpiryDate` as `YYYY-MM-DD HH:MM:SS`. The option-chain endpoint requires a bare `YYYY-MM-DD` and otherwise rejects the call with `Invalid Expiry Date`. `dhan_get_butterfly_state` now normalizes the expiry before fetching the surface (`normalizeExpiryDate` in `surface-analytics.mjs`). Earlier reviews that fell back to explicit chain calls because of this error are historical; the tool is again the preferred first call for an open fly.

## HF sampler placement — 2026-09-30

`node src/workflow-data-cli.mjs --scope hf` is office-Mac-only by design and must be started as a local process on that machine. Launching it through a remote OpenClaw node exec was refused on 2026-09-30 with a shared-state ownership conflict before any sample was taken. Treat any sampler failure as `INSUFFICIENT_DATA` for the HF gate; do not substitute session OHLC.
