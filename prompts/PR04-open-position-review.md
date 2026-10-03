# PR04 — Open-position review

**When:** every 30 minutes while a butterfly is open; every 15–20 minutes when the RV state is MARGINAL or a break-even is within half an ATM straddle. Step 5 of the daily algorithm. Last useful review is before 15:00 IST.
**Precondition:** an open butterfly recorded via [PR03](PR03-confirm-entry.md).
**Gates exercised:** `LOSS_BUDGET`, `INTRADAY_RV_DRIFT`, `HARD_EVENT_TAIL_LIQUIDITY`, `EXPIRY_EXIT`, default HOLD.

## Prompt

```
Review my open NIFTY butterfly.

Session realized loss so far today: ₹<amount>. Daily loss budget: ₹1,000.

Read fresh Dhan positions and orders and dhan_get_butterfly_state. Pull the current chain and executable-side close quotes for all four legs, compute bankable loss at executable close, and add it to the session loss.
Run the local five-minute HF sampler, build the RV input with asof and the news packet, run the RV/drift forecast, then run the controller with daily_loss_budget_rupees 1000 and session_loss_rupees.
Save the entry to the configured private journal outside the source checkout and verify persistence before replying; never publish financial records to GitHub.
Reply with the Mode A table only: HOLD or SQUARE OFF, one concrete reason, next review time in IST. State session loss vs budget inside the Why cell.
```

## Expected reply

One Mode A row. `HOLD` with a clock time for the next review, or `SQUARE OFF` with `—`.

## Notes

- RECENTRE is effectively unavailable today because the margin preflight is entry-only. A wrong body is a SQUARE OFF.
- Medium/high-confidence `UNFAVOURABLE` RV is an exit signal. MARGINAL shortens the cadence. Missing HF data alone does not force an exit, but it is disclosed.
- Session loss reaching ₹1,000 is terminal: SQUARE OFF regardless of other metrics.
- At or after 14:45 the default is SQUARE OFF; the covenant requires flat by 15:00.
- Replace `<amount>` with today's realized loss from Dhan (₹0 if none yet).
