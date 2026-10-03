# Daily Operating Algorithm — one butterfly, one lot, intraday

Operational rules updated 2026-09-30; source consistency reviewed 2026-10-03. This is the single page to follow on a trading day. It sits on top of the
[personal covenant](PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md) (intraday only, flat by 15:00 IST) and the
engine's [decision algorithm](../skill/butterfly-market-outlook/references/decision-algorithm.md), which
controls gate order. Nothing here loosens either. Dhandho researches and records; Aryan executes.

## Why the strategy exists

The strategy seeks compensation for short-volatility exposure when option-implied variance exceeds a
physical realized-variance forecast over a comparable horizon. This is a variance-risk-premium screen,
not a sufficient or necessary pathwise profit condition for a finite-width butterfly: location, skew,
path, executable prices and costs also matter. The adopted entry rule nevertheless requires a
FAVOURABLE session VRP screen before selecting strikes.

## The day, in order

| # | When (IST) | Step | Who | Output |
|---|---|---|---|---|
| 0 | before 09:30 | **Session VRP screen.** Read the local IV/HAR dashboard. Run `evaluate_session_vrp.py --url http://127.0.0.1:8770/api/state`. | Dhandho | `FAVOURABLE` / `UNFAVOURABLE` / `UNKNOWN` |
| 1 | 09:30 | If not `FAVOURABLE`: the day is closed for new entries. Journal the blocked check. Stop. | both | NO TRADE |
| 2 | 09:45–09:55 | **Candidate search** (only if step 0 passed). Fresh Dhan positions and orders, one full chain, data health, five-minute HF block via the local sampler, one news packet, RV/drift gate, hard-risk gate, optimizer, margin preflight with ₹1,000 reserve. | Dhandho | one table, up to three candidates or NO TRADE |
| 3 | — | **Honour the table.** NO TRADE means no trade. A blocked gate is NO TRADE. | Aryan | — |
| 4 | after fills | **Confirm entry.** Tell Dhandho it filled. Reconcile fills from Dhan and record them first through the local shared-writer accounting store; sanitized trade and journal records follow without delaying risk management. | both | trade ID |
| 5 | every 30 min | **Review.** Returns HOLD, SQUARE OFF or (rarely) RECENTRE. Cadence drops to 15–20 min when the RV state is MARGINAL or a break-even is within half an ATM straddle. Each review states session loss against the ₹1,000 budget. | Dhandho | one row |
| 6 | — | **No self-directed rolls.** RECENTRE is only valid as a controller output with verified transition margin; today the preflight is entry-only, so RECENTRE is effectively unavailable. If the body is wrong, the answer is SQUARE OFF. | Aryan | — |
| 7 | on trigger | **SQUARE OFF** when the review says so, when session loss reaches ₹1,000, or at 15:00 IST at the latest. | Aryan | flat |
| 8 | after flat | **No re-entry** unless a fresh step 2 passes every gate again. Re-entry inherits the day's loss so far. | both | — |
| 9 | after flat | **Closure record.** Fills, gross P&L, post-trade diagnosis, journal, publish to `main`. | Dhandho | commit hash |

## Terminal gates, in the order the controller checks them

The controller (`scripts/decision_controller.py`) stops at the first failing gate. Later metrics never
override an earlier failure.

1. `DATA_HEALTH` — chain INVALID/STALE → NO TRADE (candidates).
2. `POST_CLOSE` — market shut → LOCKED_OVERNIGHT, no fresh executable decision.
3. `LOSS_BUDGET` — session realized + bankable loss ≥ ₹1,000 → SQUARE OFF / NO TRADE. The generic controller warns on missing inputs; the operational caller must supply and validate them before any candidate approval. A warning is not a verified budget pass.
4. `SESSION_VRP` — candidates only; requires `FAVOURABLE` from step 0. `UNKNOWN` blocks.
5. `RE_ENTRY_REQUIRES_FRESH_PASS` — a candidate after a same-session square-off needs a fresh full pass.
6. `INTRADAY_RV_DRIFT` — five-minute HF block must be fresh (≤120 s old against the decision clock), quality PASS, with a news packet present and an IV anchor; candidates need `FAVOURABLE`; open positions exit on medium/high-confidence `UNFAVOURABLE`.
7. Overnight branch gates (`NEWS_FILTER`, `MARKET_REGIME`, `RECENT_GAP`, `BROKER_RMS`, `EVENT_LATENCY`, `JOINT_GAP_IV_STRESS`) — not reachable under the intraday covenant except as diagnostics.
8. `HARD_EVENT_TAIL_LIQUIDITY` — credible shock, threatened wing/break-even, unusable execution.
9. `EXPIRY_EXIT` — near-expiry harvest saturation, break-even/straddle buffer, gamma stress.
10. `RECENTER` — only with a verified close/reopen transition margin packet.
11. `OPTIMIZER` / `MARGIN_AFFORDABILITY` — ranked wide symmetric candidates, each with a fresh exact-contract margin PASS.
12. Default: HOLD.

