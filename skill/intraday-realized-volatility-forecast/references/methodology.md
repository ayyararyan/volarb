# Methodology

## Objective

Estimate the **current local physical variance state** from a fresh approximately five-minute high-frequency block and forecast integrated realized variance over the next 15-30 minutes.

The design deliberately avoids multi-day historical calibration in the live forecast. The forecast relies on short-horizon persistence of the state observed now, with explicit handling of recent jumps, drift and exogenous event risk.

## 1. HF observation block

Preferred source: liquid near-month index futures midpoint.

Recommended raw sampling:

- 1-2 second quotes when available;
- aggregate/pre-average to 5-second buckets;
- about 5 minutes total observation time;
- require at least 40 usable aggregated prices and roughly 4.5 minutes of coverage for an actionable forecast.

Use median/midpoint aggregation within each bucket to reduce bid/ask bounce. Avoid naive tick-by-tick RV.

### HF quality gate

Classify the HF block:

- `PASS`: span >= 270 seconds, >=40 aggregated prices, median inter-bucket gap <=7.5 seconds, p90 gap <=12 seconds, max gap <=20 seconds;
- `DEGRADED`: span >=240 seconds, >=30 aggregated prices, max gap <=30 seconds;
- `FAIL`: otherwise.

Only `PASS` or a strong `DEGRADED` block can support an actionable new-entry signal. Session OHLC can produce diagnostics only.

## 2. Continuous variance state

Let the cleaned aggregated log returns be `r_i`, with elapsed minutes `dt_i`, and normalized return `u_i = r_i / sqrt(dt_i)`.

### Robust local scale and jump threshold

Estimate a robust scale of `u_i` using MAD, falling back to the median-square estimator when MAD degenerates.

Set the operational jump threshold to approximately four robust standard deviations:

`|u_i - median(u)| > 4 * robust_scale`.

This is a conservative operational threshold, not a claim of an optimal jump test.

### Slow state

Over the full approximately five-minute block compute continuous-variation diagnostics using non-jump returns:

- threshold realized-variance rate;
- thresholded bipower-variation rate;
- robust median variance rate.

Use the median of valid continuous estimators as `v_slow`.

### Fast state

Over the most recent 60-90 seconds, estimate `v_fast` from the same continuous-return logic.

Interpret:

- `v_fast / v_slow >> 1`: volatility acceleration;
- approximately 1: locally stable volatility state;
- materially below 1: recent deceleration.

## 3. Short-horizon persistence forecast

Model the future continuous variance state operationally as:

`v(u) = v_slow + (v_fast - v_slow) * exp(-u / tau_v)`.

Default persistence time:

`tau_v = clamp(horizon_minutes / 2, 5, 20)`.

This parameter is an explicit operational prior, not historically fitted.

Integrated continuous variance over horizon `H` is:

`IVAR_cont = v_slow*H + (v_fast-v_slow)*tau_v*(1-exp(-H/tau_v))`.

Use the lower and upper local continuous estimators to form a transparent uncertainty range.

## 4. Recent jump pressure

Identify jump-like returns from the robust threshold.

Let jump squared returns be `q_j = r_j^2` and their current ages in minutes be `a_j`.

Define a decaying jump-pressure variance reserve:

`JP0 = sum(q_j * exp(-a_j/tau_J)) / observation_minutes`

`JP_H = JP0 * tau_J * (1-exp(-H/tau_J))`.

Default `tau_J = 30 minutes`.

Interpret jump state:

- `QUIET`: no detected jumps;
- `RECENT_JUMP`: one material detected jump;
- `SELF_EXCITING`: two or more detected jumps in the five-minute block, or otherwise clearly clustered jump activity.

The jump-pressure reserve is **not** a literal jump probability. It is a conservative continuation allowance motivated by evidence that jumps and post-jump volatility can cluster.

Construct:

- jump-adjusted central variance = continuous forecast + 0.5*JP_H for `RECENT_JUMP`;
- jump-adjusted central variance = continuous forecast + JP_H for `SELF_EXCITING`;
- upper forecast variance = continuous upper forecast + JP_H.

## 5. Annualization and horizon move

Indian cash-market annual minutes:

`252 * 375`.

For an integrated horizon variance `V_H` over `H` minutes:

`vol_ann = sqrt((V_H / H) * annual_minutes)`.

Forecast one-sigma horizon move:

`move_points = spot * sqrt(V_H)`.

## 6. Drift / centre stability

A butterfly needs low variance **and** a stationary centre.

### Directional efficiency

`DE = |sum(r_i)| / sum(|r_i|)`.

### Net displacement in sigma units

`Z_move = |log(P_now/P_start)| / sqrt(v_slow * observed_minutes)`.

### Price displacement in straddle units

`D_straddle = |P_now-P_start| / ATM_straddle`.

### Surface-centre migration

For parity forward, RND median and timestamp-aligned futures snapshots:

`migration = |C_now-C_start| / current_ATM_straddle`.

Define `center_migration_straddles` as the maximum valid migration across these **primary continuous centre measures**.

Track RND mode separately as `mode_migration_straddles`. The mode is an argmax on a discrete strike grid and can jump one strike after a very small change in local density. Therefore:

- RND mode migration is corroborative evidence only;
- a large mode-bucket shift by itself may set `mode_bucket_warning=true`;
- RND mode migration alone must **never** create `HIGH` drift or an `UNFAVOURABLE` short-gamma state;
- forward, RND median, futures/price migration and the HF path diagnostics remain the hard drift evidence.

### Drift classification

`LOW` when all available diagnostics are mild:

- `Z_move <= 1.0`;
- `DE <= 0.60`;
- price displacement <=0.25 straddles;
- primary centre migration <=0.25 straddles.

`HIGH` when any is true:

- `Z_move >= 1.5`;
- `DE >= 0.80`;
- price displacement >=0.50 straddles;
- primary centre migration >=0.50 straddles.

Otherwise `MEDIUM`.

## 7. Exogenous event/jump override

The HF path cannot forecast information that has not yet arrived.

Consume the normalized Market News Signal Filter packet separately. Set an override for high/critical latency risk, critical butterfly relevance, `TAIL_RISK_ACTIVE`, or a newly unpriced decision-relevant event inside the horizon.

Do not infer event safety merely because the last five minutes were quiet.

## 8. IV comparison

Keep physical forecast and Q-measure IV separate until this stage.

Use model-free implied volatility when the parent supplies it; otherwise use current ATM IV.

For horizon `H`:

`IVAR_Q_H = IV_anchor^2 * H / annual_minutes`.

Compare:

- continuous forecast variance;
- jump-adjusted central forecast variance;
- upper jump-adjusted forecast variance;
- implied horizon variance.

Define robust edge only when:

`upper_jump_adjusted_forecast_variance < implied_horizon_variance`.

## 9. Decision state

`FAVOURABLE` requires:

- actionable HF quality;
- upper jump-adjusted RV < implied variance;
- LOW drift;
- no exogenous event override;
- confidence medium/high;
- jump state not `SELF_EXCITING`.

`MARGINAL` applies when central edge exists but uncertainty, MEDIUM drift, developing event state, or material jump pressure weakens conviction.

`UNFAVOURABLE` applies when central jump-adjusted RV >= IV, drift HIGH, or event override is active.

`INSUFFICIENT_DATA` applies when the HF block fails the acquisition/quality gate.

## 10. No-action fallback

Session OHLC or sparse 1-5 minute snapshots may still be used for descriptive diagnostics, but they must never produce a new-entry `FAVOURABLE` state.
