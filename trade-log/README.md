# Trade log

This directory separates **executed trades** from **research/review sessions**.

## Files

- `trades.csv` — compact ledger of trades that can be established as executed.
- `episodes.jsonl` — machine-readable post-trade episodes for calibration analysis.
- `reviews/` — **legacy pre-journal review history only**. New reviews belong in `market-outlook/YYYY-MM-DD.md`; do not create new files here.
- `snapshots/` — raw provenance snapshots where useful.

## Provenance levels

### broker-verified
Fields obtained directly from a broker/account endpoint or an independently supplied contract note / statement.

### conversation-reconstructed
Facts explicitly established during the live working sessions, but not currently recoverable from the broker history endpoint.

### unknown
Fields that are not available in current context. They are intentionally left blank.

Do not infer missing strikes, fills, quantities or P&L merely to make the ledger look complete.

## Backfilling

If historical Dhan contract notes / tradebook exports become available, backfill the missing broker fields while preserving the original conversation-derived episode and adding a `broker-verified` provenance marker.

## Automatic updates from the Butterfly Market Outlook skill

The skill now treats this repository as the persistent research/trading journal when GitHub is writable.

- Every market outlook and position review is appended to `market-outlook/YYYY-MM-DD.md`.
- A confirmed executed butterfly is entered in `trades.csv` and may receive a detailed `trade-log/trades/<trade_id>.md` lifecycle record.
- Position checks and candidate reviews are recorded chronologically only in the daily market-outlook file; durable execution facts go in the ledger.
- Fully closed trades update `episodes.jsonl` for post-trade calibration.
- Recommendations are never logged as fills unless Dhan or the user confirms execution.
