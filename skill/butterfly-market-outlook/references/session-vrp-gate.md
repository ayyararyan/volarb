# Session variance-risk-premium gate

Added 2026-09-30. Runs for every **candidate** branch immediately after the data-health and post-close gates and before the intraday HF RV/drift gate. It never forces an exit of an existing position.

## Purpose

The butterfly programme exists to harvest the variance risk premium. Before spending effort on a five-minute HF block, strikes, liquidity and margin, establish that a premium exists for the session at all. On 2026-09-30 the front-expiry ATM implied volatility (≈11.9%) sat below the HAR next-session realized-volatility forecast (≈12.7%); two cycles were entered anyway and lost ₹1,969.50 gross.

## Source

The local eSSVI/HAR dashboard (`http://127.0.0.1:8770/api/state` on the office Mac) publishes:

- `atm.front.implied_volatility` — eSSVI-fitted ATM IV for the front option expiry, forward moneyness 0;
- `forecast.annualized_volatility` — log-HAR(1,5,22) forecast of one full session's realized variance including the overnight gap, from 5-minute NIFTY spot bars;
- `verdict.status`, `surface_is_stale`, `fit_ok`, `fit_age_seconds`, `arbitrage.checked`, `arbitrage.passed` — surface health;
- `forecast.status`, `forecast.age_calendar_days` — forecast health.

IV and HAR RV cover different horizons. The gate treats their difference as a **session-level premium screen only**, not a tradable spread, and not a substitute for the same-horizon HF RV/IV comparison in the child skill.

## Script

```bash
python scripts/evaluate_session_vrp.py --url http://127.0.0.1:8770/api/state --pretty
python scripts/evaluate_session_vrp.py --input saved_state.json --pretty
```

Defaults: margin ≥ 1.0 vol point **and** IV/RV ratio ≥ 1.05 for `FAVOURABLE`. Both thresholds are conservative screens chosen so that rounding, fit noise and horizon mismatch cannot manufacture a premium; they are not calibrated from outcomes and must not be loosened from a small sample.

| Output | Meaning | Controller effect |
|---|---|---|
| `FAVOURABLE` | live, arbitrage-clean surface; current forecast; IV exceeds HAR RV by the margin and ratio | continue to HF RV gate |
| `UNFAVOURABLE` | premium absent or below margin | NO TRADE, terminal gate `SESSION_VRP` |
| `UNKNOWN` | feed not live, fit stale/failed, arbitrage violation, forecast missing/old, or values missing | NO TRADE, terminal gate `SESSION_VRP` |

Pass the state into the controller snapshot as `session_vrp_state`. A missing field is `UNKNOWN`.
An actionable result requires explicit boolean `fit_ok: true` and
`arbitrage.checked: true, arbitrage.passed: true`; missing or unchecked proof is
not clean-surface evidence. Malformed state/nested objects return `UNKNOWN`
instead of raising an exception. The workflow adapter separately binds the source
snapshot to its index, evidence reference and fresh decision-time observation.

## Limits

- The dashboard's HAR forecast is as of the prior session close. Re-run the gate if the fit or forecast age exceeds the script limits.
- The front expiry under two days is gamma-dominated; the script warns and the next expiry's ATM reading should be preferred manually.
- Only NIFTY is fitted on the dashboard today. For BANKNIFTY or SENSEX without an equivalent feed, the state is `UNKNOWN` and no new entry is possible until one exists.
- Journal the gate output in the `Session VRP` field of every candidate search, including blocked ones.
