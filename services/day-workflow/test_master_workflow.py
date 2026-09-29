import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import master_workflow as m
import workflow_decision as d
import day_workflow as w
from test_day_workflow import candidate
from test_workflow_observation import evidence, save

AT = w.stamp('2026-09-29T10:00:00+05:30')


def packet():
    return {'mode':'SHADOW', 'synthetic':True, 'asof':AT.isoformat(),
        'auth':{'status':'VALID','asof':AT.isoformat(),'profile_verified':True,'expires_at':'2026-09-30T10:00:00+05:30'},
        'account':{'account_verified':True,'account_state':'VERIFIED_FLAT','asof':AT.isoformat()},
        'session':{'asof':AT.isoformat(),'trading_day_verified':True,'market_open':True,'evidence_ref':'fixture'},
        'mandate':{'day':'2026-09-29','activated':True}, 'review_due':True}


def research():
    raw = json.loads((d.SKILLS/'intraday-realized-volatility-forecast/scripts/test_stable.json').read_text())
    end = w.stamp(raw['hf_quotes'][-1]['timestamp'])
    delta = AT-end
    for key in ['hf_quotes','surface_snapshots']:
        for x in raw[key]:
            x['timestamp'] = (w.stamp(x['timestamp'])+delta).isoformat()
    raw.pop('config',None)
    raw.update(evidence_ref='synthetic',instrument_ref='synthetic-futures',current_asof=AT.isoformat())
    news = {'producer':'market-news-signal-filter','asof':AT.isoformat(),'horizon_minutes':30,
        'valid_until':(AT+dt.timedelta(minutes=30)).isoformat(),'source_refs':['fixture'],
        'normalized':{'status':'CURRENT','calibration_asof':'2026-09-20','aggregate_state':'CALM',
          'max_butterfly_relevance':'watch','max_latency_severity':'low','events':[]}}
    indices={}
    for sym in w.INDICES:
        hf=copy.deepcopy(raw); hf['symbol']=sym
        c=candidate(sym.lower(),sym)
        c['legs']={}
        for role, strike, option in [('putWing',24000,'PE'),('putBody',25000,'PE'),('callWing',26000,'CE'),('callBody',25000,'CE')]:
            price=c['limits'][role]
            c['legs'][role]={'symbol':sym,'expiry':c['spec']['expiry'],'strike':strike,'option_type':option,
                'lot_size':10,'security_id':str(len(c['legs'])+1),'exchange_segment':'BSE_FNO' if sym=='SENSEX' else 'NSE_FNO',
                'resolver_ref':'fixture','quote':{'asof':AT.isoformat(),'exchange_time':AT.isoformat(),
                'bid':price,'ask':price,'bid_size':10,'ask_size':10}}
        indices[sym]={'asof':AT.isoformat(),'data_health':'HEALTHY','hf':hf,'hard_risk_gate':'PASS',
            'risk_evidence_ref':'fixture','expiry_exit_gate':'PASS','expiry_evidence_ref':'fixture','candidates':[c]}
    return {'horizon_minutes':30,'news':news,'indices':indices,
        'ranking':{'asof':AT.isoformat(),'evidence_ref':'fixture','candidate_ids':['nifty','banknifty','sensex']}}


