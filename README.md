# volarb

Research, decision logic, and trade journal for Indian index butterfly strategies.

The repository is the source of truth for **Butterfly Market Outlook v2.2**, used for NIFTY, BANKNIFTY, and SENSEX iron butterflies. The engine separates option-implied information from real-world path/event risk, classifies the market regime before overnight carry, and keeps the final trading decision deliberately small.

## Layout

- `skill/butterfly-market-outlook/` — production skill source, references, scripts, tests, and UI metadata.
- `market-outlook/` — one append-only market-outlook journal per IST day.
- `trade-log/` — executed-trade ledger, lifecycle records, post-trade episodes, and provenance snapshots.
- `docs/WORKFLOW.md` — human-readable operating workflow.
- `docs/DEVELOPMENT_HISTORY.md` — concise evolution of the engine.
- `.github/` — skill validation, regression testing, and packaging workflow.

## Operating rules

1. **Data health before optimization.**
2. **Market regime before overnight carry.** Low VIX alone is not evidence of a calm regime.
3. **Risk-neutral is not real-world.** RND is pricing information, not a literal physical forecast.
4. **Tail/event/gap risk outranks theta.**
5. **Actual four-leg execution matters.**
6. **Near expiry is a different problem.** Dynamic harvest, gamma, break-even buffer, and next-open risk dominate headline theta.
7. **Intraday is the default in hostile regimes.** Overnight carry must explicitly pass regime, recent-gap, event-latency, broker/RMS, and full-reprice stress gates.
8. **Learning is logged, not auto-fitted.** Threshold changes require review and regression testing.

## Current engine

**Butterfly Market Outlook v2.2 — regime-aware candidate engine**

Regimes: `CALM_CARRY / TRANSITION / LATENT_JUMP_RISK / ACTIVE_STRESS / UNKNOWN`.

The repository records research and trading process. It is not a promise of future performance.
