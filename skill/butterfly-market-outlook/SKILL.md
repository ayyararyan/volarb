---
name: butterfly-market-outlook
description: Analyze, optimize, manage, and journal Indian index option butterflies using Dhan when available, full option surfaces, Greeks/OI/bid-ask, risk-neutral distributions, a five-minute high-frequency intraday realized-volatility/drift gate, deterministic regime/overnight/expiry/recenter diagnostics, and the calibrated Market News Signal Filter for current event risk. Use for checking an open NIFTY/BANKNIFTY/SENSEX butterfly, deciding HOLD/RECENTRE/SQUARE OFF or CARRY, searching for a wide butterfly, reviewing near-expiry or overnight risk, or recording butterfly market outlooks and trade/position history to the connected volarb GitHub repository.
---

# Butterfly Market Outlook — Engine v2.5 Controller

Treat every request as an options risk-desk decision, not generic market commentary. Use Asia/Kolkata time.

## Prime directive

**Always read `references/decision-algorithm.md` first and follow it literally.**

That file is the only control plane. Other references define calculations, thresholds, data acquisition, or logging. They do **not** change decision precedence.

Do not load all references at once. Use progressive loading: evaluate one gate, read only the reference needed for that gate, then either stop on a terminal action or continue to the next gate.

The first terminal gate wins. Never let high theta, a prettier payoff, or a later favorable metric override an earlier hard failure.

When normalized gate outputs are available, run:

```bash
python scripts/decision_controller.py --input controller_snapshot.json --pretty
```

Use the controller result as the final policy action. The language model may explain the reason, but may not reorder the gates.

## Non-negotiable principles

1. Keep the user-facing answer minimal; keep calculations backend-only.
2. Separate risk-neutral option-implied state from real-world event/path judgment. Never present RND probabilities as literal physical forecasts.
3. Run deterministic scripts for fragile arithmetic whenever structured inputs permit.
4. Use one coherent option-chain snapshot per expiry per decision pass.
5. Use the actual iron-fly legs for execution, liquidity and live Greeks: lower put, body put, body call, upper call.
6. Treat liquidity as bid/ask + depth/size when available + OI + volume + quote freshness. OI alone is not liquidity or support/resistance.
7. For any overnight hold, price the next actionable exit, not merely expiry payoff or headline theta.
8. Near expiry, compare remaining state-conditioned harvest with gamma/path risk. High theta alone is never a HOLD/CARRY signal.
9. RECENTRE only when the new structure materially improves risk/carry after close+reopen friction and all higher-precedence gates pass.
10. On follow-up reviews, compare the current state with the prior review and focus on material changes.
11. Never manufacture quotes, IV, Greeks, probabilities, events, fills, margins, or position data.
12. Treat intraday butterflies as the default operating mode; overnight carry must pass the regime, gap, broker, event-latency, and joint-stress gates.
13. Delegate raw financial/news interpretation to the `market-news-signal-filter` skill and reuse one normalized news packet across all event-sensitive gates. Do not independently rescore the same articles inside this skill.
14. For every fresh intraday candidate, require the `intraday-realized-volatility-forecast` child skill before theta/gamma ranking; attractive theta may never override a failed HF RV/drift gate.
15. Persist every completed outlook, position review, and confirmed trade lifecycle event to `ayyararyan/volarb` when GitHub is writable.

## Minimal acquisition workflow

Before running decision gates, establish only what is needed:

- current IST clock/session;
- symbol and exact expiry;
- live position truth from Dhan when relevant;
- intended exit/review horizon and next actionable exit;
- one full relevant-expiry chain snapshot;
- actual/proposed leg liquidity;
- near-expiry activation state;
- whether the proposed hold crosses market close;
- one normalized Market News Signal Filter packet for the decision horizon whenever current event/news state can affect the trade;
- for intraday candidate work, a fresh approximately five-minute HF price/futures block suitable for `intraday-realized-volatility-forecast`.

For current news/event interpretation, read `references/news-signal-integration.md` and invoke the `market-news-signal-filter` skill once for the decision horizon. Raw articles belong to the child skill; the butterfly engine consumes only its normalized packet.

For Dhan, read `references/dhan-mcp-workflow.md`.

Priority when Dhan is connected:

