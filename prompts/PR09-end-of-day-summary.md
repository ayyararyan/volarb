# PR09 — End-of-day summary and journal

**When:** after 15:00 IST once flat, or any evening.
**Precondition:** none. If a cycle is still unrecorded, run [PR05](PR05-square-off-and-closure.md) first.
**Output:** day summary, trade-log summary, journal completeness check, commit hash.

## Prompt

```
End-of-day summary for today.

Confirm flat in Dhan positions and orders. List today's cycles from trades.csv with gross P&L each, run summarize_trade_log.py for the broker-confirmed running total since 23 Sep, and check that every check, outlook, review and decision from today has a journal entry in market-outlook/<today>.md.
Add a closing entry (session VRP state at open, cycles, gross day P&L vs the ₹1,000 budget, which gates fired, what to fix), publish to ayyararyan/volarb main, and verify the remote hash.
Reply with one table: cycles, gross day P&L, running total, journal complete yes/no, commit hash.
```

## Expected reply

One summary table with the commit hash. If the journal is missing an entry, the reply names it rather than silently backfilling.

## Notes

- Gross only. Net-after-charges comes from the local ledger reconciliation, which is a separate task.
- A day with no trade still gets a closing entry; blocked checks are part of the record.
- No positions are opened or closed by this prompt.
