# Market News Signal Filter Integration Contract

Use this module for every fresh butterfly outlook that requires current news, event, or cross-asset interpretation. The parent butterfly skill owns the trade decision; the child `market-news-signal-filter` skill owns raw-news interpretation and calibration.

## Prime rule

**Do not independently rescore raw news inside the butterfly skill when the Market News Signal Filter is available.**

The flow is:

`raw sources -> market-news-signal-filter -> normalized news packet -> butterfly regime/event/path gates -> controller action`

Invoke the child skill once for the relevant decision horizon and reuse the same packet across regime classification, overnight event latency, hard-event/tail checks, MarketState comparison, and logging. Do not call it separately from multiple gates using different source sets.

## Decision windows

- Intraday review/candidate: include only information available before the decision timestamp and relevant through the intended exit/review horizon.
- Overnight/carry review: freeze the primary news window from the prior Indian cash close, normally 15:30 IST, through the decision timestamp; also include scheduled events between the decision and the next actionable exit.
- Post-close: update contingency planning with new information, but never reinterpret a prior carry decision using hindsight.

## Child-skill output adapter

Normalize the child output into this internal object before it enters the butterfly engine:

```json
{
  "status": "CURRENT|STALE_CALIBRATION|UNAVAILABLE|INVALID",
  "calibration_asof": "YYYY-MM-DD|null",
  "aggregate_state": "CALM|NOISY_BUT_BENIGN|EVENTFUL|HIGH_UNCERTAINTY|TAIL_RISK_ACTIVE|UNKNOWN",
  "max_gap_risk": "none|low|moderate|high|extreme|unknown",
  "max_butterfly_relevance": "ignore|watch|material|critical|unknown",
  "max_overnight_relevance": "none|low|moderate|high|extreme|unknown",
  "max_latency_severity": "low|medium|high|critical|unknown",
  "dominant_channels": ["OIL_ENERGY"],
  "direction": "risk-on|risk-off|mixed|unknown",
  "events": [
    {
      "event": "one-sentence fact spine",
      "primary_class": "HARD_SIGNAL",
      "fundamental_information": 0,
      "attention_hazard": 0,
      "uncertainty_hazard": 0,
      "evidence_quality": 0,
      "novelty": 0,
      "transmission_channels": [],
      "sensitivity_state": "DORMANT|NORMAL|HIGH|STRESSED|UNKNOWN",
      "gap_risk": "none|low|moderate|high|extreme",
      "butterfly_relevance": "ignore|watch|material|critical",
      "overnight_relevance": "none|low|moderate|high|extreme",
      "inside_untradeable_window": false,
      "latency_severity": "low|medium|high|critical"
    }
  ]
}
```

Do not copy article bodies, headline dumps, or raw source lists into MarketState. Keep only the normalized event facts and calibration metadata needed for risk decisions.

## Adapter rules

### Calibration status

- `CURRENT`: child calibration is <=45 calendar days old.
- `STALE_CALIBRATION`: older than 45 days; usable only as a prior. Require stronger live cross-asset confirmation and lower confidence.
- `UNAVAILABLE`: child skill cannot be invoked or required child output is missing.
- `INVALID`: malformed/internally contradictory output.

For a new overnight entry/recenter/rotation, `UNAVAILABLE` or `INVALID` news filtering must force the market-regime input to `UNKNOWN`; the parent controller therefore blocks initiation. For an existing position, continue risk management conservatively with `UNKNOWN`/degraded news state rather than inventing a benign state.

A stale calibration alone does not prove danger. It lowers confidence and prevents the parent from treating old sensitivity coefficients as current facts.

### Latency severity

Map child outputs deterministically:

- `critical`: any event inside the untradeable window with `butterfly_relevance=critical` or `gap_risk=extreme`.
- `high`: material event with high gap/overnight relevance, or `TAIL_RISK_ACTIVE` with plausible overnight transmission.
- `medium`: watch/material developing event with moderate movement hazard.
- `low`: no material event inside the untradeable window.

Use the maximum across independent event clusters. Duplicate stories do not increase severity.

### Regime hazard

Feed the normalized child packet to `classify_market_regime.py` as `news_filter` and set `news_filter_required=true` for every actionable overnight decision.

The classifier maps aggregate state, gap risk, butterfly relevance, and explicit event hazards into one event-hazard contribution. It may tighten a regime but may never increase evidence quality or factual confidence because prices moved.

### Hard-event/tail gate

Use the child packet as the only news interpretation input. A child event can support the hard-risk override when all are true:

1. the event is credible enough for its class or is an explicitly preserved rumor/attention hazard;
2. calibrated butterfly relevance is `critical` or the aggregate state is `TAIL_RISK_ACTIVE`;
3. transmission is live for the target index/horizon; and
4. the event materially threatens a break-even/wing, produces unusable execution, or leaves the option surface stale to fresher price discovery.

Do not square off merely because a headline sounds alarming.

## Cross-asset usage

Oil, INR, global rates, global equities, and GIFT Nifty remain market observations, not independent news classifiers.

Use them to:

- confirm whether a child-identified transmission channel is active;
- detect whether the domestic option surface is stale to fresher price discovery;
- set path scenarios and stress states.

Do not use cross-asset movement to retroactively upgrade a weak rumor into a hard fact.

## Monthly recalibration ownership

The child skill owns monthly news-to-market recalibration and stores its own current parameters. The butterfly skill must not duplicate or independently fit those coefficients.

On the first fresh outlook after a completed calendar month, if the child calibration has not been refreshed for that month, request/use its monthly recalibration workflow before relying on the coefficients for a new overnight structure when practical. If unavailable in a time-sensitive existing-position review, mark calibration stale and continue conservatively.

## Logging contract

Persist only compact fields:

- calibration as-of/status;
- aggregate news state;
- dominant transmission channels;
- max gap risk / butterfly relevance / latency severity;
- one-line fact spine for decision-critical events;
- actual subsequent gap/market response later for post-trade calibration.

Never dump the raw article corpus into the butterfly repository.
