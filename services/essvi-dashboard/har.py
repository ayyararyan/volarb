"""Positive log-HAR(1,5,22) on complete-session realized variance."""
from __future__ import annotations

import numpy as np
import pandas as pd

IST = 'Asia/Kolkata'


def realized_variance(bars: pd.DataFrame, daily: pd.DataFrame, asof: pd.Timestamp):
    """75 five-minute returns plus prior close -> today's open squared gap.

    No forward filling: rejected sessions remain NaN in the trading-session index.
    Dhan timestamps denote interval OPEN. Index daily closes are not substituted
    for the previous last intraday close (official closes can be VWAP-derived).
    """
    bars = bars.copy()
    bars['timestamp'] = pd.to_datetime(bars.timestamp, utc=True).dt.tz_convert(IST)
    if bars.timestamp.duplicated().any():
        raise ValueError('Duplicate bar timestamps')
    daily = daily.copy()
    daily['timestamp'] = pd.to_datetime(daily.timestamp, utc=True).dt.tz_convert(IST)
    days = sorted(set(daily.timestamp.dt.date))
    groups = {d: g.set_index('timestamp').sort_index() for d, g in bars.groupby(bars.timestamp.dt.date)}
    clean, audit = {}, []
    for d in days:
        opening = pd.Timestamp(str(d) + ' 09:15', tz=IST)
        closing = pd.Timestamp(str(d) + ' 15:30', tz=IST)
        if closing > asof:
            continue
        expected = pd.date_range(opening, periods=75, freq='5min')
        g = groups.get(d)
        reason = None
        if g is None or not expected.isin(g.index).all():
            reason = 'missing five-minute bars'
        else:
            values = g.loc[expected, ['open', 'close']].to_numpy(float)
            if not np.isfinite(values).all() or (values <= 0).any():
                reason = 'invalid prices'
            else:
                path = np.r_[values[0, 0], values[:, 1]]
                intraday = float(np.square(np.diff(np.log(path))).sum())
                clean[d] = (values[0, 0], values[-1, 1], intraday)
        audit.append({'date': str(d), 'accepted_bars': reason is None, 'reason': reason})
    result = []
    for i, d in enumerate(days):
        if pd.Timestamp(str(d)+' 15:30', tz=IST) > asof:
            continue
        previous = days[i-1] if i else None
        rv = overnight = float('nan')
        if d in clean and previous in clean:
            overnight = float(np.log(clean[d][0] / clean[previous][1]) ** 2)
            rv = clean[d][2] + overnight
        result.append({'date': str(d), 'rv': rv, 'intraday': clean.get(d, (None,None,float('nan')))[2], 'overnight': overnight})
    return pd.DataFrame(result).set_index('date'), audit


def design(rv: pd.Series, horizon_sessions: int = 1):
    """At t, forecast mean daily variance over t+1..t+h, not just day t+h."""
    if isinstance(horizon_sessions, bool) or not isinstance(horizon_sessions, int) or horizon_sessions < 1:
        raise ValueError('horizon_sessions must be a positive integer')
    positive = rv.where(rv > 0)
    x = pd.DataFrame({'constant': 1., 'daily': np.log(positive),
                      'weekly': np.log(positive.rolling(5).mean()),
                      'monthly': np.log(positive.rolling(22).mean())})
    future = pd.concat([positive.shift(-j) for j in range(1, horizon_sessions+1)], axis=1)
    # Every session in the target must be observed; no partial-window averages.
    y = np.log(future.mean(axis=1, skipna=False))
    return x, y


def fit(x, y):
    beta, _, rank, _ = np.linalg.lstsq(np.asarray(x), np.asarray(y), rcond=None)
    if rank < 4:
        raise ValueError('HAR regressors are rank deficient')
    residual = np.asarray(y) - np.asarray(x) @ beta
    smearing = float(np.exp(residual).mean())
    return beta, smearing


def forecast(rv: pd.Series, min_train=100, validation_days=60, horizon_sessions=1):
    if not rv.index.is_unique or not rv.index.is_monotonic_increasing:
        raise ValueError('Session index must be unique and chronological')
    x, y = design(rv, horizon_sessions)
    eligible = x.notna().all(axis=1) & y.notna()
    xx, yy = x.loc[eligible], y.loc[eligible]
    if len(xx) < min_train or x.iloc[-1].isna().any():
        raise ValueError('Insufficient complete history: need 100 training pairs and latest 22 contiguous complete sessions')
    beta, smear = fit(xx, yy)
    pred = float(np.exp(x.iloc[-1].to_numpy() @ beta) * smear)
    if not np.isfinite(pred) or pred <= 0:
        raise ValueError('Invalid HAR prediction')
    # Direct horizon-specific OLS. At validation origin t, training label windows
    # must END by t. Merely slicing earlier origins would leak up to h-1 sessions.
    positions = pd.Series(np.arange(len(rv)), index=rv.index)
    label_end_positions = positions.loc[xx.index] + horizon_sessions
    checks = []
    for i in range(max(min_train, len(xx)-validation_days), len(xx)):
        available = label_end_positions <= positions.loc[xx.index[i]]
        if int(available.sum()) < min_train:
            continue
        b, s = fit(xx.loc[available], yy.loc[available])
        p = float(np.exp(xx.iloc[i].to_numpy() @ b)*s)
        checks.append({'origin': xx.index[i],
                       'target_end':rv.index[int(positions.loc[xx.index[i]])+horizon_sessions],
                       'training_pairs':int(available.sum()), 'actual': float(np.exp(yy.iloc[i])),
                       'har': p, 'yesterday': float(np.exp(xx.iloc[i]['daily'])),
                       'mean22': float(np.exp(xx.iloc[i]['monthly']))})
    validation = {}
    for name in ('har', 'yesterday', 'mean22'):
        if checks:
            actual = np.array([r['actual'] for r in checks]); predicted = np.array([r[name] for r in checks])
            ratio = actual / predicted
            validation[name] = {'qlike': float((ratio-np.log(ratio)-1).mean()),
                                'rmse_variance': float(np.sqrt(np.square(actual-predicted).mean()))}
    return {'status':'ok', 'model':'log-HAR(1,5,22)', 'asof_session':rv.index[-1],
            'horizon':f'Mean daily variance over {horizon_sessions} full sessions after the as-of close; includes overnight gaps',
            'horizon_sessions':horizon_sessions,
            'variance':pred, 'annualized_volatility':float(np.sqrt(252*pred)),
            'mean_daily_variance':pred, 'cumulative_variance':float(horizon_sessions*pred),
            'window_volatility':float(np.sqrt(horizon_sessions*pred)),
            'annualization':252, 'training_pairs':len(xx), 'training_start':xx.index[0],
            'coefficients':dict(zip(x.columns, map(float,beta))), 'smearing':smear,
            'validation_days':len(checks), 'validation':validation,
            'history':[{'date':d,'vol':float(np.sqrt(252*v))} for d,v in rv.tail(100).items() if np.isfinite(v)],
            'walk_forward':checks}


def forecast_horizons(rv: pd.Series):
    """Preserve the one-session fields for consumers; add direct 5/22-session fits."""
    fits = {str(h): forecast(rv, horizon_sessions=h) for h in (1, 5, 22)}
    result = dict(fits['1'])
    result['horizons'] = {h: {k:v for k,v in f.items() if k not in ('history','walk_forward')}
                          for h,f in fits.items()}
    result['walk_forward'] = {h:f['walk_forward'] for h,f in fits.items()}
    result['horizon_method'] = 'Separate direct log-HAR regressions on future average daily variance; training-only smearing'
    return result
