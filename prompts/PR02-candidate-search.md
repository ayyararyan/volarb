# PR02 — Candidate search

**When:** 09:45–09:55 IST. Step 2 of the daily algorithm.
**Precondition:** [PR01](PR01-morning-session-vrp-screen.md) returned `FAVOURABLE` today. Otherwise do not send this prompt.
**Gates exercised:** all terminal gates in controller order, then optimizer and margin affordability.

## Prompt

```
Candidate search for one NIFTY butterfly, one lot total, intraday only, flat by 15:00 IST.

Today's session VRP screen was FAVOURABLE. Session loss so far today: ₹0. Daily loss budget: ₹1,000.

1. Read fresh Dhan positions and orders; confirm flat with no pending orders.
2. Pull one coherent current-expiry chain with timestamped executable-side quotes and data health.
3. Run the five-minute HF sampler locally on the office Mac, build the RV input with asof, the IV anchor and one news packet, and run the RV/drift forecast.
4. Run the first-terminal-gate controller with session_vrp_state, daily_loss_budget_rupees 1000 and session_loss_rupees.
5. If the controller reaches the optimizer, rank wide symmetric candidates and run dhan_check_butterfly_margin with reserveRupees 1000 for each finalist.

Publish the journal entry to ayyararyan/volarb main before replying.
Reply with the Mode C table only: up to three ranked rows, or one NO TRADE row naming the failing gate.
```

## Expected reply

Mode C table. Either up to three rows of `[expiry] [lower / body / upper]` with a short reason each, or one `NO TRADE` row that names the dominant blocked gate.

## Notes

- A blocked gate is NO TRADE. Later metrics never override an earlier failure.
- The HF block must be under 120 s old against the decision clock, quality PASS, with a news packet. Session OHLC or prior-day RV cannot substitute.
- Margin PASS is research affordability, not sizing or risk approval.
- Change `NIFTY` to `BANKNIFTY` or `SENSEX` only if PR01 was FAVOURABLE for that symbol.
