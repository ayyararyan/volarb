# Supporting market-analysis framework

This is a data/interpretation reference, not a competing controller or a checklist
to preload. Follow [decision-algorithm.md](decision-algorithm.md) gate-by-gate and
load only the relevant sections. The [personal covenant](https://github.com/ayyararyan/volarb/blob/main/docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md)
overrides generic carry examples: intraday only and flat by 15:00 IST.

Apply these principles within the current controller:

- Build one canonical MarketState and compare it with the previous review when available.
- Run data-health/freshness gates before interpreting option metrics.
- Keep the option-implied RND as a **risk-neutral pricing distribution**, not a physical forecast.
- Build a separate real-world event/path scenario layer for carry/recenter decisions.
- Use actual iron-fly legs for execution, liquidity and Greeks.
- On candidate searches, pass path scenarios into the optimizer when useful; on existing positions, map both RND and path stress to break-evens/wings.
- On follow-ups, prioritize state deltas over repeated narrative.

See `architecture-v2.md` and `market-state.md`.

## Detailed market context

## Purpose

Use this file for the detailed internal research pass behind a butterfly carry analysis. The final answer should remain much shorter than this checklist.

## 1. Establish the clock

Record:
- current IST date/time;
- Indian cash-market status: pre-open / open / post-close / weekend / holiday;
- GIFT Nifty session status and timestamp when relevant;
- intended holding horizon and expiry;
- time remaining to expiry in calendar days and trading sessions.

The usefulness of each signal changes with the clock. During weekends, distinguish Friday's option/futures surface from Saturday/Sunday developments. During pre-open, prioritize GIFT Nifty once open, reopened crude/FX, U.S. close, and early Asia. During the Indian session, prioritize live spot/futures, India VIX, the exchange option surface, and intraday trend.

## 2. Source hierarchy

Prefer primary exchange/official sources whenever practical.

### Connected account / structured market data
- **Dhan** for the user's actual positions, funds/orders/trades when relevant, and the full structured NIFTY/BANKNIFTY/SENSEX option chain with IV, Greeks, OI, volume and top bid/ask. Prefer symbol-aware tools and never ask for a security ID when they are available.

### Exchange / primary market infrastructure
- **NSE India** for NIFTY/BANKNIFTY cash/intraday state, index futures, India VIX and official validation/fallback option-chain data.
- **BSE India** for SENSEX cash/derivatives and official validation/fallback option-chain data.
- **NSE IX** for official GIFT Nifty live/derivatives watch and session status.
- RBI for policy, rates, liquidity and official FX/reference information.
- Federal Reserve / BLS / BEA / ECB / BOJ or equivalent primary sources for major scheduled global events.

If Dhan is unavailable, use NSE/BSE as the surface source. If the user explicitly asks for exchange-only construction, do not substitute Dhan or another broker chain.

### High-quality current reporting
Use Reuters first when available, then AP, Bloomberg, Financial Times, WSJ, CNBC, Business Standard, Economic Times, Moneycontrol or similarly reputable outlets for current developments and market context. For consequential geopolitical claims, corroborate where practical.

### Secondary market pages
Use exchange-linked data vendors, major broker pages, TradingView, Investing.com or similar sources only for non-surface context when primary sources are unavailable or cumbersome. Check timestamps carefully.

Do not rely on SEO prediction pages as the main evidence for a live carry decision. Technical levels are supplementary only.

## 3. Underlying, futures and intraday state

Collect only what is relevant:
- cash index level / last close;
- current session open, high and low from NSE/BSE when trading;
- front NSE/BSE future and basis versus cash when available;
- GIFT Nifty and change from the last meaningful Indian cash/futures reference when trading;
- intraday direction/acceleration when official 1D data expose enough information;
- breadth or sector leadership only when it explains the index move.

For BANKNIFTY, pay extra attention to major banks, rates, RBI/liquidity and financial-sector news. For SENSEX, note concentration in the largest constituents when material.

Basis is price-discovery/context, not a standalone forecast.

## 4. Full option-surface state

Read `dhan-mcp-workflow.md`, `exchange-surface-workflow.md` and, for NSE fallback work, `nse-option-chain.md`.

When Dhan is connected:
- read the **entire relevant Dhan expiry** for NIFTY/BANKNIFTY/SENSEX;
- when useful also read the next expiry for term structure;
- prefer two-sided bid/ask marks and OTM-side parity-consistent pricing;
- use `dhan_analyze_option_surface` when available, otherwise normalize the raw Dhan chain and run `scripts/analyze_option_surface.py`;
- use the Dhan Greeks as additional live state, not as a replacement for payoff/distribution analysis.

When Dhan is unavailable, use the full official NSE/BSE expiry as the fallback surface source.

Required internal diagnostics:
- ATM IV and ATM straddle;
- local smile slope / downside-versus-upside skew;
- 25-delta risk reversal when available;
- smile curvature / symmetric wing richness;
- 25-delta butterfly when available;
- front-versus-next ATM IV;
- option-implied median/mode/10th/90th percentiles;
- lower/upper wing-breach probabilities;
- `P(loss)`, expected loss and CVaR when debit is known;
- OI/volume/bid-ask liquidity at the actual fly legs.

Do not reduce the chain to simplistic rules such as high call OI = resistance or high put OI = support. Near expiry, treat concentrations as potential pin/crowding landmarks that can unwind.

## 5. Volatility state

Check:
- India VIX level and daily change;
- relevant-expiry ATM/local IV from the exchange surface;
- front-versus-next expiry ATM IV;
- skew and curvature;
- ATM straddle expansion/compression;
- whether IV is unusually compressed into a known or newly emerged event.

Interpretation:
- low VIX is not automatically safe; it may be stale or vulnerable to an unpriced jump;
- rising IV with spot moving away from the body widens the distribution while the centre migrates;
- steepening downside skew matters more when futures/GIFT/spot are also moving toward the lower wing;
- high smile curvature is primarily a relative-value/distribution-shape input, not a direction call;
- falling IV can help or hurt a long fly depending on spot and the exact surface; avoid blanket vega claims without checking the legs.

The current workflow consumes the qualified historical HAR/session-VRP forecast
through [session-vrp-gate.md](session-vrp-gate.md), then the separate fresh HF
physical-RV/drift child for eligible intraday work. Do not fit a new historical
model or backtest during current-observation selection. Neither historical HAR
nor session OHLC substitutes for the mandatory fresh HF observation block.

## 6. Cross-asset overnight dashboard

Use only signals relevant to India for the horizon:
- S&P 500 / Nasdaq / Dow close or futures;
- Nikkei, Hang Seng, Kospi and other Asian risk tone once open;
- Brent and WTI;
- DXY and USD/INR;
- U.S. 2Y/10Y yields when rates are material;
- gold when geopolitical stress is material;
- major commodity moves relevant to India.

Look for **confirmation**. One adverse asset is less meaningful than oil + INR weakness + equities down + yields/volatility moving in the same stress direction.

## 7. India-specific inputs

When available and material:
- FII/DII cash flows;
- index futures positioning;
- major domestic policy announcements;
- RBI operations/liquidity;
- heavyweight corporate news;
- sector-specific events relevant to BANKNIFTY or SENSEX.

Do not over-weight one day's FII/DII flow for a next-morning gap without supporting price/futures/volatility confirmation.

## 8. Scheduled event risk

Search the interval from now through the user's intended exit.

Examples:
- RBI/Fed/ECB/BOJ decisions and speeches;
- CPI, WPI, payrolls, GDP, PMI, industrial production;
- major court/policy decisions affecting markets;
- index rebalances;
- large constituent earnings;
- expiry and settlement effects.

State exact times in IST when timing matters internally.

## 9. Geopolitical and unscheduled jump risk

Search specifically for developments occurring after the last meaningful market price discovery.

Examples:
- Middle East attacks affecting energy supply/shipping;
- war escalation/de-escalation;
- sanctions or tariffs;
- unexpected political/security incidents;
- natural disasters affecting markets.

Use the normalized [news-signal child packet](news-signal-integration.md) rather
than rescoring raw articles in this parent reference. For each material event, ask:
1. Did it happen before or after the last NSE/BSE option-surface print?
2. Did it happen before or after the last GIFT/futures print?
3. Have crude/FX/global equities had a chance to react?
4. Is the event confirmed by a reputable source?
5. Does it plausibly alter India via oil, FX, rates, or global risk appetite?

This timing question is critical. A calm Friday IV surface does not price a Saturday shock.

## 10. Freshness classification

Classify the Dhan/exchange option surface internally:

- **live**: current exchange quotes reflect current tradable conditions;
- **stale-to-price-discovery**: GIFT/futures have moved materially after the last option surface;
- **stale-to-news**: material news occurred after the last tradable exchange/GIFT print.

For Monday pre-06:30 IST checks, Friday options and Friday GIFT may both be stale-to-news if weekend events occurred. Once NSE IX reopens, GIFT becomes the first fresh tradable signal; the domestic option surface remains stale until NSE/BSE options reopen and usable quotes populate.

## 11. Technical/location context

Use technical levels as landmarks, not forecasts.

Useful landmarks:
- previous close/high/low;
- recent swing support/resistance;
- gap zones;
- round numbers;
- high open-interest strikes / potential pin zones near expiry;
- VWAP/value area intraday when available.

Map these levels to the butterfly. A level exactly near a break-even is more relevant than a generic technical level far from the fly.

## 12. Option-specific synthesis

Synthesize the exchange surface into the fly rather than narrating the chain:
- body alignment with forward, RND median and modal region;
- lower versus upper wing-breach probability;
- ATM straddle versus body-to-wing / body-to-break-even distance;
- skew steepening/flattening toward the threatened wing;
- curvature and fly debit/carry attractiveness;
- term-structure evidence of near-term event premium/compression;
- OI migration/crowding near body/wings;
- bid/ask spreads, volume and OI at the actual legs;
- near-expiry gamma and unwind risk.

## 13. Scenario construction

Build scenarios from market evidence, then translate into butterfly geometry.

### Benign / centre-holding
What needs to be true:
- GIFT/futures near the prior distribution centre;
- oil/FX orderly;
- no fresh shock;
- exchange surface remains centred and wing probabilities modest.

### Base / ordinary adverse move
Use a plausible gap/drift consistent with the current exchange surface plus cross-asset tone. State internally whether the zone stays inside break-even, inside wing but outside break-even, or reaches a wing.

### Stress / tail
Use a jump scenario motivated by the current risk, not an arbitrary number. Explicitly allow the stress to exceed the option-implied distribution when a new post-surface event makes the surface stale-to-news.

If useful, add an upside stress separately; do not assume downside is always the only risk.

## 14. Carry-state mapping

Supply these diagnostics to the canonical controller; they do not independently
choose the final action or override an earlier terminal gate:
- position geometry;
- option-implied distribution centre and tails;
- skew/curvature/term structure;
- expected move / ATM straddle;
- gap/jump risk;
- time to expiry;
- trend persistence risk;
- adjustment flexibility and leg liquidity;
- futures/GIFT/cross-asset confirmation;
- freshness of the exchange surface.

A wide butterfly can remain manageable in a mildly directional market if its break-evens and wing probabilities remain comfortable. A perfectly centred fly can still be poor carry when a major new event occurred after the last option surface.

## 15. Follow-up deltas

On repeated checks, compare with the previous run:
- spot/futures/GIFT change;
- exchange-surface freshness state;
- RND median/mode shift relative to the body;
- lower/upper wing-breach probability change;
- ATM IV/straddle expansion or compression;
- skew change toward the threatened wing;
- curvature/term-structure change;
- OI migration/unwind around body and wings;
- leg spread/liquidity change;
- Brent / USDINR / global futures / Asia change;
- new headlines;
- time decay / shorter time to expiry;
- distance from centre/break-even.

Lead with the change in risk state rather than repeating the whole dashboard.


## Regime classification

Before overnight carry, explicitly decide whether the market is `CALM_CARRY`, `TRANSITION`, `LATENT_JUMP_RISK`, `ACTIVE_STRESS` or `UNKNOWN`. Do not use VIX alone. Compare recent realized volatility/gaps and tail-gap frequency with implied volatility, skew/term structure and fresh event/news hazard. A low-VIX/high-event-risk mismatch is `LATENT_JUMP_RISK`. See `regime-engine.md`.
