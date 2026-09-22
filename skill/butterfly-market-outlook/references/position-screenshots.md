# Position Screenshot and Calculation Guide

## Screenshot extraction checklist

Read, if visible:
1. underlying/index;
2. expiry date;
3. call or put for each leg;
4. strike;
5. signed quantity: long positive, short negative;
6. average/entry premium;
7. LTP/current premium;
8. current P&L;
9. spot/futures price;
10. broker timestamp.

For a standard long butterfly, a common ratio is `+1 / -2 / +1`. Do not assume this ratio if the screenshot shows otherwise.

## JSON schema for scripts/analyze_position.py

```json
{
  "underlying": "NIFTY",
  "spot": 23346.4,
  "atm_iv": 0.1139,
  "days_to_expiry": 1.0,
  "legs": [
    {"type": "call", "strike": 23000, "qty": 1, "entry": 360.0, "multiplier": 75},
    {"type": "call", "strike": 23350, "qty": -2, "entry": 170.0, "multiplier": 75},
    {"type": "call", "strike": 23700, "qty": 1, "entry": 45.0, "multiplier": 75}
  ]
}
```

Notes:
- `type` must be `call` or `put`.
- `qty` is positive for long and negative for short.
- `entry` is premium per index point. If unavailable, omit it; expiry payoff can still be mapped but profit/loss break-evens cannot be calculated.
- `multiplier` is optional and defaults to 1. Use the actual lot multiplier when known.
- `atm_iv` is decimal annualized IV, e.g. `0.14` for 14%.
- `days_to_expiry` is calendar days and may be fractional.

## Distinguish three objects

### Expiry payoff
Pure intrinsic payoff of the option legs at expiration.

### Expiry P&L
Expiry payoff minus/plus the entry premium cashflow. Requires entry prices.

### Current mark-to-market P&L
Depends on current option prices, not just spot. Do not reconstruct it from expiry payoff.

## If the screenshot is incomplete

Proceed with the geometry if strikes/quantities are readable. State that exact break-evens or max P&L require entry premiums. Do not let one missing premium block the entire market-risk analysis.