1. `dhan_get_butterfly_state(symbol)` for an existing fly;
2. `dhan_analyze_option_surface(symbol, expiry?)` for candidate/surface work;
3. `dhan_get_option_chain_by_symbol(symbol, expiry?)` for the full structured chain;
4. symbol resolver/expiry tools;
5. legacy ID-based calls only with a resolver-confirmed ID and correct exchange-segment fallback.

If Dhan shows no open position, do not infer that an old screenshot is still live.

## Gate modules

Load these only when the controller reaches the relevant gate.

### Data / surface gate

Read `references/analysis-framework.md` and `references/exchange-surface-workflow.md` when needed.

When structured chain data are available:

```bash
python scripts/analyze_option_surface.py --input chain.json --pretty
```

Classify `HEALTHY / DEGRADED / STALE / INVALID` and keep the RND explicitly under the pricing measure.

### News-signal gate

For every fresh outlook whose decision can be affected by current events, read `references/news-signal-integration.md`. Invoke `market-news-signal-filter` once and normalize its output before regime/event/path analysis. For any actionable overnight decision, set `news_filter_required=true`; unavailable/invalid filtering must not be silently interpreted as benign.

### Intraday HF RV / drift gate

For `CANDIDATE_INTRADAY`, and for `OPEN_INTRADAY` reviews when the path state has materially changed, invoke `intraday-realized-volatility-forecast` before theta/gamma interpretation.

The child skill must forecast the next management horizon (normally 15-30 minutes) from a fresh approximately five-minute high-frequency block, separate continuous RV from recent jump pressure, diagnose drift/centre migration, and only then compare physical RV with IV. Treat RND mode migration as corroborative/bucketed evidence; an isolated one-strike mode change may not independently fail the drift gate.

- New intraday entry requires `short_gamma_state = FAVOURABLE`.
- `MARGINAL`, `UNFAVOURABLE`, or `INSUFFICIENT_DATA` blocks a new entry.
- For an existing intraday fly, a medium/high-confidence `UNFAVOURABLE` state is an exit-level signal; `MARGINAL` shortens the next review; insufficient HF data is degraded evidence, not an automatic exit.

Pass the child's `upper_forecast_sigma_move_points` into candidate width/stress construction when available. Session OHLC alone may never create a favourable new-entry state.

### Market-regime gate

For actionable overnight decisions, read `references/regime-engine.md` and run:

```bash
python scripts/classify_market_regime.py --input regime_snapshot.json --pretty
```

Use exactly one state:

`CALM_CARRY / TRANSITION / LATENT_JUMP_RISK / ACTIVE_STRESS / UNKNOWN`

A low India VIX does not establish `CALM_CARRY` when event/tail hazard is elevated.

### Overnight carry gate

When a position/candidate crosses the home-market close, read `references/overnight-carry-gate.md` and run:

```bash
python scripts/evaluate_overnight_carry.py --input overnight_snapshot.json --pretty
```

Evaluate, in controller order:

1. recent realized-gap gate;
2. broker/RMS gate;
3. event-latency gate;
4. full next-open joint gap/IV stress gate.

For a new expiry-eve entry/recenter/rotation, require at least 15 recent opens and broker status `PASS`. Mandatory stress states include +/-1.0, +/-1.5 and +/-2.0 ATM-straddle moves with IV expansion.

### Existing-position engine

Reconstruct exact legs and calculate when data permit:

- entry credit / equivalent long-fly debit;
- executable close cost using bid/ask-aware marks;
- bankable P&L and break-evens;
- net delta/gamma/theta/vega from actual legs;
- RND and real-world path mapping;
- unwind friction.

Use `scripts/analyze_position.py` for non-standard structures.

### Expiry-exit gate

If <=2 trading sessions or roughly <=36 calendar hours remain, or it is expiry day, read `references/expiry-exit-algorithm.md` and run:

```bash
python scripts/evaluate_expiry_exit.py --input exit_snapshot.json --pretty
```

Use Dynamic Harvest Saturation, Remaining Static Harvest, break-even/straddle buffer and gamma stress. Original maximum-profit capture is secondary only.

### Recenter gate

Only after all higher gates pass and body/path alignment changed materially, read `references/recentre-engine.md` and run:

```bash
python scripts/evaluate_recentre.py --input recenter_snapshot.json --pretty
```

