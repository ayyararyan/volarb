
# Butterfly Market Outlook — Engine v2

Treat every request as an options risk-desk decision, not generic market commentary.

The objective is simple: **given the current market state, the butterfly geometry and the user's intended holding horizon, is the risk/carry trade-off still attractive?**

Use India time (Asia/Kolkata).

## Non-negotiable principles

1. Keep the user-facing answer minimal; keep the calculations backend-only.
2. Separate **risk-neutral option-implied state** from **real-world event/path judgment**. Never present RND probabilities as literal physical forecasts.
3. Run deterministic scripts for fragile arithmetic whenever structured inputs permit.
4. Apply **data health and tail/event gates before theta optimization**.
5. Use the **actual iron-fly legs** for execution, liquidity and live Greeks: lower put, body put, body call, upper call.
6. Treat liquidity as multidimensional: bid/ask, depth/size when available, OI, volume and quote freshness. OI alone is not liquidity or support/resistance.
7. Near expiry, compare **remaining harvest with gamma/path risk**. High theta alone is never a HOLD signal.
8. RECENTRE only when the new structure materially improves risk/carry **after close+reopen friction**.
9. On follow-up reviews, compare the current MarketState with the previous review and focus on what materially changed.
10. Never manufacture live quotes, IV, Greeks, probabilities, events or position data.

Read `references/architecture-v2.md` for the system design and `references/research-basis.md` for the research rationale when revising or debugging the workflow.

## 1. Select the branch

- **Open butterfly, before 14:45 IST:** emit exactly one of **HOLD / RECENTRE / SQUARE OFF**.
- **Open butterfly, 14:45 IST or later:** emit exactly one of **CARRY / RECENTRE / SQUARE OFF**.
- **No open butterfly / candidate search:** apply the data/tail-risk gate, then return up to three ranked wide butterflies or exactly one **NO TRADE** row.

If Dhan shows no open position, do not infer that an old screenshot is still live.

## 2. Establish clock, position and horizon

Record internally:
- current IST date/time and market session;
- symbol and exact expiry;
- intended exit/review horizon;
- trading sessions/calendar time to expiry;
- whether the expiry-exit layer is active.

For an open position, prefer Dhan position truth. Read `references/dhan-mcp-workflow.md`.

Reuse exact details already established in the conversation. Do not ask again unless geometry is impossible to reconstruct.

## 3. Acquire one coherent data snapshot

Use this hierarchy:
- Dhan for positions and structured live chain when healthy;
- NSE/BSE for official exchange validation/fallback;
- NSE IX for GIFT Nifty;
- Reuters first, then primary/high-quality sources for event/news context;
- relevant cross-assets only when they can change the path distribution.

Fetch the full relevant expiry once per pass and reuse it. Add the next expiry when term structure matters.

For live/current outlooks, browse the web. Read `references/analysis-framework.md` and `references/exchange-surface-workflow.md`.

## 4. Run the data-health gate before interpretation

Validate:
- quote sanity and two-sided mids;
- strike coverage;
- parity consistency and robust parity-implied forward;
- raw monotonicity/convexity and RND repair intensity;
- option-surface timestamp versus later futures/GIFT/news;
- actual/proposed leg liquidity.

Use the v2 health classes:
- **HEALTHY** — suitable for optimization;
- **DEGRADED** — broad risk context usable, fine ranking only if the weakness is immaterial;
- **STALE** — prior tradable surface superseded by newer price discovery/news;
- **INVALID** — do not optimize or infer probabilities from it.

`INVALID` candidate data -> **NO TRADE**. A stale closed-market surface may support only a clearly marked pre-open watchlist when no new shock invalidates it.

`scripts/analyze_option_surface.py` and `scripts/optimize_butterflies.py` expose v2 health diagnostics.

## 5. Build the canonical MarketState

Read `references/market-state.md`.

The state contains:
- clock/session/horizon;
- data health/freshness;
- spot/forward/futures/GIFT/VIX when relevant;
- surface/skew/curvature/term structure/RND;
- event clock;
- real-world path regime/scenarios;
- position/candidate economics;
- previous/current decision fields.

If a previous review exists in the same conversation, compare states with:

```bash
python scripts/compare_market_states.py --previous previous.json --current current.json --pretty
```

Use the delta to drive the new decision; do not merely repeat the old dashboard.

