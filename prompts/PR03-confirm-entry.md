# PR03 — Confirm entry and record the trade

**When:** immediately after all four legs fill. Step 4 of the daily algorithm.
**Precondition:** you executed a candidate from [PR02](PR02-candidate-search.md) or [PR06](PR06-re-entry-fresh-pass.md).
**Output:** trade ID, local shared-writer accounting, private trade file and journal entry; recordkeeping never delays urgent risk management.

## Prompt

```
Entry filled. Record the trade.

Butterfly: NIFTY <expiry> <lower> / <body> / <upper>, one lot total.
Fill time: <HH:MM> IST.

Read Dhan trades/order-trade execution records and reconcile positions and outstanding orders (do not infer fills from acceptance or take my figures as truth), reconcile signed units per leg, and compute gross entry credit/debit.
First append verified fills and the opening accounting review through the local shared writer under a new cycle ID. Then write the private trade file, trades.csv row and journal entry in the configured private journal outside source; never publish these records to GitHub. Do not create a second live ledger.
Reply with one row: trade ID, verified legs, gross entry, session loss so far vs ₹1,000, first review time.
```

## Expected reply

One row: cycle/trade ID, verified legs and units, gross entry credit, session loss vs budget, and the first review time (normally 30 minutes after fill).

## Notes

- Fills come from Dhan, not from the prompt. If Dhan disagrees with your figures the reply will say so.
- Same cycle ID persists through any adjustment; re-entry after a square-off gets a new ID.
- Replace `<expiry>`, `<lower>`, `<body>`, `<upper>`, `<HH:MM>` before sending.
