# Engine v2.2 data-health overlay

Before using any surface for a decision, classify it as `HEALTHY`, `DEGRADED`, `STALE`, or `INVALID`. Diagnostics must include parity-forward dispersion, raw monotonicity/convexity violations, RND repair fraction, local strike coverage, quote sanity and freshness relative to later price discovery/news. A heavily repaired RND is not a high-confidence probability surface merely because the algorithm produced a smooth density.

Keep RND probabilities under the pricing measure. Real-world event/path scenarios are a separate layer.

# Exchange Surface and Price-Discovery Workflow

Use this reference for every live butterfly decision on NIFTY, BANKNIFTY or SENSEX. It is a backend research layer only. Do not expand the user-facing output because of this workflow.

## Objective

Convert the connected Dhan option chain plus official exchange price-discovery/validation sources into a compact state estimate for the butterfly:

- where the option-implied terminal distribution is centred;
- how wide and asymmetric that distribution is;
- whether downside/upside skew is steepening toward a threatened wing;
- whether smile curvature makes the fly unusually rich/cheap relative to its body;
- whether front-expiry volatility is carrying event premium relative to the next expiry;
- whether spot, domestic futures and GIFT Nifty are confirming or contradicting one another;
- whether the latest option surface predates material overnight/weekend news.

The output layer remains the strict one-table format in `output-template.md`.

## 1. Surface source map

When the connected **Dhan** app is available, it is the primary structured option-surface source for NIFTY, BANKNIFTY and SENSEX. Read `dhan-mcp-workflow.md` and prefer the symbol-aware tools. Dhan exposes the full chain with IV, Greeks, OI, volume and top bid/ask in one payload.

- Read the **entire relevant expiry**, not only a local window, when constructing the surface.
- When useful also read the **next listed expiry** to measure ATM term structure.
- Prefer valid two-sided bid/ask midpoints over LTP for marks. Use LTP only when bid/ask is unavailable and the quote is plausibly fresh.
- Keep OI, change in OI, volume, IV, Greeks, best bid/ask and displayed size for each strike when available.
- Reuse one fresh Dhan snapshot during a decision pass instead of repeatedly refetching the same expiry.

Official exchange pages are the validation/fallback layer:

### NIFTY / BANKNIFTY

Use NSE India to validate index/futures/VIX state, exchange status and suspicious chain discrepancies. If Dhan is unavailable, the NSE option chain becomes the primary surface source. When code execution has outbound network access, fetch the full expiry with `scripts/fetch_nse_option_chain.py` without strike trimming, then run `scripts/analyze_option_surface.py`.

### SENSEX

Use BSE India to validate the cash/derivatives reference and as the fallback option-chain source when Dhan is unavailable.

The BSE table exposes the same fields needed for normalization: strike, expiry, call/put OI, change in OI, volume, IV, LTP, best bid/ask and displayed bid/ask quantity. Read the complete relevant expiry table and normalize it to the schema used by the surface analyzer:

```json
{
  "provider": "BSE India",
  "symbol": "SENSEX",
  "expiry": "YYYY-MM-DD or exchange label",
  "underlying_value": 0.0,
  "chain": [
    {
      "strike": 0.0,
      "call": {"oi": 0, "change_oi": 0, "volume": 0, "iv": 0.0, "ltp": 0.0, "bid": 0.0, "ask": 0.0, "bid_qty": 0, "ask_qty": 0},
      "put":  {"oi": 0, "change_oi": 0, "volume": 0, "iv": 0.0, "ltp": 0.0, "bid": 0.0, "ask": 0.0, "bid_qty": 0, "ask_qty": 0}
    }
  ]
}
```

If the user explicitly requests exchange-only construction, honor that request and use NSE/BSE only. Otherwise, a healthy connected Dhan surface is the preferred structured live surface.

## 2. Surface construction

For each expiry:

