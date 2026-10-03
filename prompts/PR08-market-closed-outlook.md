# PR08 — Market-closed outlook

**When:** pre-open (before 09:15 IST), after 15:30 IST, weekends or holidays.
**Precondition:** none. Useful the evening before or early morning to see whether tomorrow is likely to open for entries.
**Output:** Mode C with `pre-open watchlist` reasons, a NO TRADE row, or a `LOCKED OVERNIGHT` status row if a position is unexpectedly open.

## Prompt

```
Market-closed outlook for NIFTY butterflies for the next session.

Read fresh Dhan positions and orders first; access failure means unknown exposure and a blocked account-specific assessment, never flatness. If a position is open, reply with a one-row LOCKED OVERNIGHT status and the next actionable exit window instead of an outlook.
Only if verified flat with no pending orders: read the latest available chain and surface, the session VRP dashboard state, and run the market-news-signal-filter once for the next-session horizon. Apply the tail-risk gate.
Do not run the HF sampler; there is no live block to sample.
Save the outlook to the configured private daily journal outside source and verify persistence before replying; never publish it to GitHub.
Reply with the Mode C table only. If the gate passes, say pre-open watchlist in each Why cell; if it fails, one NO TRADE row with the dominant risk and when to re-run.
```

## Expected reply

Mode C table with `pre-open watchlist` rows, or one `NO TRADE` row, or one `LOCKED OVERNIGHT` row.

## Notes

- Watchlist rows are not entries. Tomorrow still needs [PR01](PR01-morning-session-vrp-screen.md) FAVOURABLE and a full [PR02](PR02-candidate-search.md) pass with a live HF block.
- Post-close chains are stale by definition; the reply cites their timestamp.
- Scenarios in the journal are conditional repricings, not forecasts.
