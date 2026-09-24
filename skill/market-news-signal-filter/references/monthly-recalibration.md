# Monthly Recalibration Protocol

## Goal

Refresh how strongly Indian indices respond to news channels without allowing hindsight to contaminate information-quality judgments.

Run after each completed calendar month, preferably on the first analysis run after month-end. Use a rolling 252-trading-session window.

Persist only the updated parameter snapshot in `calibration.md`. Do not retain the raw news corpus or market dataset in the packaged skill.

## 1. Build the rolling market panel

For NIFTY, SENSEX, and BANKNIFTY collect daily:

- prior close;
- open;
- high;
- low;
- close;
- optionally India VIX, INR, Brent crude, US 10Y yield, and a broad US equity index for diagnostics.

Prefer official exchange/index-provider history when available. Cross-check suspicious rows and remove obvious bad prints, missing zeros, duplicate dates, and stale observations.

Compute:

- overnight gap = open_t / close_(t-1) - 1;
- close-to-close return = close_t / close_(t-1) - 1;
- open-to-close return = close_t / open_t - 1;
- normalized range = (high_t - low_t) / close_(t-1).

Re-estimate absolute gap and daily-move percentiles: 50, 75, 90, 95, and 99.

## 2. Freeze the information set before observing outcomes

For every session t, define the overnight news window as prior Indian cash close through the next pre-open/open.

For same-day events, preserve exact event timestamps and only evaluate market movement after the event.

Do not read the realized return before classifying the event set.

## 3. Build event clusters, not article counts

For the rolling year:

1. Gather market-relevant primary releases, wires, and high-quality reporting.
2. Cluster duplicates and syndicated copies into one event.
3. Extract a fact spine.
4. Score the event with the standard rubric.
5. Map to transmission channels.
6. Save the temporary calibration record only for the duration of the refresh.

The refresh should cover all material market-relevant event clusters, but not every low-value article on the internet. Stale commentary and duplicates remain controls/noise rather than additional observations.

## 4. Include quiet controls

Do not train only on crash/rally days.

Retain sessions where:

- news was apparently dramatic but the market barely reacted;
- a scheduled event was largely priced in;
- no major news cluster existed;
- different channels offset each other.

These controls prevent selection bias and exaggerated multipliers.

## 5. Define normalized market response

For each index i and event window t:

- `gap_z = abs(gap) / rolling_Q90_abs_gap`
- `daily_z = abs(close_to_close) / rolling_Q90_abs_daily_move`
- `range_z = normalized_range / rolling_Q90_range`

For overnight calibration use:

`response = max(gap_z, 0.75 * daily_z, 0.50 * range_z)`

For a same-session event, replace gap_z with the post-event move scaled by a comparable intraday volatility benchmark when available.

This is a movement-hazard target. Do not use signed return unless calibrating direction separately.

## 6. Define the expected uncalibrated hazard

Let `H = max(fundamental_information, attention_hazard, uncertainty_hazard)`.

Map H to a neutral expected response relative to the 90th-percentile scale:

- H=0 -> 0.20
- H=1 -> 0.35
- H=2 -> 0.60
- H=3 -> 1.00
- H=4 -> 1.35

This mapping is only a calibration scaffold. Information scores themselves never change after seeing the outcome.

For each dominant channel, compute `response / expected_response`.

## 7. Attribute conservatively

Update a single-channel parameter only when that channel is dominant or attribution is reasonably clean.

When two or more independent material channels are aligned:

- update the interaction term;
- give only fractional weight to each standalone channel;
- do not pretend the full market move belongs to each channel.

When attribution is ambiguous, retain the observation for aggregate regime-state estimation but exclude it from channel-specific coefficient fitting.

## 8. Apply recency weights

Within the rolling 252-session window use:

- most recent 63 trading sessions: 50% total weight;
- sessions 64-126: 30% total weight;
- sessions 127-252: 20% total weight.

Normalize weights within each bucket. This permits adaptation without letting one dramatic week erase the longer baseline.

## 9. Estimate and shrink channel multipliers

For each channel/index pair:

1. Compute the recency-weighted median of `response / expected_response` across attributable events.
2. Let `n_eff` be the effective weighted number of independent event windows.
3. Shrink toward neutral sensitivity 1.00:

`shrunk = (n_eff / (n_eff + 12)) * raw + (12 / (n_eff + 12)) * 1.00`

4. Clamp structural channel multipliers to [0.65, 1.65].
5. Update smoothly:

`new_multiplier = 0.75 * old_multiplier + 0.25 * shrunk`

Use the faster regime-break rule below only when justified.

## 10. Detect a regime break

Compare recent 21-session response for a channel with its trailing 126-session response.

Mark channel state:

- `DORMANT`: recent normalized response <=0.65 of trailing baseline and at least 3 recent events.
- `NORMAL`: no meaningful shift.
- `HIGH`: recent response >=1.35 times trailing baseline and at least 3 recent events.
- `STRESSED`: recent response >=1.75 times trailing baseline, or at least two 95th-percentile market responses tied to the channel within 21 sessions.

For HIGH/STRESSED states, use:

`new_multiplier = 0.40 * old_multiplier + 0.60 * shrunk`

Still apply the [0.65, 1.65] structural cap. Interaction multipliers may raise total hazard above this, subject to the aggregate cap in `calibration.md`.

## 11. Validate before accepting the update

Check:

- whether the new multiplier improves ordering of quiet/moderate/tail event windows;
- whether a result depends on one outlier;
- whether a channel has at least 5 independent event windows before calling its coefficient medium confidence;
- whether the sign/direction story is economically coherent;
- whether a supposedly important event was actually published after the relevant market move.

Reject an update that relies on timestamp leakage, duplicate stories, bad price data, or circular attribution.

## 12. Save only compact parameters

Overwrite/update `calibration.md` with:

- calibration as-of date;
- price sample window and cleaned observation counts;
- movement percentiles;
- channel multipliers by index;
- channel regime states;
- interaction multipliers;
- confidence labels;
- at most a short list of representative event anchors explaining major parameter changes.

Do not save the raw one-year article corpus, full OHLC dataset, or every temporary event record inside the skill.
