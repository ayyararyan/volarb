import unittest
import numpy as np
import pandas as pd
from har import realized_variance, design, forecast


class HARTests(unittest.TestCase):
    def bars(self):
        days=pd.bdate_range('2026-01-05',periods=4,tz='Asia/Kolkata')
        rows=[]
        for i,d in enumerate(days):
            times=pd.date_range(d+pd.Timedelta(hours=9,minutes=15),periods=75,freq='5min')
            prices=100*np.exp(i*.01+np.arange(76)*.0001)
            rows.extend({'timestamp':t,'open':prices[j],'close':prices[j+1]} for j,t in enumerate(times))
        return pd.DataFrame(rows),pd.DataFrame({'timestamp':days})

    def test_variance_includes_all_75_returns_and_one_gap(self):
        b,d=self.bars();r,_=realized_variance(b,d,pd.Timestamp('2026-01-10',tz='Asia/Kolkata'))
        self.assertAlmostEqual(r.iloc[1].intraday,75*.0001**2,places=13)
        self.assertAlmostEqual(r.iloc[1].overnight,(.01-75*.0001)**2,places=13)
        self.assertAlmostEqual(r.iloc[1].rv,75*.0001**2+(.01-75*.0001)**2,places=13)

    def test_missing_session_not_bridged_or_filled(self):
        b,d=self.bars();b=b.drop(index=90)
        r,_=realized_variance(b,d,pd.Timestamp('2026-01-10',tz='Asia/Kolkata'))
        self.assertTrue(np.isnan(r.iloc[1].rv));self.assertTrue(np.isnan(r.iloc[2].rv))
        self.assertTrue(np.isfinite(r.iloc[3].rv))

    def test_incomplete_current_session_excluded(self):
        b,d=self.bars();r,_=realized_variance(b,d,pd.Timestamp('2026-01-08 14:00',tz='Asia/Kolkata'))
        self.assertEqual(r.index[-1],'2026-01-07')

    def test_duplicate_bars_rejected(self):
        b,d=self.bars()
        with self.assertRaises(ValueError):realized_variance(pd.concat([b,b.iloc[:1]]),d,pd.Timestamp('2026-01-10',tz='Asia/Kolkata'))

    def series(self):
        rng=np.random.default_rng(8)
        return pd.Series(np.exp(-10+rng.normal(0,.5,230)),index=pd.bdate_range('2025-01-01',periods=230).strftime('%Y-%m-%d'))

    def test_weekly_monthly_lags_and_target(self):
        rv=self.series();x,y=design(rv);i=30
        self.assertAlmostEqual(x.iloc[i].weekly,np.log(rv.iloc[i-4:i+1].mean()))
        self.assertAlmostEqual(x.iloc[i].monthly,np.log(rv.iloc[i-21:i+1].mean()))
        self.assertAlmostEqual(y.iloc[i],np.log(rv.iloc[i+1]))

    def test_walkforward_prediction_equals_prefix_forecast(self):
        rv=self.series();f=forecast(rv,validation_days=2);row=f['walk_forward'][0]
        prefix=forecast(rv.loc[:row['origin']],validation_days=0)
        self.assertAlmostEqual(row['har'],prefix['variance'],places=14)
        changed=rv.copy();changed.loc[changed.index>row['origin']]*=100
        again=forecast(changed,validation_days=2)
        self.assertAlmostEqual(row['har'],again['walk_forward'][0]['har'],places=14)

    def test_positive_variance_and_annualization(self):
        f=forecast(self.series(),validation_days=0)
        self.assertGreater(f['variance'],0)
        self.assertAlmostEqual(f['annualized_volatility']**2,252*f['variance'])

    def test_latest_incomplete_window_cannot_forecast(self):
        rv=self.series();rv.iloc[-7]=np.nan
        with self.assertRaises(ValueError):forecast(rv)

    def test_multisession_target_is_complete_future_mean(self):
        rv=self.series()
        for h in (5,22):
            _,y=design(rv,h);i=40
            self.assertAlmostEqual(np.exp(y.iloc[i]),rv.iloc[i+1:i+h+1].mean(),places=14)
            self.assertTrue(y.iloc[-h:].isna().all())
            broken=rv.copy();broken.iloc[i+3]=np.nan
            self.assertTrue(np.isnan(design(broken,h)[1].iloc[i]))

    def test_multisession_purged_validation_has_no_future_leakage(self):
        rv=self.series()
        for h in (5,22):
            row=forecast(rv,horizon_sessions=h,validation_days=2)['walk_forward'][0]
            prefix=forecast(rv.loc[:row['origin']],horizon_sessions=h,validation_days=0)
            self.assertAlmostEqual(row['har'],prefix['variance'],places=14)
            self.assertEqual(row['training_pairs'],prefix['training_pairs'])
            changed=rv.copy();changed.loc[changed.index>row['origin']]*=30
            other=forecast(changed,horizon_sessions=h,validation_days=2)['walk_forward'][0]
            self.assertAlmostEqual(row['har'],other['har'],places=14)

    def test_multisession_variance_scaling(self):
        for h in (5,22):
            f=forecast(self.series(),horizon_sessions=h,validation_days=0)
            self.assertAlmostEqual(f['cumulative_variance'],h*f['mean_daily_variance'])
            self.assertAlmostEqual(f['annualized_volatility']**2,252*f['mean_daily_variance'])
            self.assertAlmostEqual(f['window_volatility']**2,f['cumulative_variance'])

    def test_invalid_horizon(self):
        for h in (0,-1,1.5,True):
            with self.assertRaises(ValueError):design(self.series(),h)

if __name__=='__main__':unittest.main()
