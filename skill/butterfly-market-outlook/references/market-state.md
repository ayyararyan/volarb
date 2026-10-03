# Canonical MarketState — current analytical state

Use one state object per decision pass. It is an internal contract between modules, not a user-facing artifact.
This nested analytical object is not the flat JSON input to
`scripts/decision_controller.py`. The orchestrator explicitly maps supported
evidence into the [v2.6 controller contract](decision-algorithm.md); missing fields
must not be inferred from permissive script defaults.

```json
{
  "meta": {
    "symbol": "NIFTY|BANKNIFTY|SENSEX",
    "expiry": "YYYY-MM-DD",
    "asof_ist": "ISO-8601",
    "mode": "open_position|candidate_search",
    "session": "preopen|open|postclose|overnight|weekend",
    "holding_horizon_hours": 0.5,
    "next_actionable_exit_ist": null,
    "untradeable_window_hours": null
  },
  "data_health": {
    "status": "HEALTHY|DEGRADED|STALE|INVALID",
    "surface_freshness": "live|stale_to_price_discovery|stale_to_news",
    "issues": [],
    "forward_source": "parity|exchange_future|input|spot_fallback",
    "parity_dispersion_points": null,
    "rnd_repair_fraction": null
  },
  "price": {
    "spot": null,
    "forward": null,
    "futures": null,
    "gift_nifty": null,
    "india_vix": null
  },
  "surface": {
    "atm_strike": null,
    "atm_iv": null,
    "atm_straddle": null,
    "rr25_vp": null,
    "bf25_vp": null,
    "local_skew_vp": null,
    "local_curvature_vp": null,
    "front_minus_next_atm_iv_vp": null,
    "rnd_q10": null,
    "rnd_median": null,
    "rnd_q90": null,
    "rnd_mode": null
  },
  "news_filter": {
    "status": "CURRENT|STALE_CALIBRATION|UNAVAILABLE|INVALID",
    "calibration_asof": null,
    "aggregate_state": "CALM|NOISY_BUT_BENIGN|EVENTFUL|HIGH_UNCERTAINTY|TAIL_RISK_ACTIVE|UNKNOWN",
    "max_gap_risk": "none|low|moderate|high|extreme|unknown",
    "max_butterfly_relevance": "ignore|watch|material|critical|unknown",
    "max_overnight_relevance": "none|low|moderate|high|extreme|unknown",
    "max_latency_severity": "low|medium|high|critical|unknown",
    "dominant_channels": [],
    "direction": "risk-on|risk-off|mixed|unknown"
  },
  "intraday_rv": {
    "status": "CURRENT|LOW_CONFIDENCE|INSUFFICIENT_HF_DATA|INVALID|null",
    "hf_quality": "PASS|DEGRADED|FAIL|null",
    "horizon_minutes": null,
    "continuous_rv_forecast_ann": null,
    "jump_adjusted_rv_forecast_ann": null,
    "upper_rv_forecast_ann": null,
    "implied_vol_anchor_ann": null,
    "forecast_horizon_variance": null,
    "upper_forecast_horizon_variance": null,
    "implied_horizon_variance": null,
    "forecast_sigma_move_points": null,
    "upper_forecast_sigma_move_points": null,
    "fast_slow_variance_ratio": null,
    "jump_state": "QUIET|RECENT_JUMP|SELF_EXCITING|null",
    "jump_pressure_variance": null,
    "drift_risk": "LOW|MEDIUM|HIGH|UNKNOWN|null",
    "directional_efficiency": null,
    "center_migration_straddles": null,
    "mode_migration_straddles": null,
    "mode_bucket_warning": null,
    "hf_regime_state": "QUIET_EDGE|VOL_EDGE_WITH_JUMP_RISK|DRIFTING|RV_TOO_HIGH|EVENT_RISK|INSUFFICIENT_HF_DATA|null",
    "short_gamma_state": "FAVOURABLE|MARGINAL|UNFAVOURABLE|INSUFFICIENT_DATA|null",
    "confidence": "low|medium|high|null"
  },
  "market_regime": {
    "state": "CALM_CARRY|TRANSITION|LATENT_JUMP_RISK|ACTIVE_STRESS|UNKNOWN",
    "confidence": "low|medium|high",
    "path_stress": null,
    "implied_stress": null,
    "event_hazard": null,
    "complacency_gap": null
  },
  "event_clock": [],
  "path": {
    "regime": "range_bound|choppy|directional_up|directional_down|event_jump|uncertain",
    "expected_center": null,
    "confidence": "low|medium|high",
    "scenarios": []
  },
  "overnight_carry": {
    "active": false,
    "market_regime_state": null,
    "operational_state": null,
    "broker_feasibility": null,
    "broker_auto_squareoff_warning": false,
    "same_state_open_pnl": null,
    "worst_1_0_straddle_open_pnl": null,
    "worst_1_5_straddle_open_pnl": null,
    "worst_2_0_straddle_open_pnl": null,
    "ocr_1_5": null
  },
  "position": {
    "lower": null,
    "center": null,
    "upper": null,
    "entry_credit": null,
    "close_cost": null,
    "net_delta": null,
    "net_gamma": null,
    "net_theta": null,
    "break_even_lower": null,
    "break_even_upper": null,
    "dynamic_harvest_saturation": null,
    "remaining_static_harvest": null
  },
  "decision": {
    "previous_action": null,
    "current_action": null,
    "dominant_reason": null,
    "next_review_ist": null
  },
  "controller_evidence": {
    "daily_loss_budget_rupees": null,
    "session_loss_rupees": null,
    "session_vrp_state": "FAVOURABLE|UNFAVOURABLE|UNKNOWN|null",
    "re_entry_after_square_off": null,
    "fresh_candidate_pass": null,
    "candidate_ids": [],
    "candidate_specs": {},
    "candidate_margin_checks": {},
    "recenter_margin_check": null
  }
}
```

## Rules

- Populate only evidence-supported fields; use `null`, not guesses.
- Populate `news_filter` once from `market-news-signal-filter`.
- Record loss-budget/session-VRP/re-entry evidence before candidate HF work. Preserve exact candidate/transition margin packets from `margin-affordability.md`; a status label is not sufficient evidence.
- For a fresh intraday candidate, populate `intraday_rv` from `intraday-realized-volatility-forecast` before candidate optimization.
- Session OHLC or sparse snapshots may not be represented as `intraday_rv.short_gamma_state=FAVOURABLE`.
- Keep RND, physical RV forecast and path scenario probabilities conceptually separate.
- For an intraday candidate, `UNFAVOURABLE`, `MARGINAL`, or `INSUFFICIENT_DATA` terminates new entry before theta ranking.
- For an existing intraday position, medium/high-confidence `UNFAVOURABLE` is exit-level; `MARGINAL` shortens review cadence.
- A previous state may come from an earlier review; never invent missing history.
- Do not persist sensitive account identifiers.
- Generic cross-close diagnostics populate the overnight fields; they never override the [personal covenant](https://github.com/ayyararyan/volarb/blob/main/docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md), which requires intraday-only exposure and flat by 15:00 IST.
