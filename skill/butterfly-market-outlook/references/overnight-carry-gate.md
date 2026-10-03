# Overnight Carry Gate — Engine v2.4

This retained generic calculation module runs only when reached by the current
[decision controller](decision-algorithm.md); its generation label does not replace
v2.6 gate precedence. For Aryan, the [personal covenant](https://github.com/ayyararyan/volarb/blob/main/docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md)
requires intraday-only trading and flat by 15:00 IST. These generic diagnostics
cannot authorize overnight carry or entry/recenter after the deadline.

Use this gate after the v2.4 market-regime classifier whenever a butterfly will remain open across a period in which the home option market is closed and the next actionable exit is in a later session. It is mandatory when <=2 trading sessions remain to expiry and especially for a new entry/recenter/rotation into next-session expiry.

The objective is not to ban overnight carry. The v2.4 regime state determines how demanding this gate must be. It is to price the thing actually being traded: **next-actionable-exit MTM under gap, volatility and execution stress**, plus broker/RMS feasibility. Headline theta is considered only after these gates pass.

## Core principle

Overnight theta is compensation for a period in which the position cannot be dynamically managed. Therefore:

`large theta != attractive carry`

Evaluate:

`next-open carry reward vs joint gap + IV + execution + broker-liquidation risk`

Do not treat expiry payoff geometry as the primary horizon when the intended exit is the next market open.

## Activation

Set `overnight_carry.active = true` when all are true:

- the position/candidate crosses the home-market close;
- the next intended or realistically actionable exit is in a later session; and
- the structure remains short gamma over that interval.

The gate is **mandatory** when either:

- <=2 trading sessions remain to expiry; or
- a new fly/recenter/rotation is being opened after 14:30 IST for a next-session exit.

For post-close reviews, the market is already non-actionable. Internally label the state `LOCKED_OVERNIGHT`; do not interpret a post-close review as fresh evidence that the earlier carry decision was correct.

## 1. Next-actionable-exit horizon

Record:

- decision timestamp;
- market close timestamp;
- next actionable exit timestamp;
- hours in the untradeable window;
- time remaining to expiry at that next exit;
- whether settlement/expiry occurs the same session.

If the user intends to close around the next open, optimize the distribution of `PnL_next_open`, not primarily `PnL_expiry`.



## 1A. Regime-adjusted thresholds

Supply the output of `scripts/classify_market_regime.py` as `market_regime`. Apply its threshold parameters before ordinary overnight stress rules:

- `CALM_CARRY`: baseline OCR and gap-buffer thresholds;
- `TRANSITION`: require `OCR_1_5 >= 1.0` and recent p90 gap < 80% of nearest break-even buffer;
- `LATENT_JUMP_RISK`: block new expiry-eve carry; existing carry requires `OCR_1_5 >= 1.25` and p90 gap < 65% of nearest break-even buffer;
- `ACTIVE_STRESS`: block new expiry-eve carry; existing carry requires `OCR_1_5 >= 1.50` and p90 gap < 50% of nearest break-even buffer;
- `UNKNOWN`: block a new expiry-eve carry.

A low VIX does not relax these rules when the regime classifier detects latent event/tail risk.

## 2. Recent realized-gap regime gate

Before endorsing an actionable overnight carry, measure the **recent close-to-next-open gap distribution** for the same underlying.

Use a rolling window of roughly **20-30 trading opens** when available; require at least **15 observations** for a new entry/recenter/rotation. Define each observation as:

`gap_pct = 100 * (next_open - prior_close) / prior_close`

Track:

- median, 80th-percentile and 90th-percentile absolute gap;
- frequency of absolute gaps >= 0.50%;
- 90th-percentile gap converted to current index points;
- distance from **current spot** to the nearest expiry break-even, not merely body-to-break-even distance;
- local expected gap-gamma drag `0.5 * |Gamma| * E[gap_points^2]` when reliable actual-leg net gamma is available;
- `gap_gamma_burden = expected_gap_gamma_drag / same_state_next_open_harvest`.

Default rules:

- missing/insufficient recent gap history -> **BLOCK a new overnight entry/recenter/rotation**;
- current spot already outside the nearest break-even -> **BLOCK**;
- recent 90th-percentile absolute gap >= current-spot-to-nearest-break-even buffer -> **BLOCK**;
- expected local gap-gamma drag >= same-state next-open harvest -> **BLOCK**;
- 90th-percentile gap at 80-100% of the break-even buffer -> warning / strong exit bias;
- gap-gamma burden at 60-100% -> warning;
- >=15% of recent opens with |gap| >= 0.50% -> elevated-gap-regime warning.

This gate deliberately uses recent realized opens as a **regime screen**, not as a forecast that the next gap will equal a historical percentile. It complements, and never replaces, the full joint gap/IV repricing grid below. Do not estimate large-move P&L from local gamma alone.

## 3. Mandatory joint stress grid

For expiry-eve overnight carry, full-reprice the actual four legs at the next actionable exit under at least:

- spot gap: `+/-1.0 * current ATM straddle`;
- spot gap: `+/-1.5 * current ATM straddle`;
- spot gap: `+/-2.0 * current ATM straddle`.

Default volatility multipliers when no better event-specific stress is available:

- 1.0-straddle gap: ATM IV x 1.20;
- 1.5-straddle gap: ATM IV x 1.40;
- 2.0-straddle gap: ATM IV x 1.60.

These are deterministic stress states, not probabilities. Replace them with better empirically grounded joint spot/volatility stresses when available, but do not omit the +/-1.5 and +/-2.0 states.

Also reprice a `same_state_open` case with spot and IV unchanged to estimate harvest actually available by the intended next exit.

For large moves, do **not** extrapolate only with local gamma. Use full four-leg repricing from leg IVs whenever possible. If full repricing is impossible, classify the overnight gate as `DEGRADED`; a new expiry-eve entry cannot pass solely on a local Greek approximation.

## 4. Stress economics

Define:

- `H_open` = same-state P&L available by the next actionable exit;
- `L_1_5` = worst loss under the +/-1.5-straddle joint spot/IV stress;
- `L_2_0` = worst loss under the +/-2.0-straddle joint spot/IV stress;
- `OCR_1_5 = max(H_open,0) / max(L_1_5, epsilon)`.

Use these default diagnostics:

- `OCR_1_5 >= 1.0`: strong stress efficiency;
- `0.5 <= OCR_1_5 < 1.0`: only eligible in a benign event regime with validated broker feasibility;
- `OCR_1_5 < 0.5`: reject new expiry-eve overnight entry/rotation; for an existing actionable position, strong exit bias.

Do not interpret `OCR_1_5` as expected value. It is a reward-versus-stress diagnostic.

If explicit real-world opening scenario probabilities are defensible, compute probability-weighted next-open P&L separately. Do not assign probabilities to the mandatory stress grid merely to manufacture an expected value.

## 5. Event-latency gate

Source event severity from the normalized `market-news-signal-filter` packet described in `news-signal-integration.md`. Reuse the same packet that fed the regime classifier; do not independently rescore the raw article set.

An event is **latency-critical** when it can materially change the index path after the home option market closes and before the next actionable exit.

Examples:

- major U.S. macro releases;
- central-bank decisions/speeches with material rates implications;
- major geopolitical/oil events;
- policy announcements or elections with likely overnight transmission;
- material index-heavyweight news released after local close.

Classify each as `low / medium / high / critical` using the child packet's calibrated gap risk, butterfly relevance, overnight relevance, and timing. Record whether it occurs inside the untradeable window. A low-credibility rumor may still be high latency hazard if its attention/uncertainty channel is material; preserve the child skill's distinction between truth confidence and movement hazard.

Rules:

- `UNAVAILABLE/INVALID` news filter on a new overnight entry/recenter/rotation -> **BLOCK**;
- `STALE_CALIBRATION` -> warning and lower confidence; require live cross-asset confirmation but do not treat staleness alone as proof of danger;
- `high/critical` latency event + no full next-open repricing -> **BLOCK overnight entry/rotation**;
- `high/critical` latency event + `OCR_1_5 < 1.0` -> **BLOCK overnight entry/rotation**;
- `medium` latency event + `OCR_1_5 < 0.5` -> **BLOCK overnight entry/rotation**;
- do not call the regime benign merely because the event has not happened yet.

A post-close event review updates contingency planning only; it cannot retroactively make the original carry decision safer.

## 6. Broker / RMS feasibility gate

The theoretical defined-risk payoff is not enough. Model whether the broker can force liquidation before the intended exit.

Track:

- broker feasibility status: `PASS / UNKNOWN / WARN / FAIL`;
- authoritative current margin requirement when available;
- available margin/headroom;
- any expiry-day margin uplift or hedge-benefit change;
- any broker auto-squareoff / RMS warning;
- whether a stressed move could create a margin shortfall before manual exit.

Hard rules:

- explicit broker auto-squareoff/RMS warning -> `WARN` or `FAIL`; if the market is actionable, prefer **SQUARE OFF** unless the warning is demonstrably resolved;
- known insufficient margin / forced-liquidation condition -> **FAIL**;
- a **new** expiry-eve overnight entry/recenter/rotation requires broker status `PASS`; `UNKNOWN` is not enough;
- an existing position with broker status `UNKNOWN` is at least `DEGRADED`; do not call overnight carry operationally safe.

Do not infer the broker's exact liquidation rule from generic exchange margin concepts. Use authoritative broker data/warnings when available.

## 7. Candidate gate precedence

For a new expiry-eve overnight candidate or rotation:

1. data health must pass;
2. market regime must be classified and eligible;
3. recent realized-gap history must pass the empirical gap gate;
4. broker/RMS feasibility must be `PASS`;
5. latency-critical events must pass the event gate;
6. mandatory next-open full-reprice stress must pass;
7. only then may theta/carry and Pareto ranking choose among survivors.

A candidate rejected by this gate must not re-enter the ranking because it has unusually high theta.

## 8. Existing-position rule

Before local close, an existing position that fails the overnight gate should normally be squared off rather than knowingly entering the untradeable window.

After local close, no executable decision exists. Internally set:

`operational_state = LOCKED_OVERNIGHT`

and prepare the next-open contingency map. Do not label the post-close state a fresh `CARRY` decision.

At the next open, the ordinary expiry-exit algorithm resumes with live forward, surface, broker state and liquidity.

## 9. Deterministic helper

For a prepared overnight snapshot run:

```bash
python scripts/evaluate_overnight_carry.py --input overnight_snapshot.json --pretty
```

For candidate search, `scripts/optimize_butterflies.py` v2.4 automatically applies the mandatory next-open stress and candidate rejection logic when an `overnight_carry` object is supplied.

## 10. Logging / calibration

Persist, when known:

- next-actionable-exit horizon;
- untradeable-window duration;
- recent gap sample size, p80/p90 absolute gap, >=0.50% gap frequency, break-even-buffer ratio and gap-gamma burden;
- Market News Signal Filter calibration as-of/status, aggregate state and dominant channels;
- event-latency classification;
- broker feasibility status and warning presence;
- same-state next-open harvest;
- +/-1.0, +/-1.5, +/-2.0 straddle joint stress P&Ls;
- `OCR_1_5`;
- actual next-open state and forecast error after the trade closes.

Do not change thresholds from a single episode. Test structural changes across prior episodes and synthetic regimes before promotion.
