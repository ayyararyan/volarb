# PR06 — Re-entry fresh pass

**When:** after a same-session square-off, only if there is time to hold and exit before 15:00 IST. Step 8 of the daily algorithm.
**Precondition:** [PR05](PR05-square-off-and-closure.md) recorded closure with 0 remaining units, and session loss is below ₹1,000.
**Gates exercised:** `RE_ENTRY_REQUIRES_FRESH_PASS` plus every gate in [PR02](PR02-candidate-search.md).

## Prompt

```
Re-entry candidate search for one NIFTY butterfly, one lot total, intraday only, flat by 15:00 IST.

This is a same-session re-entry after square-off of cycle <ID>. Session realized loss so far today: ₹<amount>. Daily loss budget: ₹1,000.

Treat this as a fresh complete pass: confirm flat with no pending orders in Dhan, re-read the session VRP dashboard, pull a fresh chain, run the local HF sampler and RV/drift forecast with a current news packet, then run the controller with re_entry_after_square_off true, fresh_candidate_pass true, daily_loss_budget_rupees 1000 and session_loss_rupees.
Only if the controller reaches the optimizer, rank candidates and run dhan_check_butterfly_margin with reserveRupees 1000.
Publish the journal entry to ayyararyan/volarb main before replying.
Reply with the Mode C table only.
```

## Expected reply

Mode C table: up to three candidates, or one `NO TRADE` row.

## Notes

- Re-entry inherits the day's loss. With ₹700 already lost, a new butterfly has only ₹300 of budget before a forced SQUARE OFF.
- Nothing from the earlier pass is reused: no chain, no HF block, no margin packet.
- A new cycle ID is assigned at [PR03](PR03-confirm-entry.md) if you enter.
- Replace `<ID>` and `<amount>` before sending.
