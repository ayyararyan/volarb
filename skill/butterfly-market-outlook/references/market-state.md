# Canonical MarketState

Use one state object per decision pass. It is an internal contract between modules, not a user-facing artifact.

```json
{
  "meta": {
    "symbol": "NIFTY|BANKNIFTY|SENSEX",
    "expiry": "YYYY-MM-DD",
    "asof_ist": "ISO-8601",
    "mode": "open_position|candidate_search",
    "session": "preopen|open|postclose|overnight|weekend",
    "holding_horizon_hours": 24.0,
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
  "event_clock": [
    {
      "time_ist": "ISO-8601 or null",
      "kind": "scheduled|unscheduled",
      "name": "event",
      "severity": "low|medium|high|critical",
      "channels": ["equity", "oil", "fx", "rates"],
      "priced_by_surface": true,
      "inside_untradeable_window": false
    }
  ],
  "path": {
    "regime": "range_bound|choppy|directional_up|directional_down|event_jump|uncertain",
    "expected_center": null,
    "confidence": "low|medium|high",
    "scenarios": [
      {
        "label": "base",
        "spot": null,
        "probability": null,
        "iv_shift_vp": 0.0,
        "source": "judgmental|model|market"
      }
    ]
  },
  "overnight_carry": {
    "active": false,
    "operational_state": "ACTIONABLE|LOCKED_OVERNIGHT|null",
    "broker_feasibility": "PASS|UNKNOWN|WARN|FAIL|null",
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
  }
}
```

## Rules

- Populate only fields supported by current evidence; use `null`, not guesses.
- Keep RND fields and path scenario probabilities conceptually separate.
- A previous state may come from an earlier review in the same conversation. If unavailable, initialize without inventing history.
- Do not persist sensitive account identifiers in the state.
- Use `scripts/compare_market_states.py` when both previous and current states are available.
- A newly unpriced high/critical event combined with an `event_jump` regime must produce at least an elevated review state (normally <=30 minutes) unless the decision layer already chooses RECENTRE/SQUARE OFF/NO TRADE.
- If the intended hold crosses market close with <=2 sessions to expiry, populate `overnight_carry` and the next-actionable-exit horizon before theta/carry interpretation.
- A post-close open position has `operational_state=LOCKED_OVERNIGHT`; do not log a fresh executable carry decision while the home option market is closed.
