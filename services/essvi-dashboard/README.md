# Realized variance and eSSVI dashboard

Status: **active, optional read-only research service; deployment-specific launcher**.
It is not an Execution Engine, a remaining-day RV forecast or an autonomous trading
service. The loopback dashboard displays fitted ATM IV, direct 1/5/22-session HAR
forecasts, a 5-session Q horizon proxy and an interactive eSSVI surface. It uses
broker observations/fitted models, never demonstration prices.

## Entrypoints and dependencies

| Path | Purpose |
|---|---|
| [`start.command`](start.command), [`run.py`](run.py) | Explicit office-Mac launcher; authentication, optional history preparation, capture reuse/start, dashboard |
| [`prepare.py`](prepare.py) | Privately fetch history, validate sessions and save dated HAR forecasts |
| [`har.py`](har.py) | Pure research calculations; independently testable offline |
| [`app.py`](app.py), [`index.html`](index.html) | Loopback read-only `/api/state`, eSSVI fitting and dashboard UI |
| [`test_har.py`](test_har.py), [`requirements-test.txt`](requirements-test.txt) | Synthetic offline model tests |
| [`vendor/plotly.min.js`](vendor/plotly.min.js) | Deliberately vendored Plotly 2.35.2 with embedded license; no CDN |

Live use needs Python 3.11+, the external
[Shaurya data/research packages](https://github.com/ayyararyan/shaurya) and an existing
Dhan MCP authentication installation. The integration was validated against
Shaurya revision `c3bd026b8373d300143db97961be7fe999989b3c`; this repository does not
vendor those packages. The dashboard owns its `SurfaceEngine` and refits current
DAT rows every three seconds; it does not run either older dashboard server.

## Explicit start and environment boundary

From this directory:

```sh
./start.command
```

`ESSVI_PYTHON` selects the interpreter; its default is
`$HOME/Documents/Shaurya/research/.venv/bin/python`. **This does not configure the
other integrations.** The retained office-Mac launcher uses:

- MCP source/authentication installation: `$HOME/dhan-chatgpt-mcp`;
- its legacy deployment credential file: `$HOME/dhan-chatgpt-mcp/.env`;
- Shaurya capture executable: `$HOME/Documents/Shaurya/data/.venv/bin/shaurya-chain-capture`;
- external destination credentials: `$HOME/Documents/Market-Making-Secrets/broker.env`;
- private dashboard history/state/logs: `$HOME/.local/state/essvi-dashboard/`.

These are **deployment-specific compatibility assumptions**, not portable kit
paths. `run.py` invokes the local MCP's explicit authentication recovery, then
copies only validated Dhan identity/token fields into the external broker file
using concurrency-checked atomic replacement. Do not point it at a newly installed
portable MCP without deliberately adapting and reviewing its source/runtime paths;
portable MCP state defaults to `$VOLARB_DATA_DIR/dhan`, not its checkout. Repository
cleanup does not alter credentials, run authentication or migrate this integration.

The launcher refuses an occupied port before auth/data work. It reuses a verified
active NIFTY DAT stream when available; otherwise, during the regular 09:15–15:30 IST
session, it starts one read-only collector through 15:30. New collectors request
the nearest three expiries and up to 180 options. Isolated local capture does not
change production archive settings. No scheduler or login service is installed.
Default page: `http://127.0.0.1:8770/`; after feed closure it stays visible with
explicit stale status.

Refresh history/model explicitly using the configured Shaurya environment:

```sh
"${ESSVI_PYTHON:-$HOME/Documents/Shaurya/research/.venv/bin/python}" prepare.py
```

Forecasts are never silently refitted on page refresh. Preparation uses the most
recent completed session and forecasts complete future sessions, including any
portion already elapsed if launched intraday. `./start.command --skip-history`
reuses the explicitly dated saved result. This is **not** the controller's
[intraday remaining-window RV module](../../skill/intraday-realized-volatility-forecast/SKILL.md).

## Research methodology

History preparation requests two years of NIFTY spot index five-minute bars in
at most 80-day batches. No futures rolls or expired-option history are needed.
The data is private and not bundled. Historical retrieval and benchmark outcomes
are preserved in the [dated validation archive](../../archive/research/essvi-dashboard/README.md).

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

## Direct multi-session forecasts

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

## Q ratio

`Q = annualization * five_session_mean_daily_variance / selected_ATM_IV²`

Equivalently, it is the squared ratio of annualized 5-session forecast RV to
selected-expiry ATM IV. The interface calls it a **horizon proxy**, not an
expiry-matched integrated variance ratio: the HAR window is five trading sessions,
whereas IV prices the selected option expiry on a calendar-time basis. The value
updates when IV or the selected expiry changes. Missing/nonpositive inputs, stale
IV, failed arbitrage checks, disconnected page polling or forecast age greater
than three calendar days suppress the metric. No trading threshold is applied.

## Verification and historical evidence

For offline tests only, no credentials, live service or Shaurya checkout are needed:

```sh
python3 -m pip install -r requirements-test.txt
python3 -B -m unittest -v test_har.py
```

CI runs synthetic HAR tests only; it does not start the dashboard, authenticate,
download prices or validate live UI/integrations. Model tests cover arithmetic,
session quality, target-window completeness, purged training, future-data invariance
and scaling. Raw candles, forecasts, logs, credentials and screenshots remain private.
The [30 September validation record](../../archive/research/essvi-dashboard/validation-2026-09-30.md)
contains dated sample sizes, losses and UI observations, including HAR's failure to
beat the mean22 benchmark. Those numbers are not current forecasts.
