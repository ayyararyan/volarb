# NIFTY eSSVI + HAR-RV dashboard

Local dashboard: **http://127.0.0.1:8770/**. The minimal dark-mode view shows fitted ATM IV,
1/5/22-session HAR forecast RV, the 5-session Q ratio, and an interactive eSSVI
surface with expiry selection. Equations and coefficient tables are not displayed. All displayed values come from
broker observations or the fitted models, not demonstration data.

## Start / maintain

```sh
cd /path/to/essvi-dashboard
./start.command
```

The on-demand launcher validates/recovers Dhan Web authentication using the existing
local MCP implementation, privately updates only the two Dhan fields in external
`~/Documents/Market-Making-Secrets/broker.env`, fetches history, estimates HAR and
reuses an active NIFTY DAT stream if one is available. Otherwise, during the regular
session, it starts one read-only NIFTY collector until 15:30 IST. New collectors
request the nearest three expiries and up to 180 options. The initial launch reused
today's existing 120-option/two-expiry stream; it did not open another broker socket.

No credentials are stored in this project. State, historical candles, model
provenance and logs are in `~/.local/state/essvi-dashboard/`. Capture intentionally
uses the supported isolated local-storage lane; production archive settings are
unchanged. This launcher installs no scheduler or login service.

On this Mac the app uses the existing Shaurya research Python environment and data/
research packages, **not either old dashboard server**. `app.py` consumes canonical
DAT rows and owns a new `SurfaceEngine`, independently refitting every three seconds.
The server binds only to loopback. Its only endpoint besides local assets is a
read-only `/api/state`. At feed closure, the page stays up with explicit stale status.

To refresh just HAR history/model (the running app picks up the atomic file update):

```sh
"$HOME/Documents/Shaurya/research/.venv/bin/python" prepare.py
```

Forecasts are **not silently refitted on page refresh**. Run preparation after a
completed session for the following session's forecast. An intraday launch uses
the most recent completed session and forecasts the entire next session, including
any portion already elapsed. It is **not a remaining-day or 15–30-minute forecast**.
`./start.command --skip-history` reuses the explicitly dated saved HAR result.
An already occupied server port is detected before auth/data work.

## Research and model choice

### Data actually available

The old cache contained 17,740 one-minute observations, 8 July–11 September 2026,
with the last session partial. That was insufficiently current/long for the new
model. Dhan's documented intraday endpoint supports five years of active-instrument
history, in requests of at most 90 days. Using the existing private read-only
adapter, we retrieved two years of **NIFTY spot index 13 / IDX_I / INDEX five-minute
bars**, in <=80-day batches. No futures rolls or expired-option history are required.

