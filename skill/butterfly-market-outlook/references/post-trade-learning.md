# Post-Trade Learning and Calibration

The live agent must remain deterministic and auditable. "Learning" means measuring past forecasts/rules and proposing reviewed changes; it does not mean silently modifying thresholds after a few trades.

## Episode schema

Store one record only after a trade is fully closed:

```json
{
  "trade_id": "local-non-sensitive-id",
  "symbol": "NIFTY",
  "entry_time_ist": "ISO-8601",
  "exit_time_ist": "ISO-8601",
  "expiry": "YYYY-MM-DD",
  "lower": 0,
  "center": 0,
  "upper": 0,
  "entry_credit": 0.0,
  "entry_rnd_median": 0.0,
  "entry_rnd_p_outside_wings": 0.0,
  "path_expected_center": null,
  "path_prob_inside_wings": null,
  "actual_expiry_or_exit_spot": 0.0,
  "actual_outside_wings": false,
  "realized_pnl_points": 0.0,
  "max_open_profit_points": null,
  "max_profit_giveback_points": null,
  "recentered": false,
  "recenter_incremental_pnl_points": null,
  "estimated_slippage_points": null,
  "actual_slippage_points": null,
  "dominant_exit_reason": "harvest|gamma|event|alignment|liquidity|other"
}
```

## What to measure

- centre forecast absolute error;
- frequency and severity of tail misses;
- Brier score only for **explicit real-world probabilities**;
- RND wing-mass frequency as a pricing diagnostic, not a claim that it should calibrate one-for-one to physical outcomes;
- execution slippage versus estimate;
- profit give-back after maximum open P&L;
- recenter incremental P&L only when a defensible counterfactual is available;
- performance by days-to-expiry and regime.

## Threshold changes

Do not revise live gates from isolated outcomes. Require:
- a meaningful sample across regimes;
- evidence that a rule is systematically miscalibrated;
- an explicit human-approved change;
- regression tests against historical episodes before packaging a new skill version.

Run:

```bash
python scripts/summarize_trade_log.py --input episodes.jsonl --pretty
```
