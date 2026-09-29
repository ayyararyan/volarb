---
name: intraday-realized-volatility-forecast
description: Forecast 15-30 minute physical realized volatility for NIFTY, BANKNIFTY, or SENSEX from a fresh approximately five-minute high-frequency futures/price observation block, separating continuous spot volatility, recent jump pressure, exogenous event risk, and directional/centre drift before comparing the forecast with option-implied volatility. Use when an intraday short-gamma or butterfly decision depends on whether forecast RV is likely to remain below IV over the next review interval. Do not use prior-day RV averages, HAR/GARCH calibration, or long-run historical data as the live forecast input.
---

# Intraday Realized Volatility Forecast

Forecast **physical realized volatility over the next 15-30 minutes** from a fresh local high-frequency state estimate, then compare it with current option-implied volatility and diagnose centre drift separately.

This skill is designed for intraday short-gamma decisions. It is a live state forecaster, not a historical-volatility lookup.

## Prime rules

1. Use a fresh high-frequency observation block, normally about 5 minutes, as the primary live input.
2. Prefer liquid index futures mids/efficient prices sampled every 1-2 seconds and internally aggregate/pre-average to roughly 5-second observations.
3. Never let whole-session OHLC, prior-day RV, HAR/GARCH, or long-run averages produce an actionable `FAVOURABLE` state.
4. Estimate the **current physical volatility state independently of absolute IV**. Compare with IV only after the physical forecast exists.
5. Separate continuous volatility, endogenous recent-jump pressure, exogenous event/jump risk, and drift. Do not collapse them into one number prematurely.
6. A recent jump does not imply another jump with certainty. Treat it as evidence of an elevated conditional volatility/jump state and decay its influence through time.
7. Treat futures/parity forward as carry/arbitrage references. Use their migration, not their level, as a centre-stability diagnostic.
8. If the high-frequency block is incomplete or noisy, return `INSUFFICIENT_HF_DATA` or low confidence rather than inventing precision.
9. The parent butterfly skill owns geometry, liquidity, margin, break-even and final trade decisions.

Read `references/methodology.md` before forecasting. Read `references/input-output-schema.md` before constructing script input. Read `references/research-basis.md` when explaining or modifying the model.

## Live workflow

### 1. Set the management horizon

Use the actual interval until the next intended review/exit, normally:

- 15 minutes for very near-expiry/high-gamma exposure;
- 20-30 minutes for standard intraday butterfly management.

Do not substitute time-to-expiry for the management horizon.

### 2. Build a five-minute HF observation block

Prefer approximately 5 minutes of:

- liquid near-month futures bid/ask midpoint or robust last price;
- 1-2 second polling/streaming frequency when available;
- at least 40 usable 5-second aggregated price points after cleaning.

At the start and end of the observation block also capture the relevant option-surface state when available:

- spot;
- parity forward;
- ATM IV and ATM straddle;
- RND median and mode;
- current normalized Market News Signal Filter packet.

If the available connector can only provide isolated snapshots or session OHLC and cannot supply a genuine HF block, do **not** approve a new short-gamma trade from this skill.

### 3. Run the deterministic HF forecaster

```bash
python scripts/forecast_intraday_rv.py --input snapshot.json --pretty
```

The script:

1. cleans raw HF quotes and uses mid prices when bid/ask are available;
2. aggregates noisy raw observations to approximately 5-second buckets;
3. estimates slow local continuous variance over the full observation window;
4. estimates a fast spot-volatility state over the most recent 60-90 seconds;
5. separates jump-like returns from continuous variation using a robust threshold/bipower diagnostic;
6. projects the fast state toward the slow state over the 15-30 minute horizon using short-horizon volatility persistence;
7. carries recent jump variation forward as a decaying **jump-pressure reserve** rather than pretending to know the exact probability of another jump;
8. produces continuous and jump-adjusted physical RV forecasts plus an upper risk band.

### 4. Diagnose drift separately

