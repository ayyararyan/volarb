# PR05 — Square-off and closure record

**When:** after you have squared off all four legs, whether on a SQUARE OFF review, at the ₹1,000 budget, or at the 15:00 IST deadline. Step 9 of the daily algorithm.
**Precondition:** Dhan shows the butterfly closed.
**Output:** closure fills, gross P&L, post-trade diagnosis, journal, commit hash.

## Prompt

```
Squared off. Record the closure.

Cycle ID: <ID from PR03>. Exit time: <HH:MM> IST. Reason: <review said SQUARE OFF / loss budget / 15:00 deadline>.

Read exit fills from Dhan trades/order-trade execution records; reconcile positions and outstanding orders, verifying zero remaining units and no pending strategy orders.
Compute gross cycle P&L, update the trade file and trades.csv row, close the cycle in the local simple_ledger via the shared writer, and write a short post-trade diagnosis (entry thesis vs what happened, which gate fired).
Publish to ayyararyan/volarb main and reply with one row: cycle ID, gross P&L, session loss vs ₹1,000, remaining units and pending strategy orders (both must be 0), commit hash.
```

## Expected reply

One closure row. Remaining units and pending strategy orders must both read 0; residual exposure or working orders keep closure unverified.

## Notes

- Every figure in the repository is gross. Net-after-charges P&L is reconciled later in the local ledger.
- If you square off without a SQUARE OFF review, say so in the reason; the diagnosis records it as a self-directed exit.
- After closure, re-entry needs a fresh full pass ([PR06](PR06-re-entry-fresh-pass.md)) and inherits today's loss.
