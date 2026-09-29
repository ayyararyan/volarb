# Input / output schema

## Script input

```json
{
  "symbol": "BANKNIFTY",
  "horizon_minutes": 30,
  "hf_quotes": [
    {"timestamp":"2026-09-29T13:45:00+05:30","bid":54290.0,"ask":54292.0},
    {"timestamp":"2026-09-29T13:45:02+05:30","bid":54291.0,"ask":54293.0}
  ],
  "surface_snapshots": [
    {
      "timestamp":"2026-09-29T13:45:00+05:30",
      "forward":54295.0,
      "futures":54291.0,
      "atm_straddle":250.0,
      "rnd_median":54300.0,
      "rnd_mode":54300.0
    },
    {
      "timestamp":"2026-09-29T13:50:00+05:30",
      "forward":54298.0,
      "futures":54296.0,
      "atm_straddle":246.0,
      "rnd_median":54300.0,
      "rnd_mode":54300.0
    }
  ],
  "current": {
    "spot": 54296.0,
    "atm_iv": 0.19,
    "atm_straddle": 246.0,
    "model_free_implied_vol": null
  },
  "session_ohlc": {
    "open": 54280.0,
    "high": 54400.0,
    "low": 54150.0,
    "current": 54296.0,
    "elapsed_minutes": 275
  },
  "news_filter": {
    "aggregate_state":"NOISY_BUT_BENIGN",
    "max_butterfly_relevance":"watch",
    "max_latency_severity":"low"
  },
  "config": {
    "bucket_seconds": 5,
    "observation_minutes": 5,
    "fast_window_seconds": 90,
    "jump_threshold_sigma": 4.0,
    "volatility_decay_minutes": 15,
    "jump_decay_minutes": 30
  }
}
```

## Field conventions

- Prefer bid/ask midpoint. If only `price` is supplied, use it.
- `hf_quotes` must belong to the current observation block only.
- Timestamps should be offset-aware ISO 8601.
- `atm_iv` and `model_free_implied_vol` use annualized decimal volatility, e.g. `0.19` for 19%.
- `surface_snapshots` need not be high frequency; start/end observations are sufficient for centre migration.
- `session_ohlc` is diagnostic fallback only and can never create an actionable favourable state.

## Script output

The script returns, among other diagnostics:

```json
{
  "hf_quality":"PASS|DEGRADED|FAIL",
  "hf_regime_state":"QUIET_EDGE|VOL_EDGE_WITH_JUMP_RISK|DRIFTING|RV_TOO_HIGH|EVENT_RISK|INSUFFICIENT_HF_DATA",
  "short_gamma_state":"FAVOURABLE|MARGINAL|UNFAVOURABLE|INSUFFICIENT_DATA",
  "continuous_rv_forecast_ann":0.0,
  "jump_adjusted_rv_forecast_ann":0.0,
  "upper_rv_forecast_ann":0.0,
  "implied_vol_anchor_ann":0.0,
  "forecast_horizon_variance":0.0,
  "upper_forecast_horizon_variance":0.0,
  "implied_horizon_variance":0.0,
  "jump_state":"QUIET|RECENT_JUMP|SELF_EXCITING",
  "jump_pressure_variance":0.0,
  "fast_slow_variance_ratio":0.0,
  "drift_risk":"LOW|MEDIUM|HIGH|UNKNOWN",
  "center_migration_straddles":0.0,
  "mode_migration_straddles":0.0,
  "mode_bucket_warning":false,
  "confidence":"low|medium|high"
}
```