[Dhan historical-data specification](https://dhanhq.co/docs/v2/historical-data/)

### Realized variance

Use regular 09:15–15:30 IST cash sessions with all **75 five-minute bars**. Timestamps
are interval-open; the 15:25 bar completes at 15:30. Include the first five-minute
return from the first open, then consecutive closes. Add the squared previous
session's last intraday close to today's open log return. Thus:

`RV_t = log(open_t / intraday_close_(t-1))² + sum_(j=1..75) log(P_j/P_(j-1))²`

The overnight component is a coarse jump proxy, not an observed overnight path.
NIFTY is an index, not an executable futures mid; this is an index-RV estimator.
Five-minute sampling reduces sensitivity to very-high-frequency noise, but the
sampling choice is not optimized here. Dhan daily history defines observed session
dates. Missing 5-minute bins, nonpositive prices, conflicting overlapping candles
and duplicate timestamps are never forward-filled. Nonstandard short sessions are
excluded. Rejected sessions remain missing in the session index: lag windows cannot
silently bridge them. Current incomplete sessions are not training targets.

### HAR

Corsi's heterogeneous daily/weekly/monthly structure is deliberately parsimonious.
Use a log-variance variant with **1, 5 and 22 trading-session** components:

`log RV_(t+1) = c + beta_d log RV_t + beta_w log(mean_5 RV)_t + beta_m log(mean_22 RV)_t + error`

Fit by OLS; obtain a positive expected-variance forecast by multiplying the
exponentiated fitted log value by the **training-only mean exponentiated residual**
(smearing correction). The headline is `sqrt(252 * forecast_variance)` as annualized
volatility; forecast variance in return² is available in its tooltip and the API. It is
the square root of predicted variance, not an estimate of expected square-root RV.
No IV, option premium, 10:00 anchor, or prior dashboard forecast enters this model.

[Corsi's original HAR working paper](https://realvol.com/HVOLPaper.pdf).
The maintained [arch HARX implementation](https://bashtage.github.io/arch/univariate/generated/arch.univariate.HARX.html)
was considered. This four-coefficient OLS implementation uses the already-installed
NumPy least-squares solver; a second modeling dependency is unnecessary. The
session-quality, lag alignment and retransformation checks are local and tested.

### eSSVI and interpretation

Reuse the existing constrained Shaurya eSSVI fitter: OTM bid/ask midpoints with ATM
included, per-expiry forward selection, no temporal smoothing and no strike
extrapolation. ATM IV is the fit evaluated at forward log-moneyness `k=0`, not a
broker-provided IV field. Numerical butterfly/calendar checks and stale-fit status
remain explicit. Numerical grid checks are not a proof over all possible strikes.

[Corbetta et al., calibration and arbitrage-free interpolation](https://arxiv.org/abs/1804.04924).
Plotly visually connects the displayed maturity slices; those connections are a
visual aid, not extra observed expiries.

The option IV uses the surface engine's calendar-time convention; HAR's displayed
vol uses 252 sessions/year. **Annualization does not equalize horizons**. Selected
expiry IV and one-session HAR are contextual side-by-side readings, not a matched
variance risk premium or trading signal. No spread or buy/sell indication is shown.

## Actual validation — 30 September 2026

- Historical session index: 496 completed sessions, 30 Sep 2024–29 Sep 2026.
- Valid daily variance observations: 491; five unavailable/rejected (including the
  initial day without a prior close). Missing windows leave 425 fitted HAR pairs.
- Final forecast is conditional on data through **29 Sep close**.
- Evaluation: last 60 eligible sessions; expanding-window OLS, with every training
  target strictly before the evaluated target. Retransformation is re-estimated
  only inside each training fold. Benchmarks use the same forecast origins.

| Model | QLIKE (lower is better) | Variance RMSE |
|---|---:|---:|
| HAR(1,5,22) | 0.277639 | 0.0000336230 |
| Previous session's variance | 0.413924 | 0.0000372137 |
| 22-session mean variance | **0.269916** | **0.0000308810** |

HAR outperformed persistence but **did not beat the 22-session average** on this
holdout. No statistical-superiority or trading-performance claim is made. The
holdout did not select or tune the specified model. No uncertainty band is invented.
Input hashes, coefficients, daily acceptance audit, per-origin held-out predictions
and scores are retained in the private state directory.

Verification: twelve unit tests cover return arithmetic, overnight inclusion,
missing/duplicate/incomplete observations, exact lag alignment, positivity,
annualization and future-data invariance of walk-forward forecasts. Desktop and
390-pixel mobile Chromium checks verify the surface, expiry selector, forecast
readings and Q ratio, including stale-input suppression. Synthetic test observations never enter the live dashboard.

## Environment

Reused Shaurya checkout revision: `c3bd026b8373d300143db97961be7fe999989b3c`.
Existing runtime: NumPy 2.2.6, pandas 2.3.3, SciPy 1.18.1, Pydantic 2.13.4,
PyArrow 23.0.1, dhanhq 2.2.0. Plotly 2.35.2 is vendored locally with its embedded
license header. The UI needs no CDN request. The dashboard does not modify the Shaurya packages.

Tests: `"$HOME/Documents/Shaurya/research/.venv/bin/python" -m unittest -v test_har.py`.

## Multi-session forecasts — 30 September 2026

The dark-mode screen now shows **1-, 5- and 22-trading-session HAR forecasts**
side by side, ATM IV, Q ratio and the surface. Equations, coefficients, benchmark tables
and explanatory sections are intentionally not displayed in the UI.

Each horizon h has a separate **direct** log-HAR regression, using the same lagged
1/5/22-session variance regressors. Its target is the **average daily variance of
all h future sessions**, not just variance on the h-th day. Every target session
must be present. Models are fitted independently; one-session forecasts are not
recursively fed back as observations.

- Displayed annualized RV: `sqrt(252 * predicted_mean_daily_variance)`.
- Expected cumulative variance over h sessions: `h * predicted_mean_daily_variance`.
- Square root of cumulative variance: `sqrt(h * predicted_mean_daily_variance)`;
  this is not the annualized headline. The cumulative variance is in each value's
  tooltip and the API.
- Each training fold uses only labels whose entire h-session window has ended by
  that forecast origin. Smearing is also fitted on that fold only.
- Overlapping 5/22-session evaluation windows are **not independent observations**.
  The 60-origin loss comparisons are descriptive, not significance tests, and the
  most recent evaluable origin differs by horizon. No model tuning uses holdouts.
- A 22-session forecast is not automatically a 30-calendar-day or expiry-matched
  forecast. All windows start after the stated historical as-of close; none is an
  intraday remaining-window nowcast. Historical jump/gap treatment is unchanged.

Direct multi-horizon HAR references include
[Lyócsa and Plíhal, FX market volatility modelling](https://pmc.ncbi.nlm.nih.gov/articles/PMC7526631/)
and [Modeling realized volatility of the EUR/USD exchange rate](https://doi.org/10.1016/j.iref.2020.10.001).
This implementation applies the direct-window idea to log **variance**, as above.

Using the same saved historical data through 29 September (no new broker download):

| Horizon | Annualized forecast | Training pairs | HAR QLIKE | Persistence QLIKE | Mean22 QLIKE |
|---|---:|---:|---:|---:|---:|
| 1 session | 12.69% | 425 | 0.27764 | 0.41392 | 0.26992 |
| 5 sessions | 12.83% | 417 | 0.14954 | 0.40730 | 0.12979 |
| 22 sessions | 13.56% | 383 | 0.20411 | 0.26334 | 0.07153 |

The 22-session-average benchmark beats HAR on these three evaluation sets; these
forecasts demonstrate the requested HAR model, not a claim of model superiority.
Private forecast JSON preserves each horizon's coefficients, sample size, forecast,
validation scores and per-origin predictions. `prepare.py` regenerates all three
horizons on subsequent on-demand refreshes. Twelve model tests now pass, including
multi-horizon target completeness, purged-prefix equivalence, future-value
invariance and variance/volatility scaling.

## Q ratio

`Q = annualization * five_session_mean_daily_variance / selected_ATM_IV²`

Equivalently, it is the squared ratio of annualized 5-session forecast RV to
selected-expiry ATM IV. The interface calls it a **horizon proxy**, not an
expiry-matched integrated variance ratio: the HAR window is five trading sessions,
whereas IV prices the selected option expiry on a calendar-time basis. The value
updates when IV or the selected expiry changes. Missing/nonpositive inputs, stale
IV, failed arbitrage checks, disconnected page polling or forecast age greater
than three calendar days suppress the metric. No trading threshold is applied.

## Installation and repository boundary

Python 3.11+ is required. This is the dashboard source, not a self-contained copy
of Shaurya or Dhan authentication. It requires the existing Shaurya data/research
packages and the office-Mac Dhan MCP runtime. The surface dependency is
[ayyararyan/shaurya](https://github.com/ayyararyan/shaurya), at the revision above.
Install its `data/` and `research/` packages in the chosen environment according
to that project's instructions. Broker credentials must remain outside Git.

`start.command` resolves its own checkout directory; it defaults to the existing
`$HOME/Documents/Shaurya/research/.venv/bin/python`. Set `ESSVI_PYTHON` to use
another Python environment that already contains both Shaurya packages. The
authentication and collector default locations remain the documented office-Mac
paths under `$HOME`; adapt them deliberately when migrating machines.

For **offline HAR tests only**, no credentials or Shaurya checkout are required:

```sh
python3 -m pip install -r requirements-test.txt
python3 -m unittest -v test_har.py
```

GitHub Actions runs only these synthetic model tests. It does not connect to Dhan,
start the dashboard, download prices or perform live UI checks. Runtime state,
raw candles, saved forecasts, credential files, logs and screenshots are excluded
from this repository. Historical numerical results above are dated research
summaries, not bundled data. Publishing does not start or schedule any process.
