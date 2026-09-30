# Tasks

## Done — 2026-09-30

- [x] Session VRP gate (`evaluate_session_vrp.py`, controller `SESSION_VRP`), loss-budget gate, re-entry gate, tests.
- [x] RV forecaster freshness/news-packet/IV validation; fixture checker extended with negative cases; `build_rv_input.py`.
- [x] MCP `dhan_get_butterfly_state` expiry normalization; local service redeployed.
- [x] `summarize_trade_log.py` reads `trade-log/trades.csv`.
- [x] 2026-09-30 NIFTY cycles recorded; `docs/DAILY_OPERATING_ALGORITHM.md` written.

## Open

- [ ] Feed `session_loss_rupees` automatically from Dhan realized P&L plus executable close cost at each review.
- [ ] Extend the IV/HAR dashboard to BANKNIFTY and SENSEX so the session VRP gate is not `UNKNOWN` for them.
- [ ] Live-session verification of the local HF sampler → `build_rv_input.py` → forecaster path during market hours.
- [ ] Transition-scoped margin packet so RECENTRE can be evaluated rather than blocked.
- [ ] Reconcile net-after-charges P&L for all eight recorded cycles in the local ledger.

## Previously listed — 2026-09-30

### Butterfly workflow automation

- [ ] Complete end-to-end data acquisition.
- [ ] Perform live-session verification.
- [ ] Implement scheduling/publication adapters.
- [ ] Resolve live-execution permission: administrator adoption of the bounded execution policy and verification in a fresh session. This task does not itself enable live orders.