## What each gate needs from the tooling

| Gate | Source | Command run on the office Mac |
|---|---|---|
| Session VRP | eSSVI/HAR dashboard on port 8770 | `python skill/butterfly-market-outlook/scripts/evaluate_session_vrp.py --url http://127.0.0.1:8770/api/state` |
| Position truth | local read-only MCP on port 3000 | `dhan_get_positions`, `dhan_get_orders`, `dhan_get_butterfly_state` |
| Chain / surface | local MCP | `dhan_analyze_option_surface`, `dhan_get_option_chain_by_symbol` |
| HF block | local sampler, run **directly on the office Mac**, never via a remote node exec | `node src/workflow-data-cli.mjs --scope hf` in the dhan-chatgpt-mcp project (about five minutes) |
| RV input | RV skill helper | `python skill/intraday-realized-volatility-forecast/scripts/build_rv_input.py --hf-evidence <file> --symbol NIFTY --spot … --atm-iv … --atm-straddle … --news-packet <file> --asof <decision-ISO-time> --output rv_input.json` |
| RV forecast | RV skill | `python skill/intraday-realized-volatility-forecast/scripts/forecast_intraday_rv.py --input rv_input.json` |
| News packet | `market-news-signal-filter` skill, once per horizon | — |
| Margin | local MCP | `dhan_check_butterfly_margin` with `reserveRupees: 1000` |
| Decision | controller | `python skill/butterfly-market-outlook/scripts/decision_controller.py --input controller_snapshot.json` |

Missing required candidate evidence blocks entry. For an existing position, missing HF data or a missing loss measurement is degraded evidence handled exactly as the controller specifies; it is not automatically an exit and never establishes flatness. Account/quote failures cannot support an actionable HOLD. The first terminal gate still wins.

## Controller inputs added on 2026-09-30

| Field | Type | Used by |
|---|---|---|
| `session_vrp_state` | `FAVOURABLE` / `UNFAVOURABLE` / `UNKNOWN` | `SESSION_VRP` (candidates) |
| `daily_loss_budget_rupees` | number ≥ 0 | `LOSS_BUDGET` |
| `session_loss_rupees` | number ≥ 0, realized + bankable loss so far today | `LOSS_BUDGET` |
| `re_entry_after_square_off` | bool | `RE_ENTRY_REQUIRES_FRESH_PASS` |
| `fresh_candidate_pass` | bool | `RE_ENTRY_REQUIRES_FRESH_PASS` |

## What went wrong on 30 September and what changed

- Two NIFTY cycles were entered after a NO TRADE decision, with no session VRP, and rolled twice inside 40 minutes: gross −₹1,969.50 on 22 fills. See `trade-log/trades/2026-09-30-NIFTY-001.md` and `-002.md`.
- The HF sampler had been launched through a remote node exec and was refused; it now runs locally.
- The RV forecaster accepted day-old HF blocks and a missing news packet as CURRENT/FAVOURABLE; it now requires a decision clock (`asof`), freshness within 120 s, an IV anchor, and caps the state at MARGINAL without a news packet.
- The MCP butterfly-state tool failed on every open-position review because Dhan reports position expiries with a timestamp; the expiry is now normalized before the chain call.
- The trade-log summariser could not read `trades.csv`; it now can, and reports gross INR, win/loss sizes and a broker-confirmed-only total.
- The controller had no VRP or loss-budget input; both are now terminal gates, plus the re-entry gate.

## What is still not automated

- Session loss must be supplied to each review from Dhan realized P&L plus the executable close cost; the controller does not fetch it.
- The loss budget is a decision rule, not a broker-side stop. Realized loss can exceed it through slippage.
- Net-after-charges P&L is unknown until reconciled in the local ledger; every figure in this repository is gross.
- Nothing here monitors the market between reviews. Reviews happen when requested.
