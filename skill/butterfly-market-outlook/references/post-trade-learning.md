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
  "dominant_exit_reason": "harvest|gamma|event|alignment|liquidity|broker|other",
  "news_filter": {
    "calibration_asof": null,
    "calibration_status": null,
    "aggregate_state": null,
    "dominant_channels": [],
    "max_gap_risk": null,
    "max_butterfly_relevance": null,
    "max_latency_severity": null
  },
  "overnight_carry": {
    "next_actionable_exit_ist": null,
    "untradeable_window_hours": null,
    "broker_feasibility": null,
    "broker_auto_squareoff_warning": null,
    "max_latency_event_severity": null,
    "same_state_open_pnl_points": null,
    "worst_1_5_straddle_open_pnl_points": null,
    "worst_2_0_straddle_open_pnl_points": null,
    "ocr_1_5": null,
    "actual_open_gap_in_prior_straddles": null
  }
}
```

## What to measure

- centre forecast absolute error;
- child news-filter hazard bucket versus realized opening-gap percentile, without changing the original information-quality labels;
- frequency and severity of tail misses;
- Brier score only for **explicit real-world probabilities**;
- RND wing-mass frequency as a pricing diagnostic, not a claim that it should calibrate one-for-one to physical outcomes;
- execution slippage versus estimate;
- profit give-back after maximum open P&L;
- recenter incremental P&L only when a defensible counterfactual is available;
- performance by days-to-expiry and regime;
- overnight next-open forecast error, gap in prior-close straddle units, event-latency misses, and broker/RMS warning frequency when the v2.4 overnight gate was active.

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
