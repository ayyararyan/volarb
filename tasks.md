# Tasks

## Done — 2026-09-30

- [x] Session VRP gate (`evaluate_session_vrp.py`, controller `SESSION_VRP`), loss-budget gate, re-entry gate, tests.
- [x] RV forecaster freshness/news-packet/IV validation; fixture checker extended with negative cases; `build_rv_input.py`.
- [x] MCP `dhan_get_butterfly_state` expiry normalization; local service redeployed.
- [x] `summarize_trade_log.py` reads CSV from an explicit private input path.
- [x] 2026-09-30 NIFTY cycles recorded; `docs/DAILY_OPERATING_ALGORITHM.md` written.

## Open — current manual workflow

Status reviewed 2026-10-03 against source. Historical deployment receipts above are not fresh readiness checks.

- [ ] Feed `session_loss_rupees` automatically from Dhan realized P&L plus executable close cost at each review.
- [ ] Extend the IV/HAR dashboard to BANKNIFTY and SENSEX so the session VRP gate is not `UNKNOWN` for them.
- [ ] Live-session verification of the local HF sampler → `build_rv_input.py` → forecaster path during market hours.
- [ ] Transition-scoped margin packet so RECENTRE can be evaluated rather than blocked.
- [ ] Reconcile net-after-charges P&L for all eight recorded cycles in the local ledger.

## Previously listed — 2026-09-30

### Butterfly workflow automation

- [ ] Complete end-to-end live orchestration. Read-only acquisition and explicit accounting adapters exist, but SHADOW does not automatically dispatch them.
- [ ] Perform live-session verification.
- [ ] Implement scheduling/publication adapters.
- [ ] Resolve live-execution permission: administrator adoption of the bounded execution policy and verification in a fresh session. This task does not itself enable live orders.

## Open — Execution Engine and strategy architecture

- [ ] **NEXT PRIORITY — Classify every Execution Engine box and sub-box as `PURE_AGENTIC`, `PURE_ALGORITHMIC`, or `HYBRID`.** Decide the classification deliberately for each canonical VID/component before further box implementation, beginning with `[5,0,8,1,2]` Command Commit Guard. For hybrid boxes, specify the exact boundary between LLM/LangGraph judgment and deterministic code, including which side has final mutation authority. Record the decisions in the canonical execution architecture/docs so later implementations inherit the classification rather than re-deciding it ad hoc.
- [ ] Implement the generic convergence pipeline beyond current runtime ports/contracts; keep strategy semantics upstream and broker mechanics downstream.
- [ ] Supply production clock, persistence/Execution Ledger, scheduler and full engine driver, then validate composed engine behavior with the existing testkit.
- [ ] Measure latency budgets and select concurrency/persistence topology from evidence; no current benchmark establishes production targets.
- [ ] Implement and validate the strategy-side orchestration/optional Strategy Execution Adapter under the [canonical design](docs/autonomous-butterfly-workflow.md).
- [ ] Adopt any future execution authority through the covenant process and explicit readiness verification; source cleanup does not activate it.

Completed architecture decisions (not pending design): canonical Execution Engine identity, Broker Execution Port vocabulary, Provider Error Envelope, Dhan translation/streams and deterministic testbed infrastructure. See [current notes](notes.md) and [implementation status](execution-engine/README.md).
