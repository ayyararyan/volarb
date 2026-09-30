# PR07 — Anytime status check

**When:** any time you want a factual snapshot without a trading decision.
**Precondition:** none.
**Output:** positions, orders, session loss vs budget, gate inputs available. No HOLD/SQUARE OFF/candidate output.

## Prompt

```
Status check only, no trading decision.

Read fresh Dhan positions and orders. Report: open butterfly (or flat), pending orders, today's realized P&L from Dhan, bankable P&L at executable close if a position is open, session loss vs the ₹1,000 budget, the current session VRP state from the dashboard, and the time remaining to the 15:00 IST flat deadline.
Publish the check to the daily journal on ayyararyan/volarb main before replying.
Reply with one table only. Do not recommend HOLD, SQUARE OFF or candidates.
```

## Expected reply

One status table. Rows or columns for position, orders, realized P&L, bankable P&L, session loss vs budget, VRP state, time to deadline.

## Notes

- Account or quote failure is reported as unknown exposure, never as flat.
- Use this before [PR04](PR04-open-position-review.md) if you want to know the session loss figure to pass in.
- This is a bounded check, not monitoring. Nothing runs between prompts.