class MasterTest(unittest.TestCase):
    def test_full_three_index_path_recomputes_rv_selects_one(self):
        p=packet();p['research']=research()
        result=m.evaluate(p,now=AT)
        self.assertEqual(result['action'],'CANDIDATE_VALIDATED',result)
        self.assertEqual(result['selected']['id'],'nifty')
        self.assertEqual(result['selected']['checked_max_loss_rupees'],900)
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(len(result['indices']),3)

    def test_live_rejected(self):
        p=packet();p['mode']='LIVE'
        self.assertEqual(m.evaluate(p,now=AT)['action'],'NEED_EVIDENCE')

    def test_auth_decisions(self):
        for status, expected in [('MISSING','RECOVER_WEB_TOKEN'),('EXPIRED','RECOVER_WEB_TOKEN'),
             ('REJECTED','RECOVER_WEB_TOKEN'),('NETWORK_ERROR','AUTH_HANDOFF'),('ACCOUNT_MISMATCH','AUTH_HANDOFF')]:
            p=packet();p['auth']['status']=status
            self.assertEqual(m.evaluate(p,now=AT)['action'],expected)
        p=packet();p['auth'].update(status='EXPIRED',attempts_this_pass=1)
        self.assertEqual(m.evaluate(p,now=AT)['action'],'AUTH_HANDOFF')

    def test_auth_cooldown_and_lifetime(self):
        p=packet();p['auth']['expires_at']=(AT+dt.timedelta(minutes=30)).isoformat()
        self.assertEqual(m.evaluate(p,now=AT)['action'],'RECOVER_WEB_TOKEN')
        p['auth'].update(status='MISSING',last_attempt_at=AT.isoformat())
        self.assertEqual(m.evaluate(p,now=AT)['action'],'AUTH_HANDOFF')

    def test_account_failure_not_flat(self):
        p=packet();p['account']['account_verified']=False
        self.assertEqual(m.evaluate(p,now=AT)['action'],'ACQUIRE_ACCOUNT')
        p['account'].update(account_verified=True,account_state='OUTSTANDING_ORDERS')
        self.assertEqual(m.evaluate(p,now=AT)['action'],'RECONCILE_ORDERS')

    def test_deadline_independent_of_news_mandate_ownership_margin(self):
        p=packet(); now=AT.replace(hour=14,minute=45)
        p['asof']=p['auth']['asof']=p['account']['asof']=p['session']['asof']=now.isoformat()
        p['account']['account_state']='EXPOSURE_PRESENT';p.pop('mandate')
        self.assertEqual(m.evaluate(p,now=now)['action'],'SQUARE_OFF')
        p['session']['market_open']=False
        self.assertEqual(m.evaluate(p,now=now)['action'],'LOCKED_OVERNIGHT')

    def test_first_terminal_prevents_research(self):
        p=packet();p['auth']['status']='EXPIRED'
        with patch.object(m,'compose',side_effect=AssertionError('must not run')):
            self.assertEqual(m.evaluate(p,now=AT)['trace'],['AUTH'])

    def test_bad_data_prevents_hf_news(self):
        r=research();r.pop('news')
        for i in r['indices'].values(): i['data_health']='STALE';i.pop('hf')
        self.assertEqual(d.compose(r,AT)['action'],'NO_TRADE')

    def test_sparse_or_stale_hf_cannot_be_overridden_by_flag(self):
        for kind in ['sparse','stale','config']:
            r=research()
            for i in r['indices'].values():
                i['intraday_rv_state']='FAVOURABLE'
                if kind=='sparse': i['hf']['hf_quotes']=i['hf']['hf_quotes'][-2:]
                if kind=='stale': i['hf']['hf_quotes'][-1]['timestamp']=(AT-dt.timedelta(minutes=1)).isoformat()
                if kind=='config': i['hf']['config']={'jump_threshold_sigma':999}
            self.assertEqual(d.compose(r,AT)['action'],'NO_TRADE')

    def test_news_horizon_and_staleness_block(self):
        for mutate in [lambda r:r['news'].update(horizon_minutes=15),
            lambda r:r['news'].update(asof=(AT-dt.timedelta(minutes=6)).isoformat()),
            lambda r:r['news']['normalized'].update(aggregate_state='UNKNOWN')]:
            r=research();mutate(r)
            self.assertEqual(d.compose(r,AT)['action'],'NEED_EVIDENCE')

    def test_news_once_reused_across_three_indices(self):
        with patch.object(d,'news_packet',wraps=d.news_packet) as child:
            d.compose(research(),AT)
            self.assertEqual(child.call_count,1)

    def test_exact_candidate_wrong_contract_depth_margin_cost(self):
        for mutate in [lambda c:c['legs']['putWing'].update(strike=23900),
            lambda c:c['legs']['putWing']['quote'].update(ask_size=1),
            lambda c:c['margin'].update(reserveRupees=0),
            lambda c:c.update(roundtrip_cost_bound_rupees=1001),
            lambda c:c['margin'].update(sequence=list(reversed(w.ROLES)))]:
            r=research()
            for i in r['indices'].values(): mutate(i['candidates'][0])
            self.assertEqual(d.compose(r,AT)['action'],'NO_TRADE')

    def test_missing_hf_open_not_automatic_exit(self):
        r=research();r['indices']={'NIFTY':r['indices']['NIFTY']};r['position_symbol']='NIFTY'
        del r['indices']['NIFTY']['hf']
        out=d.compose(r,AT,True)
        self.assertEqual(out['action'],'HOLD')
        self.assertEqual(out['next_review'],(AT+dt.timedelta(minutes=30)).isoformat())
        r['indices']['NIFTY']['expiry_exit_gate']='EXIT'
        self.assertEqual(d.compose(r,AT,True)['action'],'SQUARE_OFF')

    def test_rv_exit_precedes_missing_expiry(self):
        r=research();r['indices']={'NIFTY':r['indices']['NIFTY']};r['position_symbol']='NIFTY'
        r['news']['normalized']['aggregate_state']='TAIL_RISK_ACTIVE'
        del r['indices']['NIFTY']['expiry_exit_gate']
        self.assertEqual(d.compose(r,AT,True)['action'],'SQUARE_OFF')

    def test_closed_cycle_and_review_window(self):
        p=packet();p['mandate']['cycle_closed']=True
        self.assertEqual(m.evaluate(p,now=AT)['action'],'STOP')
        p['mandate']['cycle_closed']=False;p['review_due']=False
        self.assertEqual(m.evaluate(p,now=AT)['action'],'WAIT_REVIEW')

    def test_observed_cannot_trust_forged_account_summary(self):
        p=packet();p['mode']='OBSERVE'
        self.assertEqual(m.evaluate(p,now=AT)['action'],'ACQUIRE_ACCOUNT')

    def test_observed_manifest_drives_real_account_state(self):
        with tempfile.TemporaryDirectory() as folder:
            e=evidence()
            # Fixture uses a different clock, update every endpoint consistently.
            e['completed_at']=AT.isoformat()
            for ep in e['endpoints'].values(): ep['requested_at']=ep['received_at']=AT.isoformat()
            p=packet();p['mode']='OBSERVE';p['account_manifest']=str(save(Path(folder),e));p['research']=research()
            self.assertEqual(m.evaluate(p,now=AT,evidence_root=Path(folder))['action'],'NO_TRADE')  # unbound inline HF is not observed evidence

    def test_hf_manifest_integrity_and_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            e=evidence()
            e.update(scope='HF',completed_at=AT.isoformat(),instruments=[{'symbol':'NIFTY','securityId':'123'}],
                hf_quotes={'NIFTY':research()['indices']['NIFTY']['hf']['hf_quotes']})
            manifest=save(root,e)
            observed=d.load_hf_manifest(manifest,'NIFTY',AT,root)
            self.assertEqual(len(observed['hf_quotes']),151)
            with self.assertRaises(ValueError): d.load_hf_manifest(manifest,'NIFTY',AT+dt.timedelta(seconds=11),root)
            with self.assertRaises(ValueError): d.load_hf_manifest(manifest,'SENSEX',AT,root)
            source=root/(e['collection_id']+'.json');source.write_text(source.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'HASH'): d.load_hf_manifest(manifest,'NIFTY',AT,root)

    def test_news_contradiction_and_stale_prior(self):
        r=research()
        r['news']['normalized']['events']=[{'latency_severity':'critical','butterfly_relevance':'critical'}]
        self.assertEqual(d.compose(r,AT)['action'],'NEED_EVIDENCE')
        r=research();r['news']['normalized']['calibration_asof']='2026-01-01'
        self.assertEqual(d.compose(r,AT)['action'],'NEED_EVIDENCE')

    def test_short_lived_token_does_not_generate_repeatedly(self):
        p=packet();p['auth'].update(expires_at=(AT+dt.timedelta(minutes=30)).isoformat(),attempts_this_pass=1)
        self.assertEqual(m.evaluate(p,now=AT)['action'],'AUTH_HANDOFF')

if __name__=='__main__': unittest.main()