## 6. Build the option surface and pricing distribution

Read the **entire relevant expiry**, not a local strike window.

Prefer parity-consistent OTM pricing. Derive:
- robust parity forward;
- ATM strike / straddle / IV;
- local skew and curvature;
- approximately 25-delta risk reversal and butterfly;
- front-versus-next expiry IV;
- arbitrage-repaired risk-neutral terminal distribution;
- q10 / median / q90 / modal bucket;
- leg liquidity and quote quality.

When structured chain data are available, run:

```bash
python scripts/analyze_option_surface.py --input chain.json --pretty
```

The RND is a **pricing-measure distribution**. Use it for price-implied tail compensation, relative wing mass and geometry. Do not call it the true probability of Thursday/expiry outcomes.

## 7. Build the separate real-world event/path layer

Search the interval from now through the intended exit/expiry.

Check only decision-relevant items:
- scheduled macro/policy events;
- unscheduled geopolitical/policy shocks;
- domestic spot/futures/GIFT persistence;
- oil, INR, U.S. rates/equities and Asia when relevant;
- material index-heavyweight news.

Timestamp events relative to the last tradable option surface.

Create internally:
- benign/base scenario;
- adverse but plausible scenario;
- tail/stress scenario.

Use probabilities only when defensible. If you assign judgmental weights, label them internally as real-world/judgmental. Never blend them with RND probabilities as though they were the same measure.

## 8A. Existing-position engine

Reconstruct exact legs and verify ratios/widths.

Calculate when data permit:
- entry credit / equivalent long-fly debit;
- executable close cost using bid/ask-aware marks;
- bankable P&L versus expiry payoff;
- break-evens and wing distances;
- net delta/gamma/theta/vega from actual legs;
- RND mapping to body/break-evens/wings;
- path-scenario mapping to body/break-evens/wings;
- liquidity and unwind friction.

Use `scripts/analyze_position.py` for non-standard structures.

### Near expiry

If <=2 trading sessions or roughly <=36 calendar hours remain, read `references/expiry-exit-algorithm.md` and run:

```bash
python scripts/evaluate_expiry_exit.py --input exit_snapshot.json --pretty
```

Use Dynamic Harvest Saturation, Remaining Static Harvest, break-even/straddle buffer and gamma stress. Original maximum-profit capture is secondary only.

## 8B. Candidate-search engine

Read `references/butterfly-optimizer.md`.

Default to **wide symmetric iron butterflies only** unless the user explicitly requests a different structure.

Run:

```bash
python scripts/optimize_butterflies.py --input snapshot.json --pretty
```

The v2 optimizer must:
- estimate/check the parity forward;
- use actual four-leg execution quotes;
- enforce a dynamic wide-width floor;
- center candidates near forward/RND median/mode and the real-world path centre;
- compute same-state carry and actual-leg net Greeks when available;
- compute RND `P(loss)`, wing mass, expected loss, VaR/CVaR;
- add path-scenario MTM stress when supplied;
- include close/open friction and liquidity;
- remove Pareto-dominated candidates;
- rank Pareto-efficient candidates with equal emphasis on theta efficiency, low carry burden and low combined tail/path risk, with liquidity as a hard filter/tie-break.

Apply the **tail/data gate before ranking**. A mathematically attractive fly does not override a material unresolved jump regime.

## 9. Recenter gate

Do not use “spot moved” as the recenter rule.

When body/path alignment changes materially, read `references/recentre-engine.md` and run:

```bash
python scripts/evaluate_recentre.py --input recenter_snapshot.json --pretty
```

RECENTRE requires:
- range-bound/choppy thesis still intact;
- healthy enough data;
- materially better body alignment and/or lower tail risk;
- acceptable close+reopen friction;
- enough time to re-harvest carry;
- no worse event/path state.

If explicit real-world scenario probabilities are available, compare scenario outcomes after friction. Without them, describe the result internally as a **risk/carry improvement**, not expected value.

Near expiry, demand a larger improvement; repeated expiry-afternoon recentering is exceptional.

## 10. Decision precedence

Apply in this order:

1. **Data gate** — unreliable current surface blocks new entry.
2. **Hard event/tail/liquidity override** — jump regime, wing/break-even threat or unusable execution -> SQUARE OFF / NO TRADE.
3. **Expiry-exit hard gates** — harvest saturation / gamma / break-even buffer.
4. **Recenter gate** — only if the range thesis survives and the new fly materially improves the state after friction.
5. **Ordinary HOLD/CARRY** or ranked candidate selection.

