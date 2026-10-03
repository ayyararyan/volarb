# PR01 — Morning session VRP screen

**When:** trading day, before 09:30 IST. Step 0 of the daily algorithm.
**Precondition:** the local eSSVI/HAR dashboard is running on port 8770 (see [PR10](PR10-tooling-readiness-check.md)).
**Gate exercised:** `SESSION_VRP` input. Only `FAVOURABLE` opens the day for [PR02](PR02-candidate-search.md).

## Prompt

```
Morning session VRP screen for NIFTY.

Run evaluate_session_vrp.py against the local IV/HAR dashboard at http://127.0.0.1:8770/api/state.
Report the state (FAVOURABLE / UNFAVOURABLE / UNKNOWN) with the IV and HAR RV figures it used and the dashboard timestamp.
If the state is not FAVOURABLE, the day is closed for new entries: journal the blocked check and stop.
Save the entry to the configured private journal outside the source checkout and verify persistence before replying; never publish financial records to GitHub.
Reply with one table only.
```

## Expected reply

One row: state, IV vs HAR RV, dashboard timestamp, and whether a candidate search is permitted today.

## Notes

- `UNKNOWN` (dashboard down, stale, or symbol not covered) blocks exactly like `UNFAVOURABLE`. Missing evidence is never benign.
- The dashboard currently covers NIFTY only. BANKNIFTY and SENSEX return `UNKNOWN` until extended (open task in `tasks.md`).
- This gate never forces an exit of an existing position.
