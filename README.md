# volarb

Research, execution logic, and trade journal for index volatility-arbitrage butterflies.

This repository is the working record of the **Butterfly Market Outlook** framework used for NIFTY, BANKNIFTY, and SENSEX iron butterflies. It separates option-implied information from real-world path/event judgment, applies deterministic data-health and expiry-risk gates, and keeps the user-facing decision intentionally small: HOLD / RECENTRE / SQUARE OFF before 14:45 IST, or CARRY / RECENTRE / SQUARE OFF thereafter.

## Repository layout

- `skill/butterfly-market-outlook/` — the ChatGPT skill source: control instructions, references, scripts, and UI metadata.
- `docs/WORKFLOW.md` — end-to-end operating workflow in human-readable form.
- `trade-log/` — trade episodes, review history, and a machine-readable ledger.
- `trade-log/episodes.jsonl` — post-trade learning records suitable for the skill's calibration workflow.
- `trade-log/trades.csv` — compact trade ledger.

## Core philosophy

1. **Data health before optimization.** Bad or stale option data blocks new entries.
2. **Risk-neutral is not real-world.** RND is used for pricing geometry and tail compensation, not as a literal forecast.
3. **Tail/event risk outranks theta.** High carry never overrides a material jump regime or break-even threat.
4. **Actual four-leg execution matters.** Liquidity, bid/ask, Greeks, and friction are evaluated on the executable iron-fly legs.
5. **Near expiry is a different regime.** Remaining harvest is compared with gamma/path risk using dynamic harvest saturation.
6. **Recentring must earn its keep.** A new fly must materially improve alignment/risk after close-and-reopen friction.
7. **Learning is logged, not auto-fitted.** Threshold changes require explicit review and regression testing.

## Data sources

The live workflow prefers Dhan for account truth and structured option-chain data, validates against official exchange sources where needed, and uses fresh public information for event and cross-asset context.

## Trade-log provenance

Trade records distinguish among:
- **broker-verified** fields obtained from Dhan;
- **conversation-reconstructed** facts established during live reviews;
- **unknown** fields that are intentionally left blank rather than inferred.

The connected Dhan interface currently provides current positions/orders/trades but does not expose a complete historical fill ledger through this repository workflow. Older fills therefore remain marked as incomplete unless independently supplied or recovered from another source.

## Status

Engine: **Butterfly Market Outlook v2**

Timezone: **Asia/Kolkata**

This repository is a research and trading-process record, not a promise of future performance.
