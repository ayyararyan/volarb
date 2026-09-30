"""On-demand launcher; no scheduler, trading or broker-order calls."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse, json, os, re, subprocess, sys, tempfile, time, socket
from shaurya.data import DataCatalog
from shaurya.data.instrument_master import DhanDailyInstrumentMaster
from prepare import prepare, STATE, CREDENTIALS
from app import serve

HOME=Path.home(); SHAURYA=HOME/'Documents/Shaurya'; IST=ZoneInfo('Asia/Kolkata')


def auth():
    runtime=HOME/'dhan-chatgpt-mcp'
    subprocess.run(['npm','run','auth:recover'],cwd=runtime,check=True)
    # Copy the two validated Dhan fields only; never expose secrets or touch Kotak.
    source={}
    for line in (runtime/'.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);source[k.strip()]=v.strip()
    old=CREDENTIALS.read_text();new=old
    for key in ('DHAN_CLIENT_ID','DHAN_ACCESS_TOKEN'):
        if not source.get(key):raise ValueError('Missing Dhan credential field')
        pattern=r'^'+key+r'=.*$'
        if not re.search(pattern,new,re.M):raise ValueError('Destination Dhan field missing')
        new=re.sub(pattern,lambda m:key+'='+source[key],new,flags=re.M)
    fd,temp=tempfile.mkstemp(dir=CREDENTIALS.parent,prefix='.broker-');os.fchmod(fd,0o600)
    with os.fdopen(fd,'w') as f:f.write(new)
    if CREDENTIALS.read_text()!=old:
        Path(temp).unlink();raise RuntimeError('Concurrent credential edit; no replacement made')
    os.replace(temp,CREDENTIALS)


def source():
    now=datetime.now(IST);day=str(now.date())
    for root in (STATE/day,HOME/'.local/state/shaurya-dashboard'/day):
        catalog=root/'catalog'
        if not catalog.exists():continue
        for handle in DataCatalog(catalog).handles().values():
            if str(handle.status)=='active' and any(':NIFTY:option:' in i for i in handle.instrument_ids):
                # Probe DAT's authenticated local stream, not just a stale catalogue flag.
                from shaurya.data import DataAccess
                try:
                    with DataAccess(DataCatalog(catalog)).live(handle,connect_timeout_seconds=2) as stream:stream.poll(timeout_seconds=.2)
                    return catalog,handle.dataset_id
                except Exception:continue
    if now.hour<9 or (now.hour==9 and now.minute<15) or now.hour>15 or (now.hour==15 and now.minute>=30):
        raise RuntimeError('No active feed. Start during the regular 09:15–15:30 IST session.')
    root=STATE/day;root.mkdir(parents=True,exist_ok=True,mode=0o700)
    masters=STATE/'instrument-masters';DhanDailyInstrumentMaster(masters).refresh(now.date())
    master=masters/f'dhan_instrument_master_{day}.csv'
    catalog=root/'catalog';duration=int((now.replace(hour=15,minute=30,second=0)-now).total_seconds())
    cmd=[str(SHAURYA/'data/.venv/bin/shaurya-chain-capture'),'--credentials',str(CREDENTIALS),
         '--security-master',str(master),'--underlying','NIFTY','--expiry-count','3','--max-options','180',
         '--duration-seconds',str(duration),'--output-root',str(root/'capture'),'--data-catalog',str(catalog),'--allow-nonarchive-output']
    with (root/'capture.log').open('a') as log:child=subprocess.Popen(cmd,stdout=log,stderr=log,start_new_session=True)
    (root/'capture.pid').write_text(str(child.pid))
    for _ in range(45):
        if child.poll() is not None:raise RuntimeError('Read-only collector exited; inspect its local log')
        if catalog.exists():
            for handle in DataCatalog(catalog).handles().values():
                if str(handle.status)=='active':return catalog,handle.dataset_id
        time.sleep(1)
    child.terminate();raise RuntimeError('Collector startup timed out')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--skip-history',action='store_true');p.add_argument('--port',type=int,default=8770);a=p.parse_args()
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1',a.port))
        except OSError:raise SystemExit(f'Port {a.port} is already in use. Existing dashboard: http://127.0.0.1:{a.port}/')
    auth()
    if not a.skip_history:prepare()
    catalog,dataset=source();serve(catalog,dataset,a.port)
