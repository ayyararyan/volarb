# Input / output schema

## Script input

```json
{
  "symbol": "BANKNIFTY",
  "asof": "2026-09-29T13:50:05+05:30",
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
    "jump_decay_minutes": 30,
    "max_hf_age_seconds": 120,
    "max_future_skew_seconds": 60,
    "max_surface_snapshot_gap_seconds": 900
  }
}
```

## Field conventions

- `asof` is the decision clock (offset-aware ISO 8601). If omitted the script uses the wall clock, so replaying an old block without `asof` correctly fails freshness. The newest HF quote must be within `max_hf_age_seconds` (default 120) of `asof` and not more than `max_future_skew_seconds` ahead of it; otherwise the result is `INSUFFICIENT_HF_DATA` with `diagnostics.freshness.reason` set to `HF_BLOCK_STALE` or `HF_TIMESTAMPS_AHEAD_OF_ASOF`.
- `news_filter` must be a normalized `market-news-signal-filter` packet. If it is missing, empty, or has `status` UNAVAILABLE/INVALID, the output reports `news_packet_status: "MISSING"` and `short_gamma_state` is capped at `MARGINAL`. A new entry is therefore impossible without a packet.
- `surface_snapshots` outside the HF window by more than `max_surface_snapshot_gap_seconds` are dropped; with fewer than two aligned snapshots the confidence is downgraded because centre migration is unobserved.
- A missing IV anchor returns `status: "INSUFFICIENT_DATA"` with `confidence: "low"`.
- Build the input from the office-Mac sampler evidence with `scripts/build_rv_input.py`.

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
  "status":"CURRENT|INSUFFICIENT_HF_DATA|INSUFFICIENT_DATA|LOW_CONFIDENCE",
  "asof":"...",
  "hf_newest_timestamp":"...",
  "hf_age_seconds":0.0,
  "news_packet_status":"PRESENT|MISSING",
  "hf_quality":"PASS|DEGRADED|FAIL|STALE",
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