1. Establish spot and a forward estimate. Prefer a parity-consistent forward from the full Dhan chain and cross-check it against the corresponding exchange future when available; otherwise use spot as a temporary approximation and reduce confidence.
2. Build one parity-consistent call-price curve across strikes:
   - below the forward, prefer liquid OTM puts converted to calls by put-call parity;
   - above the forward, prefer liquid OTM calls;
   - near ATM, use the more liquid side or a parity-consistent blend;
   - reject obviously stale zero quotes and unusable crossed markets.
3. Build the IV smile from the same OTM-side convention.
4. Use smoothing only to remove obvious microstructure violations. Never smooth away a genuine skew feature merely because it is inconvenient.
5. Estimate the risk-neutral terminal distribution from call-spread slopes or Breeden-Litzenberger second differences after enforcing monotonicity/convexity where required.
6. Preserve lower- and upper-tail mass. Do not renormalize only the centre of the chain.

Use `scripts/analyze_option_surface.py` whenever structured chain data are available.

## 3. Required surface diagnostics

Keep these diagnostics internal unless the user explicitly asks for them.

### Distribution location

- option-implied median;
- modal probability bucket;
- 10th and 90th percentiles;
- probability below/above important butterfly levels;
- probability outside the wings;
- probability of expiry loss when the debit is known.

Map the distribution location to the butterfly body. A centred fly is one whose body is reasonably close to the current forward/median/modal region, not merely one whose body equals the last cash print.

### Skew

Measure downside-versus-upside IV asymmetry using both:

- a local quadratic fit in log-moneyness; and
- 25-delta risk reversal when the strike grid permits it.

Interpretation:

- richer downside IV is evidence of downside protection demand / asymmetric option pricing, not a deterministic bearish forecast;
- **steepening downside skew while spot/futures move toward the lower wing** raises lower-tail concern;
- flattening skew with stable price can reduce asymmetric tail concern;
- apply the symmetric logic to upside stress when upside skew is the threatened side.

### Curvature / butterfly richness

Measure smile curvature using a quadratic fit and 25-delta butterfly when available.

Curvature is primarily a **relative-value and distribution-shape** input, not a directional signal. High wing richness relative to ATM can make a long butterfly more expensive and can change its carry attractiveness even if the centre is well aligned. Use the option-implied density and actual fly debit to decide whether that curvature is useful or costly.

### Term structure

When the next expiry is available, compare relevant-expiry ATM IV with next-expiry ATM IV.

- front IV materially above next IV can indicate event/expiry premium or acute near-term uncertainty;
- front IV materially below next IV can indicate compressed near-term pricing, which is not automatically safe if a fresh unpriced catalyst exists;
- never infer event safety from low front IV when news occurred after the last option print.

### ATM straddle

Use the exchange ATM call+put mark as an expiry-priced move proxy. Compare it with:

- body-to-wing distance;
- body-to-break-even distance;
- the intended holding horizon.

Do not call the full-expiry straddle a one-day expected move when more than one session remains.

## 4. Butterfly mapping

For an open fly, calculate internally:

- body minus option-implied median / modal region;
- lower-wing probability and upper-wing probability separately;
- total probability outside wings;
- probability of expiry loss and expected loss when debit is known;
- how much a 0.5%, 1.0% and 1.5% spot move shifts the fly relative to the distribution;
- whether skew is steepening toward the threatened wing;
- whether IV expansion is widening the distribution faster than theta is helping;
- whether current leg bid/ask spreads make recentering realistically executable.

For candidate search, feed the same full-surface state into the existing wide-fly optimizer. The full surface replaces ad-hoc local-IV assumptions; it does not change the front-end ranking table.

## 5. Domestic price discovery

Use official exchange sources where practical.

### NSE cash / intraday index state

For NIFTY and BANKNIFTY, read the NSE live index page and capture only decision-relevant intraday information:

- last / previous close;
- session open, high and low;
- current percentage move;
- intraday direction/acceleration when the page exposes enough 1D information;
- India VIX from NSE.

Do not import historical-data models into this workflow unless the user later enables them.

### NSE futures

Read the relevant near-month NSE index futures contract and capture:

