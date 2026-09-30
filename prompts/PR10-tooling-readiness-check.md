# PR10 — Tooling readiness check

**When:** before [PR01](PR01-morning-session-vrp-screen.md) on a trading day, or whenever a gate keeps failing for a data reason rather than a market reason.
**Precondition:** none.
**Output:** one row per component, each OK or a concrete blocker. No market decision.

## Prompt

```
Tooling readiness check for the butterfly workflow, no market decision.

Check on the office Mac:
1. Dhan web token: valid through 15:35 IST today? If not, run the local browser recovery and stop at any OTP/CAPTCHA for me.
2. Local read-only MCP on port 3000: health, dhan_get_profile, dhan_get_positions, dhan_get_orders.
3. eSSVI/HAR dashboard on port 8770: /api/state reachable, timestamp fresh, NIFTY covered.
4. HF sampler: node src/workflow-data-cli.mjs --scope hf runs as a local process (do not use a remote node exec); report the block age and quality.
5. Controller and RV skill: decision_controller.py and forecast_intraday_rv.py import cleanly under the locked Python.
Reply with one table: component, status, blocker or expiry. Do not publish a journal entry unless a check touched market data.
```

## Expected reply

Five rows: token, MCP, dashboard, sampler, skills. Each `OK` or a specific blocker.

## Notes

- Any failing component means the matching gate fails closed later. Fix it before PR01 rather than discovering it at 09:50.
- Token recovery may stop at Dhan OTP; that is a human step on the office-Mac browser.
- The sampler takes about five minutes to produce a usable block; run this early enough.
