import copy
import csv
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import day_workflow as w
import workflow_accounting as a
import trade_ledger as t
import review_scorecard as r
import simple_ledger as simple
import master_workflow as m
from test_workflow_observation import evidence, save
from test_master_workflow import packet, research

AT=w.stamp('2026-09-29T10:00:00+05:30')


def fixture(closed=False,costs=True):
    e=evidence();e['completed_at']=AT.isoformat()
    for ep in e['endpoints'].values():ep['requested_at']=ep['received_at']=AT.isoformat()
    raw=[];positions=[];quotes=[]
    for i,(role,strike,option,sign,price) in enumerate(zip(w.ROLES,[24000,25000,25000,26000],['PE','PE','CE','CE'],[1,-1,-1,1],[10,470,470,10])):
        trade={'exchangeTradeId':'fill-'+str(i),'orderId':'order-'+str(i),'securityId':str(i+1),
            'exchangeSegment':'NSE_FNO','productType':'INTRADAY','transactionType':'BUY' if sign>0 else 'SELL',
            'tradedQuantity':10,'tradedPrice':price,'exchangeTime':'2026-09-29 09:50:00',
            'tradingSymbol':'NIFTY TEST '+str(i),'drvExpiryDate':'2026-10-06','drvStrikePrice':strike,'drvOptionType':option}
        raw.append(trade)
        if closed:
            raw.append({**trade,'exchangeTradeId':'exit-'+str(i),'orderId':'close-'+str(i),
                'transactionType':'SELL' if sign>0 else 'BUY','exchangeTime':'2026-09-29 09:55:00'})
        else:
            positions.append({'securityId':str(i+1),'exchangeSegment':'NSE_FNO','productType':'INTRADAY','netQty':sign*10,
                'drvExpiryDate':'2026-10-06','drvStrikePrice':strike,'drvOptionType':option})
        quotes.append({'securityId':str(i+1),'exchangeSegment':'NSE_FNO','last_trade_time':'2026-09-29 10:00:00',
            'bid':price,'ask':price+1,'bid_size':10,'ask_size':10})
    for k in ['positions_before','positions_after']:e['endpoints'][k]['data']=positions
    e['endpoints']['trades']['data']=raw
    e['endpoints']['position_quotes']={'status':'OK','requested_at':AT.isoformat(),'received_at':AT.isoformat(),'data':quotes}
    e['account'].update(verified_flat=closed,open_position_count=0 if closed else 4)
    receipt={'evidence_manifest':'synthetic-private-manifest','evidence_sha256':'a'*64}
    rows=[]
    for fill in a.observed_fills(e,receipt['evidence_manifest'],receipt['evidence_sha256'],AT):
        item=dict(fill);item.update(strategy_id='test-strategy',cycle_id='test-cycle',strategy_version='1',
            leg_id=fill['security_id'],lifecycle_role='EXIT' if fill['broker_fill_id'].startswith('exit') else 'ENTRY',
            linkage_provenance='RECORDED_STRATEGY_ORDER',lot_size_units='10')
        rows.append(t.normalize(item))
    if costs:
        rows.append(t.normalize({'event_type':'COST','event_time':'2026-09-29T09:59:00+05:30',
            'trading_date':'2026-09-29','broker':a.BROKER,'account_alias':a.ACCOUNT,'source_record_id':'cost',
            'source_ref':'synthetic-note','source_sha256':'b'*64,'source_kind':'CONTRACT_NOTE','provenance':'OBSERVED',
            'currency':'INR','cost_component':'TOTAL','gross_cashflow':'-100'}))
    return e,receipt,rows


