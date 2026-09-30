"""Local read-only dashboard. Fits its own eSSVI engine from DAT market rows."""
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse, json, threading, time
from shaurya.data import DataAccess, DataCatalog
from shaurya.analytics.surface_feed import SurfaceEngine, default_log_moneyness_grid
from shaurya.analytics.mispricing import MispricingPolicy
from shaurya.analytics.dashboard import build_payload

ROOT=Path(__file__).resolve().parent
STATE=Path.home()/'.local/state/essvi-dashboard'
IST=ZoneInfo('Asia/Kolkata')


class Dashboard:
    def __init__(self, catalog, dataset):
        self.access=DataAccess(DataCatalog(catalog));self.handle=self.access.catalog.get(dataset)
        expiries=sorted({date.fromisoformat(i.split(':')[4]) for i in self.handle.instrument_ids
                         if ':NIFTY:option:' in i and date.fromisoformat(i.split(':')[4])>datetime.now(IST).date()})
        self.engine=SurfaceEngine(run_id=dataset,surface_id='essvi-har-dashboard',expiries=tuple(expiries),
             log_moneyness_grid=default_log_moneyness_grid(),underlying='NIFTY',
             include_atm_strikes=True,smoothing_enabled=False,mispricing_policy=MispricingPolicy(enabled=False),
             history_limit=20,health_sample_limit=100)
        self.lock=threading.Lock();self.error=None

    def consume(self):
        try:
            with self.access.live(self.handle,connect_timeout_seconds=15) as stream:
                while True:
                    batch=stream.poll(timeout_seconds=.2)
                    with self.lock:
                        for row in batch.rows:self.engine.ingest(row)
                        now=datetime.now(IST)
                        if self.engine.due_for_fit(now):self.engine.fit(now)
        except Exception as e:
            self.error=type(e).__name__ # Never log broker/transport secrets.

    def payload(self):
        with self.lock:
            p=build_payload(self.engine,title='NIFTY volatility',source='Dhan DAT live stream')
        s=p.get('snapshot') or {}
        try:
            forecast=json.loads((STATE/'forecast.json').read_text())
            forecast={k:v for k,v in forecast.items() if k not in ('raw_files','audit','walk_forward','history')}
            # A historical forecast remains explicitly dated; no intraday rebranding.
            forecast['age_calendar_days']=(datetime.now(IST).date()-date.fromisoformat(forecast['asof_session'])).days
        except (OSError,ValueError,KeyError):
            forecast={'status':'unavailable','reason':'Run prepare.py to build HAR history and forecast.'}
        return {'now':datetime.now(IST).isoformat(),'sequence':s.get('sequence'),
                'fit_timestamp':s.get('fit_timestamp'),'fit_ok':s.get('fit_ok',False),
                'grid':s.get('grid'),'atm':p['atm'],'health':p['live_health'],
                'verdict':p['health_verdict'],'arbitrage':p['arbitrage'],
                'fit_age_seconds':p['fit_age_seconds'],'forecast':forecast,'stream_error':self.error,
                'surface_is_stale':p['health_verdict'].get('surface_is_stale',True)}


def serve(catalog, dataset, port=8770):
    dashboard=Dashboard(Path(catalog),dataset)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path=self.path.split('?',1)[0]
            if path=='/api/state':
                try: body=json.dumps(dashboard.payload(),allow_nan=False).encode()
                except Exception:
                    self.send_error(503,'Dashboard data unavailable');return
                kind='application/json'
            elif path in ('/','/index.html','/plotly.min.js'):
                f=ROOT/('index.html' if path in ('/','/index.html') else 'vendor/plotly.min.js')
                body=f.read_bytes();kind='text/html; charset=utf-8' if f.suffix=='.html' else 'application/javascript'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=dashboard.consume,daemon=True).start()
    print(f'Dashboard http://127.0.0.1:{port}/',flush=True)
    server.serve_forever()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--catalog',required=True);p.add_argument('--dataset',required=True);p.add_argument('--port',type=int,default=8770)
    a=p.parse_args();serve(a.catalog,a.dataset,a.port)
