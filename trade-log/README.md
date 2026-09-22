# Trade log

This directory separates **executed trades** from **research/review sessions**.

## Files

- `trades.csv` — compact ledger of trades that can be established as executed.
- `episodes.jsonl` — machine-readable post-trade episodes for calibration analysis.
- `reviews/` — dated market/position review history, including candidate sessions that may not have resulted in trades.
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