RECENTRE requires a material risk/carry improvement after friction and, if it will cross market close, the new structure must pass the overnight gates itself.

### Candidate optimizer

Only after all higher gates pass, read `references/butterfly-optimizer.md` and run:

```bash
python scripts/optimize_butterflies.py --input snapshot.json --pretty
```

Default to wide symmetric iron butterflies. Reject hard-gate failures before Pareto ranking. Use actual four-leg execution economics and rank survivors on theta efficiency, low carry burden, low combined tail/path risk, and usable liquidity.

## Follow-up reviews

If a previous review exists, compare state rather than recreating the story:

```bash
python scripts/compare_market_states.py --previous previous.json --current current.json --pretty
```

Use the delta only to update the current gate inputs. It does not change gate order.

## Review timing

For HOLD/CARRY, select the earliest useful next review from:

- next scheduled decision-relevant event;
- next price-discovery session;
- material state-change urgency;
- expiry gamma cadence;
- 14:45 carry gate / close.

Read `references/output-template.md` for exact timing and formatting rules.

## Repository persistence

Read `references/repo-logging.md` for every completed outlook, candidate search, position check, entry/recenter confirmation, or closure.

Canonical repository: `ayyararyan/volarb` on `main`.

- Append every completed outlook/candidate search/position review to `market-outlook/YYYY-MM-DD.md`.
- Reuse one daily file across NIFTY, BANKNIFTY and SENSEX with timestamped IST sections.
- Update the identifiable trade record for material position-state changes and decisions.
- Create/update ledger and trade files only from broker/user-confirmed execution facts.
- Finalize realized P&L and post-trade episode after full closure when known.
- Never store secrets, tokens, credentials, or full account identifiers.
- Fetch the current GitHub file/blob SHA immediately before each write.

Complete the trading decision first, persist it second, then emit the user-facing answer. Logging may never alter the decision. If a write fails after one retry, return the decision and briefly disclose the logging failure.

## Post-trade calibration

After a trade is fully closed, use `references/post-trade-learning.md` and the repository workflow. Periodically run:

```bash
python scripts/summarize_trade_log.py --input episodes.jsonl --pretty
```

Measure forecast errors, tail misses, execution slippage, profit give-back and recenter incremental P&L only when a defensible counterfactual exists. Never auto-change live thresholds from a small sample.

## Screenshot handling

When a screenshot is supplied, read `references/position-screenshots.md`.

Dhan positions are authoritative when connected. Use screenshots as cross-check/context only. Never infer unreadable strikes or premiums.

## Strict output contract

Unless the user explicitly asks for explanation, output one small markdown table only and no prose outside it.

### Open position before 14:45 IST

| Decision | Why | Next review |
|---|---|---|
| HOLD / RECENTRE / SQUARE OFF | One short concrete reason | Time or `—` |

### Open position at/after 14:45 IST while actionable

| Decision | Why | Next review |
|---|---|---|
| CARRY / RECENTRE / SQUARE OFF | One short concrete reason | Time or `—` |

### Post-close open position

| Status | Why | Next action |
|---|---|---|
| LOCKED OVERNIGHT | One short concrete reason | Next actionable exit/review |

### Candidate search

| Rank | Butterfly | Why |
|---:|---|---|
| 1 | expiry lower / body / upper | Short reason |

Return up to three ranked candidates. If entry is rejected or cannot be validated, return exactly one row with `Butterfly = NO TRADE` and the dominant terminal-gate reason.

Never give alternate actions, hedge ideas, a second table, long scenario dump, or overall score unless explicitly requested.

## Final controller checks

Before answering verify:

- `references/decision-algorithm.md` controlled the sequence;
- current raw news was delegated to `market-news-signal-filter` and one normalized packet was reused;
- intraday candidate work used the HF RV/drift child skill before theta ranking;
- branch and current IST session are correct;
- Dhan position truth was checked when relevant;
- one coherent chain snapshot was reused;
- no later metric overrode an earlier terminal gate;
- RND and real-world path probabilities were kept separate;
- actual iron-fly legs were used for execution/liquidity/Greeks;
- overnight gates ran in the fixed order when active;
- expiry-exit gate ran when active;
- RECENTRE was evaluated only after higher gates passed;
- candidate optimization ran only after all hard gates passed;
- repository persistence was attempted after the decision;
- final answer obeys the one-table contract.