class AccountingTest(unittest.TestCase):
    def test_open_reconciles_fills_inventory_and_executable_pnl(self):
        e,receipt,rows=fixture()
        out=a.reconcile(e,receipt,rows,'test-cycle',AT)
        self.assertEqual(out['status'],'RECONCILED')
        self.assertEqual(out['net_liquidation_pnl_rupees'],-120)
        self.assertFalse(out['closed'])

    def test_closure_and_unknown_costs(self):
        for costs in [True,False]:
            e,receipt,rows=fixture(True,costs)
            out=a.reconcile(e,receipt,rows,'test-cycle',AT)
            self.assertTrue(out['closed'])
            self.assertEqual(out['net_liquidation_pnl_rupees'],-100 if costs else None)

    def test_duplicate_broker_fill_deduplicated_conflict_rejected(self):
        e,receipt,rows=fixture()
        e['endpoints']['trades']['data'].append(copy.deepcopy(e['endpoints']['trades']['data'][0]))
        self.assertEqual(len(a.observed_fills(e,'ref','a'*64,AT)),4)
        e['endpoints']['trades']['data'][-1]['tradedPrice']+=1
        with self.assertRaisesRegex(ValueError,'CONFLICTING'):a.observed_fills(e,'ref','a'*64,AT)

    def test_import_never_infers_cycle(self):
        e,receipt,rows=fixture()
        incoming=a.preview_import(e,receipt,[],AT)
        self.assertEqual(len(incoming),4)
        self.assertTrue(all(not f['cycle_id'] and not f['lot_size_units'] for f in incoming))
        self.assertEqual(a.preview_import(e,receipt,rows,AT),[])

    def test_missing_fill_changed_price_unassigned_cycle_and_positions_block(self):
        for mutate in [lambda e,rs:e['endpoints']['trades']['data'].pop(),
            lambda e,rs:e['endpoints']['trades']['data'][0].update(tradedPrice=11),
            lambda e,rs:e['endpoints']['positions_after']['data'][0].update(netQty=9),
            lambda e,rs:e['account'].update(pending_order_count=1),
            lambda e,rs:e['endpoints']['positions_after']['data'][0].update(drvStrikePrice=123)]:
            e,receipt,rows=fixture();mutate(e,rows)
            with self.assertRaises(ValueError):a.reconcile(e,receipt,rows,'test-cycle',AT)
        e,receipt,rows=fixture()
        with self.assertRaises(ValueError):a.reconcile(e,receipt,rows,'guessed',AT)

    def test_stale_quote_and_shallow_depth_fail(self):
        for change in [{'last_trade_time':'2026-09-29 09:58:00'},{'bid_size':1},{'bid':None}]:
            e,receipt,rows=fixture();e['endpoints']['position_quotes']['data'][0].update(change)
            with self.assertRaises(ValueError):a.reconcile(e,receipt,rows,'test-cycle',AT)

    def test_master_uses_derived_pnl_not_caller_pnl(self):
        e,receipt,rows=fixture()
        for q in e['endpoints']['position_quotes']['data']:
            if q['securityId'] in {'2','3'}:q['ask']=530
        with tempfile.TemporaryDirectory() as folder:
            path=save(Path(folder),e)
            p=packet();p.update(mode='OBSERVE',account_manifest=str(path),cycle_id='test-cycle',valuation={'net_liquidation_pnl_rupees':999999})
            with patch.object(t,'read_ledger',return_value=rows):
                out=m.evaluate(p,now=AT,evidence_root=Path(folder))
            self.assertEqual(out['action'],'SQUARE_OFF',out)
            self.assertEqual(out['terminal_rule'],'LOSS')

    def test_no_costs_cannot_produce_hold_but_does_not_mask_expiry_exit(self):
        e,receipt,rows=fixture(costs=False)
        with tempfile.TemporaryDirectory() as folder:
            path=save(Path(folder),e)
            p=packet();p.update(mode='OBSERVE',account_manifest=str(path),cycle_id='test-cycle',research=research())
            p['research']['position_symbol']='NIFTY'
            p['research']['indices']={'NIFTY':p['research']['indices']['NIFTY']}
            p['research']['indices']['NIFTY']['expiry']='2026-10-06'
            with patch.object(t,'read_ledger',return_value=rows):
                self.assertEqual(m.evaluate(p,now=AT,evidence_root=Path(folder))['action'],'NEED_EVIDENCE')
                p['research']['indices']['NIFTY']['expiry_exit_gate']='EXIT'
                self.assertEqual(m.evaluate(p,now=AT,evidence_root=Path(folder))['action'],'SQUARE_OFF')

    def test_closure_stops_reentry_even_without_claimed_cycle_closed(self):
        e,receipt,rows=fixture(True)
        with tempfile.TemporaryDirectory() as folder:
            path=save(Path(folder),e);p=packet();p.update(mode='OBSERVE',account_manifest=str(path),cycle_id='test-cycle')
            with patch.object(t,'read_ledger',return_value=rows):
                self.assertEqual(m.evaluate(p,now=AT,evidence_root=Path(folder))['action'],'STOP')
                p.pop('cycle_id')
                self.assertEqual(m.evaluate(p,now=AT,evidence_root=Path(folder))['action'],'RECONCILE_POSITION')

    def test_shared_writer_closure_retry_one_cycle_and_projection(self):
        e,receipt,rows=fixture(True)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'ledger').mkdir()
            tradepath=root/'ledger/tradelog.csv';t.import_rows(tradepath,rows)
            parent={'review_id':'parent','record_type':'REVIEW','recorded_at_ist':AT.isoformat(),'strategy_id':'test-strategy',
                'schema_version':'2','parent_review_id':'','supersedes_review_id':'',
                'structure':'IRON_BUTTERFLY','underlying':'NIFTY','expiry':'2026-10-06','review_as_of_ist':AT.isoformat(),
                'short_put_strike':'25000','source_refs':'fixture','prior_realized_pnl_inr':'','broker_open_pnl_inr':'',
                'charges_inr':'','basis_status':'','prior_realized_status':'','charges_status':'','quote_status':'',
                'analytics_json':{'accounting':{'cycle_id':'test-cycle','state':'OPEN'}}}
            doc={'format':r.STORE_FORMAT,'format_version':1,'event_fields':list(parent),'events':[parent]}
            ledger=root/'ledger/butterfly_reviews.json';ledger.write_text(json.dumps(doc))
            with patch.object(r,'ROOT',root),patch.object(r,'LEDGER',ledger),patch.object(t,'DEFAULT_LEDGER',tradepath),patch.object(simple,'EXPECTED_ROOT',root),patch.object(a,'verified_account_evidence',return_value=(receipt,e)):
                with patch.object(simple,'refresh',side_effect=OSError('injected projection failure')):
                    with self.assertRaisesRegex(OSError,'REVIEW_COMMITTED'):
                        a.commit_cycle('fixture','test-cycle','parent',now=AT)
                out=a.commit_cycle('fixture','test-cycle','parent',now=AT)
                self.assertEqual(len(out['appended_ids']),8)
                content=ledger.read_bytes()
                self.assertEqual(a.commit_cycle('fixture','test-cycle','parent',now=AT)['appended_ids'],[])
                self.assertEqual(content,ledger.read_bytes())
                with (root/'ledger/simple_ledger.csv').open() as stream:
                    projected=list(csv.DictReader(stream))
                self.assertEqual(len(projected),1)
                self.assertEqual(projected[0]['State'],'Completed')
                self.assertIn('-100',json.dumps(projected))
                oldcost=next(x for x in t.read_ledger(tradepath) if x['event_type']=='COST')
                revised={**oldcost,'event_id':'','source_revision':'2','supersedes_event_id':oldcost['event_id'],'gross_cashflow':'-120'}
                t.import_rows(tradepath,[revised])
                corrected=a.commit_cycle('fixture','test-cycle','parent',now=AT)
                self.assertEqual(len(corrected['appended_ids']),1)
                current=[x for x in r.active(r.read_rows()) if x['review_id'].startswith('workflow-closure-')]
                self.assertEqual(len(current),1)
                self.assertEqual(current[0]['charges_inr'],'120.0')
                self.assertEqual(len(simple.project(r.read_rows())),1)

    def test_partial_exit_is_recovery_not_hold_or_closure(self):
        e,receipt,rows=fixture()
        body=copy.deepcopy(e['endpoints']['trades']['data'][1])
        body.update(exchangeTradeId='partial-exit',orderId='partial-order',transactionType='BUY',tradedQuantity=5,
                    exchangeTime='2026-09-29 09:55:00')
        e['endpoints']['trades']['data'].append(body)
        for name in ('positions_before','positions_after'):
            e['endpoints'][name]['data']=copy.deepcopy(e['endpoints'][name]['data'])
            e['endpoints'][name]['data'][1]['netQty']=-5
        fill=a.broker_fill(body,'fixture','a'*64,AT)
        template=rows[1]
        for k in ('strategy_id','cycle_id','strategy_version','leg_id','linkage_provenance','lot_size_units'):
            fill[k]=template[k]
        fill['lifecycle_role']='EXIT'
        rows.append(t.normalize(fill))
        out=a.reconcile(e,receipt,rows,'test-cycle',AT)
        self.assertEqual(out['status'],'PARTIAL_EXIT_REQUIRES_RECOVERY')
        self.assertFalse(out['closed'])

    def test_explicit_assignment_is_used_not_contract_geometry_inference(self):
        e,receipt,rows=fixture(costs=False)
        fill=dict(rows[0]); linkage={k:fill[k] for k in ('strategy_id','cycle_id','strategy_version','leg_id','lifecycle_role','linkage_provenance')}
        for k in linkage:fill[k]=''
        rows[0]=t.normalize(fill)
        with self.assertRaisesRegex(ValueError,'UNASSIGNED'):a.reconcile(e,receipt,rows,'test-cycle',AT)
        assignment={k:rows[0][k] for k in ('event_time','trading_date','broker','account_alias','source_ref','source_sha256')}
        assignment.update(event_type='ASSIGNMENT',source_record_id='explicit-link',source_kind='USER_RECORD',
            provenance='USER_RECORDED',reference_event_id=rows[0]['event_id'],**linkage)
        assignment['linkage_provenance']='USER_CONFIRMED'
        rows.append(t.normalize(assignment))
        self.assertEqual(a.reconcile(e,receipt,rows,'test-cycle',AT)['status'],'RECONCILED')

    def test_canonical_fill_import_retry(self):
        e,receipt,rows=fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'ledger').mkdir();target=root/'ledger/tradelog.csv';t.import_rows(target,[])
            with patch.object(r,'ROOT',root),patch.object(t,'DEFAULT_LEDGER',target),patch.object(a,'verified_account_evidence',return_value=(receipt,e)):
                self.assertEqual(a.commit_fills('fixture',now=AT)['unassigned_new_fills'],4)
                self.assertEqual(a.commit_fills('fixture',now=AT)['unassigned_new_fills'],0)
                self.assertTrue(all(not x['cycle_id'] for x in t.read_ledger(target)))

if __name__=='__main__':unittest.main()
