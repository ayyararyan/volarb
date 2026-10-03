# PR07 — Bounded status check

**When:** an authorized scheduled review window or an objective material-risk/emergency trigger, when a factual snapshot is needed without a trading decision.
**Precondition:** the covenant permits this review window. Curiosity, anxiety or an urge to check P&L is not a trigger.
**Output:** positions, orders, session loss vs budget, gate inputs available. No HOLD/SQUARE OFF/candidate output.

## Prompt

```
Status check within the current authorized review window or objective emergency trigger; no trading decision.
Reason/window: <scheduled review time or material-risk trigger>.

Read fresh Dhan positions and orders. Report: open butterfly (or flat), pending orders, today's realized P&L from Dhan, bankable P&L at executable close if a position is open, session loss vs the ₹1,000 budget, the current session VRP state from the dashboard, and the time remaining to the 15:00 IST flat deadline.
Save the check to the configured private daily journal outside source and verify persistence before replying; never publish it to GitHub.
Reply with one table only. Do not recommend HOLD, SQUARE OFF or candidates.
```

## Expected reply

One status table. Rows or columns for position, orders, realized P&L, bankable P&L, session loss vs budget, VRP state, time to deadline.

## Notes

- Account or quote failure is reported as unknown exposure, never as flat.
- Use this before [PR04](PR04-open-position-review.md) if you want to know the session loss figure to pass in.
- This is a bounded check, not monitoring. Nothing runs between prompts.
