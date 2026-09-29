# Post-Trade Learning and Calibration — v2.5

The live agent must remain deterministic and auditable. "Learning" means measuring forecast/rule performance and proposing reviewed changes; it does not mean silently modifying thresholds after a few trades.

## Episode additions

For every fully closed trade, preserve the existing execution/P&L fields and add the following when available.

```json
{
  "entry_regime": null,
  "entry_break_even_to_straddle": null,
  "entry_forward_to_body_straddles": null,
  "entry_rnd_median_to_body_straddles": null,
  "intraday_rv_entry": {
    "horizon_minutes": null,
    "hf_quality": null,
    "continuous_rv_forecast_ann": null,
    "jump_adjusted_rv_forecast_ann": null,
    "upper_rv_forecast_ann": null,
    "implied_vol_anchor_ann": null,
    "forecast_sigma_move_points": null,
    "upper_forecast_sigma_move_points": null,
    "fast_slow_variance_ratio": null,
    "jump_state": null,
    "jump_pressure_variance": null,
    "drift_risk": null,
    "directional_efficiency": null,
    "center_migration_straddles": null,
    "mode_migration_straddles": null,
    "mode_bucket_warning": null,
    "short_gamma_state": null,
    "confidence": null
  },
  "max_observed_open_profit_points": null,
  "max_observed_open_loss_points": null,
  "max_profit_giveback_points": null,
  "max_spot_excursion_straddles": null,
  "max_forward_excursion_straddles": null,
  "max_rnd_center_migration_straddles": null,
  "minimum_break_even_to_straddle": null,
  "realized_variance_over_forecast_horizon": null,
  "rv_forecast_error_variance": null,
  "recentered": false,
  "recenter_incremental_pnl_points": null,
  "dominant_exit_reason": "harvest|gamma|event|alignment|liquidity|broker|rv|drift|other"
}
```

Use **maximum observed** profit/loss unless a continuous broker history proves the true extrema.

## Forecast validation

For each HF RV forecast that has an exact horizon:

1. freeze the forecast at timestamp `t`;
2. after horizon `H` elapses, calculate realized variance only over `[t, t+H]`;
3. record forecast central/upper variance and realized variance;
4. record whether the realized path contained a detected jump and the realized centre migration;
5. never use the subsequent realized outcome as an input to the original forecast.

Measure over time:

- central RV forecast bias/error;
- upper-band exceedance frequency;
- error conditional on `QUIET`, `RECENT_JUMP`, and `SELF_EXCITING` states;
- error conditional on fast/slow variance ratio;
- performance by index and DTE;
- P&L by entry `short_gamma_state`, drift state and BE/straddle ratio;
- profit give-back after maximum observed open P&L;
- execution slippage versus estimate;
- recenter incremental P&L only with defensible counterfactuals.

## Threshold changes

Do not revise live gates from isolated outcomes. Require:

- a meaningful forecast/trade sample across regimes and indices;
- evidence of systematic miscalibration;
- explicit human approval;
- regression tests before packaging a new skill version.

Do not conclude that one index is structurally superior from a tiny sample; let its live RV/IV/drift state determine eligibility.