Use the same HF block plus start/end surface snapshots to calculate:

- directional efficiency;
- net displacement in current-volatility sigma units;
- price/futures displacement in ATM-straddle units;
- parity-forward migration / ATM straddle;
- RND median migration / ATM straddle as a primary centre diagnostic;
- RND mode migration as a separate corroborative bucket-warning only.

Classify drift risk `LOW / MEDIUM / HIGH`. Never let an isolated RND-mode bucket jump create `HIGH` drift; mode may corroborate but not independently trigger the hard drift gate.

Low forecast RV does **not** justify a butterfly if the centre is migrating.

### 5. Apply exogenous event override

Consume one normalized `market-news-signal-filter` packet for the forecast horizon.

Set a hard event override for high/critical near-horizon latency risk, `TAIL_RISK_ACTIVE`, critical butterfly relevance, or a newly unpriced event capable of discontinuous repricing.

Price-series jump pressure and news/event jump risk are separate inputs.

### 6. Compare physical RV with implied volatility

Prefer a model-free implied-variance anchor from the parent workflow when available; otherwise use current ATM IV for the relevant expiry.

Compare **horizon-integrated variance**, not only annualized headline vol:

- forecast continuous variance over the next H minutes;
- jump-adjusted forecast variance;
- conservative upper forecast variance;
- IV-implied variance over the same H minutes.

Also report annualized equivalents for readability.

### 7. Produce both HF regime and short-gamma state

Use one HF regime state:

- `QUIET_EDGE` — jump-adjusted upper RV remains below IV, drift low, no event override;
- `VOL_EDGE_WITH_JUMP_RISK` — continuous edge exists but recent jump pressure remains material;
- `DRIFTING` — centre/path migration is too directional;
- `RV_TOO_HIGH` — physical RV forecast consumes or exceeds IV;
- `EVENT_RISK` — exogenous near-horizon jump risk dominates;
- `INSUFFICIENT_HF_DATA` — five-minute block is inadequate.

For parent compatibility also return one short-gamma state:

- `FAVOURABLE` — actionable HF data, robust IV-over-jump-adjusted-RV edge, LOW drift, no event override, and no self-exciting jump state;
- `MARGINAL` — central edge exists but jump pressure, uncertainty, developing events or MEDIUM drift weaken it;
- `UNFAVOURABLE` — RV >= IV, HIGH drift, or event override;
- `INSUFFICIENT_DATA` — HF acquisition/quality gate fails.

## Parent butterfly integration

For a **new intraday butterfly**, the parent engine should require `short_gamma_state = FAVOURABLE` before candidate theta/gamma ranking.

For an **existing intraday butterfly**:

- a medium/high-confidence `UNFAVOURABLE` state is an exit-level volatility/path signal;
- `MARGINAL` is a warning and should shorten the next review cadence;
- `INSUFFICIENT_DATA` must not force an exit by itself; fall back to the parent risk gates.

Never let attractive theta override a failed HF RV/drift gate.

## Learning and validation

Persist at each actionable forecast:

- HF observation span and sample quality;
- continuous RV forecast;
- jump-adjusted RV forecast and upper band;
- IV anchor and horizon-integrated IV variance;
- fast/slow variance ratio;
- jump count/share/pressure state;
- drift diagnostics;
- short-gamma state.

After the exact forecast horizon elapses, record realized variance over that interval and the realized centre migration. Use these only for later human-reviewed calibration; do not silently retune parameters from a handful of forecasts.

---
To read any file's contents, use `functions.exec` to run `text(await tools.skills__read({"uri": "skills://intraday-realized-volatility-forecast/<relative_file_path>"}))`.
Read once per file. Available relative file paths:

SKILL.md
agents/openai.yaml
assets/icon.svg
references/input-output-schema.md
references/methodology.md
references/research-basis.md
scripts/forecast_intraday_rv.py
scripts/test_stable.json
scripts/test_jump.json
scripts/test_trend.json