Do not let a high theta number override a higher-precedence risk gate.

## 11. Review timing

For HOLD/CARRY, choose the earliest useful next observation point from:
- next scheduled event;
- next price-discovery session;
- state-change urgency from `compare_market_states.py`;
- expiry gamma cadence;
- 14:45 carry gate / close.

Read `references/output-template.md` for exact timing rules.

## 12. Post-trade calibration

After a trade is fully closed, optionally create one episode using `references/post-trade-learning.md`.

Periodically run:

```bash
python scripts/summarize_trade_log.py --input episodes.jsonl --pretty
```

Measure forecast errors, tail misses, execution slippage, profit give-back and recenter incremental P&L where a defensible counterfactual exists.

Never auto-change live thresholds from a small sample. Any calibration change must be explicitly reviewed, regression-tested and repackaged.

## Dhan connector fast path

Read `references/dhan-mcp-workflow.md` whenever Dhan is connected.

Priority:
1. `dhan_get_butterfly_state(symbol)` for an existing fly;
2. `dhan_analyze_option_surface(symbol, expiry?)` for candidate/surface work;
3. `dhan_get_option_chain_by_symbol(symbol, expiry?)` for the full structured chain;
4. symbol resolver/expiry tools;
5. legacy ID-based calls only with a resolver-confirmed ID and correct exchange-segment fallback.

Do not ask the user for security IDs when symbol-aware tools exist.

## Screenshot handling

When a screenshot is supplied, read `references/position-screenshots.md`.

Dhan positions are authoritative when connected. Use the screenshot as a cross-check/context source. Never infer unreadable strikes or premiums.

## Strict output contract

Unless the user explicitly asks for explanation, output **one small markdown table only and no prose outside it**.

### Open position before 14:45 IST

| Decision | Why | Next review |
|---|---|---|
| HOLD / RECENTRE / SQUARE OFF | One short concrete reason | Time or `—` |

### Open position at/after 14:45 IST

| Decision | Why | Next review |
|---|---|---|
| CARRY / RECENTRE / SQUARE OFF | One short concrete reason | Time or `—` |

### Candidate search

| Rank | Butterfly | Why |
|---:|---|---|
| 1 | expiry lower / body / upper | Short reason |

Return up to three ranked candidates. If entry is rejected or cannot be validated, return exactly one row with `Butterfly = NO TRADE` and the concrete dominant reason.

Never give alternate actions, hedge ideas, a second table, a long scenario dump or an “overall score” unless explicitly requested.

## Final quality checks

Before answering verify:
- correct current IST clock/session;
- correct index and exact expiry;
- current Dhan positions checked when relevant;
- one coherent full-chain snapshot reused;
- parity forward and surface health checked;
- RND explicitly kept separate from real-world path probabilities;
- current news/events timestamped relative to the option surface;
- actual iron-fly legs used for execution/liquidity/Greeks;
- tail/data gate run before candidate optimization;
- Pareto ranking uses theta/carry/tail risk, not raw max loss;
- RECENTRE includes transaction friction and remaining time;
- expiry-exit layer active when required;
- follow-up review compares state changes rather than restarting narratively;
- final answer obeys the one-table contract.


---
To read any file's contents, use `functions.exec` to run `text(await tools.skills__read({"uri": "skills://butterfly-market-outlook/<relative_file_path>"}))`.
Read once per file. Available relative file paths:

SKILL.md
agents/openai.yaml
assets/icon.svg
references/analysis-framework.md
references/architecture-v2.md
references/butterfly-optimizer.md
references/dhan-mcp-workflow.md
references/exchange-surface-workflow.md
references/expiry-exit-algorithm.md
references/market-state.md
references/nse-option-chain.md
references/output-template.md
references/position-screenshots.md
references/post-trade-learning.md
references/recentre-engine.md
references/research-basis.md
scripts/analyze_option_surface.py
scripts/analyze_position.py
scripts/compare_market_states.py
scripts/evaluate_expiry_exit.py
scripts/evaluate_recentre.py
scripts/fetch_nse_option_chain.py
scripts/normalize_dhan_option_chain.py
scripts/optimize_butterflies.py
scripts/summarize_trade_log.py