- last price and timestamp;
- basis versus cash;
- intraday change;
- volume/OI when available.

Interpret basis as price-discovery/context, not as a standalone forecast.

### GIFT Nifty / NSE IX

Use the official NSE IX derivatives watch / live watch for GIFT Nifty.

Capture:

- current near-month GIFT Nifty future;
- change and percentage change;
- session open/high/low;
- timestamp and trading-session status;
- volume when available.

Current NSE IX trading structure includes a morning session beginning at 06:30 IST and a second session extending into the following night. Always verify the displayed timestamp/session before treating a print as current.

## 6. Freshness state machine

This is mandatory for overnight/weekend decisions.

### State A - Indian market open

Use the live Dhan full chain when connected, plus NSE/BSE cash/futures/reference checks. Rebuild the relevant-expiry surface on each meaningful re-check, but reuse the same fresh Dhan snapshot within one pass.

### State B - Indian close, GIFT still trading

The Dhan/NSE/BSE domestic option surface is frozen at the Indian close, while GIFT may continue to discover price. Keep the last surface but shift the opening/path centre using GIFT and cross-asset moves. Mark the surface internally as **stale-to-price-discovery** if the GIFT move is material.

### State C - GIFT closed, no material new event

Retain the last tradable surface and last GIFT print. Do not pretend anything is live.

### State D - material event after the last tradable print

Mark the option surface and GIFT print internally as **stale-to-news**. Do not use low VIX, compressed IV or the previous close as evidence that the new event is priced.

For a Monday-morning check before 06:30 IST, weekend news may exist while both Indian options and GIFT are closed. In that state, jump risk can dominate the decision even if Friday's surface looked benign.

### State E - GIFT reopens before NSE cash/options

GIFT becomes the first fresh tradable price-discovery signal. Use it to update gap/centre risk, but keep the Friday domestic Dhan/NSE/BSE surface labelled stale until the option market refreshes.

### State F - NSE/BSE option market reopens

After quotes populate and spreads become usable, rebuild the full Dhan surface when connected (or NSE/BSE fallback surface). Prefer a second check a few minutes after the open rather than treating the first isolated option ticks as a stable surface.

## 7. Overnight external overlay

The option-surface layer remains Dhan/exchange market data, while overnight path/jump risk may use reputable online sources.

Use Reuters first when available, then AP/Bloomberg/FT/WSJ or primary official statements for confirmation. Check:

- Brent / WTI;
- USD/INR when trading and the latest reliable close otherwise;
- U.S. equities / futures;
- U.S. 2Y and 10Y yields when rates are material;
- major Asian markets once open;
- geopolitical developments capable of moving oil, FX or global risk appetite.

Ask for every material headline: **did this happen before or after the latest domestic option surface / GIFT print?**

## 8. Decision integration

Do not create a new user-facing score. Fold the surface state into the existing action logic.

Surface evidence that can strengthen **HOLD/CARRY**:

- body remains close to forward/median/modal region;
- wing-breach probabilities remain modest and balanced;
- skew is stable rather than steepening toward a threatened wing;
- relevant-expiry IV/straddle is not expanding materially versus the geometry;
- futures/GIFT/cross-assets do not show persistent directional confirmation;
- recentering liquidity remains usable.

Surface evidence that can strengthen **RECENTRE**:

- distribution centre/forward has migrated materially away from the body;
- tail risk remains manageable inside the existing wings;
- skew/term structure do not indicate an exceptional jump regime;
- leg liquidity makes the adjustment executable.

Surface evidence that can strengthen **SQUARE OFF / NO TRADE**:

- a credible post-surface event makes the last exchange surface stale-to-news;
- GIFT/futures reprice toward or through a break-even/wing;
- wing-breach probability or expected loss rises materially;
- skew steepens sharply toward the threatened wing while spot confirms;
- front IV/straddle expands enough that ordinary noise can consume the geometry;
- leg spreads/quotes become too poor to rely on cheap recentering.

These diagnostics remain backend-only. The final answer still uses `output-template.md` exactly.
