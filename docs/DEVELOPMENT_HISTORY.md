# Development history

Dated development history. Version and implementation statements inside older entries describe their period, not current deployment. Personal journals and financial records preserved during the private-repository cleanup were subsequently removed from the public source boundary and retained in a verified private backup; historical preservation claims below describe the earlier private state. Current entrypoints are in the [repository map](REPOSITORY_MAP.md).

## 2026-09-20 — Front-end discipline and wide-fly optimization

The workflow was tightened so that a live review returns one small decision table only. Alternate actions and long scenario dumps were deliberately removed from the user-facing layer.

Candidate selection was reframed around **wide** butterflies rather than narrow flies. The optimization objective became a trade-off among:

- high theta / carry efficiency;
- low carry burden;
- low tail risk based on the *distribution* of losses, not simply maximum loss;
- adequate OI, bid/ask and execution liquidity.

The idea of reading the full exchange option surface and deriving skew, curvature and the terminal pricing distribution became part of the backend.

## 2026-09-21 — Live Dhan integration and near-expiry logic

The Dhan connector became the preferred source for live position truth and structured full-chain data.

During a near-expiry workflow review, the exit rule was refined. A fixed percentage of original maximum theta was recognized as insufficient because the attainable profit changes as spot drifts.

The workflow therefore moved to **Dynamic Harvest Saturation**: compare the amount already bankable with what is still realistically harvestable from the current state, while explicitly accounting for gamma/path risk and break-even buffer.

The recenter engine was also tightened so that spot drift alone is never sufficient. A new fly must materially improve the risk/carry state after closing and reopening friction.

## 2026-09-21 to 2026-09-22 — Engine v2 architecture

The workflow was reorganized into a canonical MarketState architecture with explicit separation between:

- option-implied risk-neutral information;
- real-world event/path judgment;
- execution and liquidity;
- existing-position economics;
- candidate-search economics;
- follow-up state changes.

Data health and tail/event gates were moved ahead of theta optimization.

A promotion-gate concept was introduced to compare the more sophisticated v2 engine with the earlier simpler workflow before treating v2 as the production process. The emphasis was on deterministic checks, consistency, risk-sensitivity and decision quality rather than waiting for a long live P&L sample.

## 2026-09-22 — Repository capture

The complete live Butterfly Market Outlook v2 skill source, references and scripts were copied into this repository. Trade/review recordkeeping adopted explicit provenance so missing historical broker fields are left unknown rather than reverse-engineered. Those personal records now remain outside public source in private storage.


## 2026-09-23 — Overnight carry failure becomes a first-class problem

An expiry-eve risk review exposed a weakness in treating overnight theta as though it were locally continuous: gap risk can overwhelm the expected theta harvest. The public history preserves that design lesson, not the underlying personal trade record.

The engine was tightened around:
- next-actionable-exit rather than expiry-payoff thinking;
- broker/RMS and auto-squareoff feasibility;
- full joint spot-gap / IV-expansion repricing;
- stricter expiry-eve carry rules.

## 2026-09-24 — Empirical gap gate and Engine v2.2 regime layer

Recent NIFTY opens were reviewed directly. The lesson was that most overnight carries can look harmless while a small number of tail gaps dominate the risk.

An empirical gap-regime gate was added:
- rolling 20–30 open sample;
- p80/p90 absolute gap;
- frequency of large gaps;
- current-spot-to-nearest-break-even buffer;
- expected gap-gamma drag versus next-open harvest.

The broader **v2.2 market-regime engine** was then added so butterfly decisions depend on the environment rather than on IV/theta alone.

The engine now distinguishes:
- `CALM_CARRY`;
- `TRANSITION`;
- `LATENT_JUMP_RISK`;
- `ACTIVE_STRESS`;
- `UNKNOWN`.

A low VIX no longer qualifies as evidence of a calm regime when realized tail gaps or exogenous event hazard remain elevated. Intraday butterflies remain possible in hostile regimes, but overnight carry must pass the regime layer before ordinary theta/carry ranking.


## 2026-09-30 — Session VRP gate, loss budget, validation fixes (v2.6)

A workflow audit identified missing session-level premium and loss-budget inputs, the need to enforce NO TRADE decisions, and three tooling defects. Personal trade results and execution details are retained privately rather than reproduced in the public development history.

Changes:

- **Session VRP gate.** `scripts/evaluate_session_vrp.py` consumes the dashboard `/api/state` and returns FAVOURABLE / UNFAVOURABLE / UNKNOWN; the controller blocks candidates at `SESSION_VRP` unless FAVOURABLE. Unknown is never benign.
- **Loss-budget gate.** `daily_loss_budget_rupees` and `session_loss_rupees` drive a terminal `LOSS_BUDGET` gate (SQUARE OFF / NO TRADE); missing inputs warn.
- **Re-entry gate.** A candidate after a same-session square-off requires a fresh full pass.
- **RV forecaster validation.** Decision clock (`asof`) with 120-second freshness, future-skew rejection, surface-snapshot alignment, mandatory news packet (capped at MARGINAL when missing), consistent low-confidence INSUFFICIENT_DATA without an IV anchor. Fixture checker extended with five negative cases. `build_rv_input.py` converts office-Mac sampler evidence into forecaster input.
- **MCP.** `dhan_get_butterfly_state` normalizes Dhan's timestamped position expiry to `YYYY-MM-DD` before the chain call; the Invalid Expiry Date failure on every open-position review is fixed and covered by a test.
- **Trade-log summariser** accepts explicit private CSV inputs and reports gross INR statistics including a broker-confirmed-only total.
- **Documentation.** `docs/DAILY_OPERATING_ALGORITHM.md` is the single daily sequence; decision-algorithm.md is v2.6.

Not changed: thresholds in the optimizer, expiry-exit or overnight engines; the covenant; live execution remains disabled.


## 2026-10-03 — Repository-wide cleanup and consistency repair

Audited all 402 baseline files against `ec534e8`, then used fresh independent reviewers. The [canonical repository map](REPOSITORY_MAP.md), [archive index](../archive/README.md), [full audit](audits/2026-10-03-repository-cleanup.md) and [per-file classification](audits/2026-10-03-file-classification.tsv) describe the final ownership and dispositions.

- Archived the evolving architecture notebook, old single-owner VID guide, initial lab audit/release reports, dated Dhan/dashboard receipts and retired housekeeping policy. No historical financial record was rewritten; no disposable tracked code required deletion.
- Standardized **Execution Engine** / `component.execution_engine` while retaining every `[5,0,...]` VID, alias/mirror and legacy provider/executor path. Distinguished implemented contracts/test infrastructure from the future full engine.
- Repaired metadata validators, simulator correctness, packaged provider imports, non-root Docker permissions, mutation-disabled defaults, v2.6 workflow evidence/clock plumbing and missing VRP health-proof handling. No strategy thresholds or live activation changed.
- Separated current docs from historical receipts; fixed cycle-accounting guidance, bounded prompts, source-package navigation and consumer CI filters; added offline hygiene checks.
- Offline validation passed: 823 unit/regression tests, 9 RV fixture checks, all 3 skill packages, generated research artifacts, isolated setup twice, portable ZIP and Docker build/non-root smoke. All nine hosted workflow families passed; exact tested commits and run links are recorded in the audit report. A shallow-checkout-only whitespace failure was repaired by retaining HEAD's parent, without editing preserved historical records.
- Preserved the adopted covenant, frozen research controller, sole external live ledger, credentials, existing deployment and unrelated Drive-checkout dashboard edit. Source publication does not deploy services or refresh installed skills.
