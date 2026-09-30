"""Fetch private Dhan history in <=80-day chunks, quality-check, fit HAR."""
from pathlib import Path
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
import json, hashlib, argparse, time
import pandas as pd
from shaurya.data.dhan_client import DhanClient, DhanCredentials
from har import realized_variance, forecast_horizons

ROOT = Path(__file__).resolve().parent
STATE = Path.home()/'.local/state/essvi-dashboard'
CREDENTIALS = Path.home()/'Documents/Market-Making-Secrets/broker.env'


def prepare():
    raw=STATE/'history'; raw.mkdir(parents=True,exist_ok=True,mode=0o700)
    now=datetime.now(ZoneInfo('Asia/Kolkata')); end=now.date(); start=end-timedelta(days=730)
    client=DhanClient(DhanCredentials.from_env_file(CREDENTIALS))
    frames=[]; provenance=[]
    cursor=start
    while cursor < end:
        stop=min(end,cursor+timedelta(days=80))
        p=raw/f'nifty-5m-{cursor}-{stop}.csv'
        if not p.exists() or stop == end:
            f=client.intraday_minute_data(security_id='13',exchange_segment='IDX_I',instrument_type='INDEX',from_date=cursor,to_date=stop,interval=5)
            if f.empty: raise ValueError(f'No historical data for {cursor} to {stop}')
            f.to_csv(p,index=False)
            time.sleep(0.3)
        f=pd.read_csv(p);frames.append(f)
        provenance.append({'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'rows':len(f)})
        print(f'History {cursor} to {stop}: {len(f)} bars',flush=True)
        cursor=stop
    bars=pd.concat(frames,ignore_index=True)
    # Chunks can share their boundary day. Reject conflicting revisions instead
    # of silently mixing snapshots; exact duplicates are harmless.
    columns=['timestamp','open','high','low','close']
    unique=bars[columns].drop_duplicates()
    if unique.timestamp.duplicated().any():raise ValueError('Conflicting overlapping historical bars')
    bars=bars.drop_duplicates('timestamp').sort_values('timestamp')
    daily_path=raw/f'nifty-daily-{start}-{end}.csv'
    client.historical_daily_data(security_id='13',exchange_segment='IDX_I',instrument_type='INDEX',from_date=start,to_date=end+timedelta(days=1)).to_csv(daily_path,index=False)
    daily=pd.read_csv(daily_path)
    rv,audit=realized_variance(bars,daily,pd.Timestamp(now))
    rv.to_csv(STATE/'realized-variance.csv')
    result=forecast_horizons(rv.rv)
    result.update({'generated_at':now.isoformat(),'data_start':rv.index[0], 'data_end':rv.index[-1],
                   'accepted_sessions':int(rv.rv.notna().sum()), 'rejected_sessions':int(rv.rv.isna().sum()),
                   'source':'Dhan NIFTY spot index (13), 5-minute OHLC; 75 regular-session bars',
                   'audit':audit,'raw_files':provenance})
    tmp=STATE/'forecast.tmp';tmp.write_text(json.dumps(result,indent=2,allow_nan=False));tmp.replace(STATE/'forecast.json')
    print(json.dumps({k:result[k] for k in ['status','asof_session','training_pairs','accepted_sessions','rejected_sessions','annualized_volatility','validation']}),flush=True)

if __name__=='__main__':prepare()
