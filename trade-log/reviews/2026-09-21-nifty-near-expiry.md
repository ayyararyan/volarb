# NIFTY carried butterfly — 2026-09-21

Type: **live position review**

Provenance: **conversation-reconstructed**

## Established facts

- The butterfly had been opened on Friday afternoon, 2026-09-18.
- It was still being actively reviewed on Monday, 2026-09-21.
- The position was near expiry, with roughly one trading day left in the review discussion.
- Multiple intraday reviews were requested, including late-afternoon / carry logic.
- The exit framework was changed from a static fraction of original maximum theta to a **dynamic harvest** concept because spot drift changes the remaining attainable profit.
- The workflow explicitly considered whether recentering was justified with little time left to expiry.
- The position was subsequently closed and the final P&L was checked in conversation.

## Important model change triggered by this trade

The trade exposed the weakness of a static "75% of theta harvested" rule. The production logic was revised to compare **bankable profit now** with the **remaining realistically harvestable profit from the current state**, while giving much more weight to gamma/path risk near expiry.

This became the basis of the Engine v2 expiry-exit algorithm.

## Missing broker fields

Exact strikes, fills, quantity and realized P&L are not present in the currently recoverable connector context. They are intentionally not reconstructed.

When a historical tradebook or contract note is available, backfill the matching row in `trade-log/trades.csv` and preserve this review note as the decision-history record.
