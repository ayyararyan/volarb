# NSE Option-Chain Pass

Use this reference whenever the butterfly is on an NSE-listed index or security. The objective is to read the exchange's own full expiry surface, normalize it, and convert it into decision-relevant butterfly diagnostics without exposing a chain dump to the user.

## 1. Current official feed path

NSE's current option-chain flow is expiry-specific:

1. Prefer a real browser TLS/HTTP2 fingerprint (`curl_cffi` with `impersonate="chrome"`) when available; NSE/Akamai may reject plain HTTP clients even when headers/cookies look correct.
2. Open `https://www.nseindia.com/option-chain` first to establish the browser/Akamai cookie session, then optionally warm the session with `/api/allIndices`.
3. Resolve advertised expiries from:
   - `/api/option-chain-contract-info?symbol=NIFTY`
4. Fetch the chosen expiry from:
   - index: `/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry=DD-MMM-YYYY`
   - equity: `/api/option-chain-v3?type=Equity&symbol=RELIANCE&expiry=DD-MMM-YYYY`
5. Treat `records.data` as the normal strike-row container. Treat the old `option-chain-indices/equities` endpoints as compatibility-only fallbacks because current clients have migrated to v3.

Do **not** hard-code `bm_sv`, `ak_bmsc`, `nseappid`, or other session cookies. They expire. Refresh the session by revisiting `/option-chain` when NSE returns 401/403/429, HTML instead of JSON, or an empty response.

## 2. Preferred deterministic fetcher

For full-surface work, fetch the entire relevant expiry by omitting lower/centre/upper trimming:

```bash
python scripts/fetch_nse_option_chain.py \
  --transport auto \
  --symbol NIFTY \
  --expiry 22-Sep-2026 \
  --pretty --output /tmp/nse-front.json
```

When practical, repeat for the next listed expiry so ATM term structure can be measured.

Then analyze the surface:

```bash
python scripts/analyze_option_surface.py \
  --input /tmp/nse-front.json \
  --input /tmp/nse-next.json \
  --lower 22650 --center 23350 --upper 24050 \
  --debit 120 \
  --pretty
```

`--debit` is optional. Supply the butterfly geometry whenever known so the analyzer maps the risk-neutral distribution directly to the body/wings.

The fetcher:
- prefers `curl_cffi` Chrome impersonation when installed, preserving browser-like TLS/JA3/HTTP2 behavior;
- otherwise tries a dependency-free `urllib` path, which NSE may challenge;
- bootstraps a cookie session from the NSE option-chain page and warms it lightly;
- queries contract-info to validate/resolve the expiry;
- uses `option-chain-v3` as primary;
- refreshes cookies and retries once on bot/session failure;
- uses older index/equity endpoints only as a final compatibility fallback;
- normalizes strike, OI, change in OI, volume, IV, LTP/change, bid/ask and visible sizes;
- preserves the full chain unless explicit strike anchors are supplied.

If `curl_cffi` is unavailable, `auto` falls back to stdlib HTTP; if NSE/Akamai challenges that path, do not loop aggressively. If the execution sandbox has no outbound DNS/HTTP, do **not** waste repeated calls. Try the official NSE option-chain webpage through browsing. If the official surface still cannot be read, mark the surface layer unavailable rather than replacing it with a third-party chain.

## 3. Freshness and validation

Record the NSE timestamp/underlying value when present. Reject or downgrade confidence when:
- the requested expiry is not in NSE's advertised expiry list;
- the JSON contains no usable strike rows;
- the timestamp is stale for the requested live check;
- a leg has stale LTP and unusable bid/ask;
- the response is HTML/challenge text masquerading as HTTP 200.

Also classify the surface relative to later price discovery/news using `exchange-surface-workflow.md`:
- **live**;
- **stale-to-price-discovery**;
- **stale-to-news**.

Never manufacture missing exchange fields.

## 4. Build the full surface first; project locally second

Use the whole relevant expiry to estimate the surface. Do **not** estimate skew, curvature or the terminal distribution from only the three fly strikes.

Construct:
- parity-consistent OTM call-price curve;
- OTM-side IV smile;
- local quadratic smile fit;
- 25-delta put/call points when the grid permits;
- risk-neutral survival curve / terminal probability masses;
- ATM straddle proxy;
- front-versus-next ATM IV when the next expiry is available.

After the full surface is built, project it onto:
- ATM;
- all butterfly legs;
- break-even-adjacent strikes;
- 3-5 strikes outside the wings when local liquidity/crowding needs inspection.

Do not dump the full chain into the final answer.

## 5. Required diagnostics

### ATM/local volatility
- Find strike nearest the forward/underlying.
- Use the parity-consistent OTM-side surface rather than blindly averaging call/put IV.
- Keep meaningful call/put asymmetry when it signals data-quality or microstructure issues.

### Skew
Measure both:
- local IV slope / downside-minus-upside IV at symmetric log-moneyness; and
- 25-delta risk reversal when available.

Richer downside IV indicates stronger downside protection demand / asymmetric pricing, not a deterministic directional signal. Steepening skew matters more when spot/futures are simultaneously moving toward the same threatened wing.

### Curvature
Measure both:
- local quadratic smile curvature / symmetric wing richness; and
- 25-delta butterfly when available.

Treat curvature as a relative-value/distribution-shape input. High wing richness can increase the fly debit and alter theta/carry attractiveness; it is not a standalone forecast.

### Option-implied distribution
Estimate the risk-neutral terminal distribution from the full strike curve after enforcing basic no-arbitrage shape where necessary. Track:
- median / modal region;
- 10th / 90th percentiles;
- lower- and upper-tail probabilities;
- `P(outside wings)`;
- `P(loss)` and expected loss when the fly debit is known.

### ATM straddle proxy
Use liquid ATM call+put marks as an expiry-priced move proxy. Compare it with centre-to-wing and centre-to-break-even distance. Do not call the full-expiry straddle a next-day expected gap when multiple sessions remain.

### OI concentration
Identify only nearby concentrations or migrations that matter to body, break-even or wings. Describe them as concentration/crowding/potential pin context, never hard support/resistance and never proof of buying/writing from OI alone.

### Liquidity
At each butterfly leg inspect bid/ask spread, visible size, volume and OI. A wide/stale wing quote should directly reduce confidence in adjustment-cost assumptions.

## 6. Candidate-search distribution

For new wide-fly screening, use the full normalized NSE chain to build the same consistent surface and risk-neutral distribution before candidate generation.

Compare candidates on:
- `P(loss)`;
- wing-breach probability;
- expected loss;
- severe-loss probability / CVaR;
- theta capture and carry burden;
- execution friction and leg liquidity;
- body alignment with the option-implied median/modal region;
- skew/curvature/term-structure state when it materially changes tail or carry interpretation.

Maximum loss is descriptive, not the tail-risk objective.

## 7. Trader-facing chain output

Normally surface **zero or one chain sentence** only when the user explicitly asks for explanation. In the default skill response, all of this stays behind the strict one-table decision layer.
