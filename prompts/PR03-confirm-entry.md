# PR03 — Confirm entry and record the trade

**When:** immediately after all four legs fill. Step 4 of the daily algorithm.
**Precondition:** you executed a candidate from [PR02](PR02-candidate-search.md) or [PR06](PR06-re-entry-fresh-pass.md).
**Output:** trade ID, `trades.csv` row, trade file and journal entry, all before any review.

## Prompt

```
Entry filled. Record the trade.

Butterfly: NIFTY <expiry> <lower> / <body> / <upper>, one lot total.
Fill time: <HH:MM> IST.

Read the fills from Dhan positions and orders (do not take my figures as truth), reconcile signed units per leg, and compute gross entry credit/debit.
Write the trade file, the trades.csv row and the journal entry under a new cycle ID, then publish to ayyararyan/volarb main.
Also append the opening row to the local simple_ledger via the shared writer.
Reply with one row: trade ID, verified legs, gross entry, session loss so far vs ₹1,000, first review time.
```

## Expected reply

One row: cycle/trade ID, verified legs and units, gross entry credit, session loss vs budget, and the first review time (normally 30 minutes after fill).

## Notes

- Fills come from Dhan, not from the prompt. If Dhan disagrees with your figures the reply will say so.
- Same cycle ID persists through any adjustment; re-entry after a square-off gets a new ID.
- Replace `<expiry>`, `<lower>`, `<body>`, `<upper>`, `<HH:MM>` before sending.
