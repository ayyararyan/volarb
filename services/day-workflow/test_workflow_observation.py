import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

import day_workflow as workflow
import workflow_observation as observation

AT = '2026-09-29T05:00:00+00:00'
NOW = dt.datetime.fromisoformat(AT)


def evidence():
    endpoints = {}
    for name in observation.REQUIRED:
        value = {'identity_verified': True} if name.startswith('profile') else {'available_rupees': 50000} if name.startswith('funds') else []
        endpoints[name] = {'status': 'OK', 'requested_at': AT, 'received_at': AT, 'data': value}
    return {'format': observation.FORMAT, 'mode': 'READ_ONLY', 'provenance': 'OBSERVED',
            'collection_id': str(uuid.uuid4()), 'scope': 'ACCOUNT', 'completed_at': AT,
            'endpoints': endpoints, 'markets': {}, 'blockers': [], 'trading_ready': False,
            'capabilities': {'orders': False, 'scheduling': False, 'financial_ledger': False},
            'account': {'verified': True, 'verified_flat': True, 'open_position_count': 0,
                        'pending_order_count': 0, 'ownership': 'UNASSIGNED'}}


def save(root, e):
    content = json.dumps(e).encode()
    file = root/(e['collection_id']+'.json')
    file.write_bytes(content); file.chmod(0o600)
    manifest = {'format': observation.FORMAT+'.manifest', 'mode': 'READ_ONLY', 'provenance': 'OBSERVED',
                'collection_id': e['collection_id'], 'evidence_file': str(file),
                'sha256': hashlib.sha256(content).hexdigest(), 'completed_at': e['completed_at']}
    path = root/(e['collection_id']+'.manifest.json')
    path.write_text(json.dumps(manifest)); path.chmod(0o600)
    return path


class ObservationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def assess(self, e, now=NOW):
        return observation.assess_manifest(save(self.root, e), root=self.root, now=now)

    def test_observed_account_readiness_never_becomes_trading_readiness(self):
        result = self.assess(evidence())
        self.assertEqual(result['status'], 'READ_ONLY_INPUT_CONNECTED')
        self.assertEqual(result['account_state'], 'VERIFIED_FLAT')
        self.assertEqual(result['mode'], 'OBSERVE')
        self.assertFalse(result['trading_ready'])
        self.assertFalse(result['orders_sent'])
        self.assertFalse(result['jobs_scheduled'])
        self.assertFalse(result['production_ledger_written'])
        self.assertTrue(all(not item['actionable_freshness_verified'] for item in result['market_data'].values()))

    def test_exposure_and_orders_remain_unassigned_not_fake_fills(self):
        e = evidence()
        row = {'securityId': '123', 'exchangeSegment': 'NSE_FNO', 'productType': 'INTRADAY', 'netQty': 10}
        for n in ('positions_before', 'positions_after'): e['endpoints'][n]['data'] = [row]
        e['account'].update(verified_flat=False, open_position_count=1)
        r = self.assess(e)
        self.assertEqual(r['account_state'], 'EXPOSURE_PRESENT')
        self.assertNotIn('fills', r)
        order = {'orderId': '1', 'orderStatus': 'PENDING'}
        for n in ('orders_before', 'orders_after'): e['endpoints'][n]['data'] = [order]
        e['account']['pending_order_count'] = 1
        self.assertEqual(self.assess(e)['account_state'], 'OUTSTANDING_ORDERS')

    def test_fresh_received_timestamp_cannot_hide_stale_request(self):
        e = evidence(); e['endpoints']['positions_before']['requested_at'] = '2026-09-29T04:58:00+00:00'
        self.assertEqual(self.assess(e)['status'], 'BLOCKED')
        self.assertEqual(self.assess(evidence(), NOW+dt.timedelta(seconds=31))['status'], 'BLOCKED')
        self.assertEqual(self.assess(evidence(), NOW-dt.timedelta(seconds=1))['status'], 'BLOCKED')

    def test_missing_endpoint_or_identity_does_not_pass_on_envelope_boolean(self):
        for name in observation.REQUIRED:
            e = evidence(); del e['endpoints'][name]
            self.assertFalse(self.assess(e)['account_verified'])
        e = evidence(); e['endpoints']['profile_after']['data']['identity_verified'] = False
        self.assertEqual(self.assess(e)['account_state'], 'UNVERIFIED')

    def test_positions_funds_and_orders_recomputed_not_summary_trusted(self):
        for mutate in (
            lambda e: e['endpoints']['positions_after'].update(data=[{'securityId':'123','exchangeSegment':'NSE_FNO','productType':'INTRADAY','netQty':1}]),
            lambda e: e['endpoints']['funds_after'].update(data={'available_rupees':40000}),
            lambda e: e['account'].update(verified_flat=False),
            lambda e: e['account'].update(open_position_count=2),
        ):
            e = evidence(); mutate(e)
            self.assertFalse(self.assess(e)['account_verified'])

    def test_unknown_status_boolean_quantity_and_unauthorized_capabilities_block(self):
        e = evidence()
        for n in ('orders_before', 'orders_after'): e['endpoints'][n]['data'] = [{'orderStatus':'MYSTERY'}]
        self.assertFalse(self.assess(e)['account_verified'])
        e = evidence()
        for n in ('positions_before', 'positions_after'):
            e['endpoints'][n]['data'] = [{'securityId':'1','exchangeSegment':'NSE_FNO','productType':'INTRADAY','netQty':False}]
        self.assertFalse(self.assess(e)['account_verified'])
        e = evidence(); e['capabilities']['orders'] = True
        self.assertFalse(self.assess(e)['account_verified'])

    def test_tampering_hash_path_and_synthetic_provenance_rejected(self):
        e = evidence(); manifest = save(self.root, e)
        source = self.root/(e['collection_id']+'.json'); source.write_text(source.read_text()+' ')
        self.assertIn('hash mismatch', observation.assess_manifest(manifest, root=self.root, now=NOW)['blockers'][0])
        e = evidence(); e['provenance'] = 'SYNTHETIC'
        self.assertFalse(self.assess(e)['account_verified'])
        e = evidence(); manifest = save(self.root,e)
        m = json.loads(manifest.read_text()); m['evidence_file'] = '/tmp/other-evidence'; manifest.write_text(json.dumps(m))
        self.assertFalse(observation.assess_manifest(manifest, root=self.root, now=NOW)['account_verified'])

    def test_world_readable_files_and_symlinks_rejected(self):
        e = evidence(); m = save(self.root,e); m.chmod(0o644)
        self.assertFalse(observation.assess_manifest(m, root=self.root, now=NOW)['account_verified'])
        m.chmod(0o600)
        source = self.root/(e['collection_id']+'.json')
        renamed = source.with_suffix('.saved'); source.rename(renamed); source.symlink_to(renamed)
        self.assertFalse(observation.assess_manifest(m, root=self.root, now=NOW)['account_verified'])

    def test_live_evidence_cannot_enter_synthetic_runner(self):
        e = evidence()
        with self.assertRaisesRegex(ValueError, 'LIVE EXECUTION'):
            workflow.transition(workflow.initial('2026-09-29'), e)

    def test_capture_failure_is_sanitized_and_no_shell_or_secrets_in_command(self):
        result = subprocess.CompletedProcess([], 2, '{"code":"WEB_TOKEN_RECOVERY_REQUIRED"}', 'private stderr')
        with patch.object(observation.subprocess, 'run', return_value=result) as run:
            out = observation.capture('account')
            self.assertEqual(out['blockers'], ['WEB_TOKEN_RECOVERY_REQUIRED'])
            args, kw = run.call_args
            self.assertEqual(args[0], ['node', str(observation.COLLECTOR), '--scope', 'account'])
            self.assertNotIn('shell', kw)
            self.assertNotIn('private stderr', str(out))
        with patch.object(observation.subprocess, 'run', side_effect=subprocess.TimeoutExpired('fixture',120)):
            self.assertEqual(observation.capture()['status'], 'BLOCKED')

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            observation.decode('{"verified":false,"verified":true}')

    def test_market_capture_requires_endpoint_binding_and_reports_partial(self):
        e = evidence(); e['scope'] = 'MARKET'
        self.assertEqual(self.assess(e)['status'], 'READ_ONLY_INPUT_PARTIAL')
        for symbol in ('NIFTY','BANKNIFTY','SENSEX'):
            snapshot = {'symbol': symbol, 'expiry': '2026-10-01', 'chain': [{'strike': 25000}]}
            e['markets'][symbol] = {'expiry': '2026-10-01', 'normalized_snapshot': snapshot}
            e['endpoints'][symbol+':chain'] = {'status': 'OK', 'data': snapshot}
        self.assertEqual(self.assess(e)['status'], 'READ_ONLY_INPUT_CONNECTED')
        e['endpoints']['NIFTY:chain'] = {'status': 'UNAVAILABLE'}
        r = self.assess(e)
        self.assertEqual(r['status'], 'READ_ONLY_INPUT_PARTIAL')
        self.assertFalse(r['market_data']['NIFTY']['captured'])


if __name__ == '__main__':
    unittest.main()
