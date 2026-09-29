"""Verified local Dhan evidence ingress. OBSERVED is never relabelled SYNTHETIC.

Acquisition only: this does not choose a trade, dispatch orders, schedule a job,
or append to financial/research ledgers. The existing SHADOW machine stays isolated.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import uuid

from volarb_paths import EVIDENCE_ROOT, COLLECTOR
ROOT = EVIDENCE_ROOT
FORMAT = 'volarb.dhan.readonly.v1'
REQUIRED = ('profile_before', 'profile_after', 'positions_before', 'positions_after',
            'orders_before', 'orders_after', 'funds_before', 'funds_after', 'trades')
TERMINAL = {'TRADED', 'CANCELLED', 'REJECTED', 'EXPIRED'}
KNOWN = TERMINAL | {'TRANSIT', 'PENDING', 'PART_TRADED'}
POSITION_KEYS = ('securityId', 'exchangeSegment', 'productType', 'netQty',
                 'drvExpiryDate', 'drvOptionType', 'drvStrikePrice')


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.tzinfo is not None, 'Missing evidence timezone')
    return parsed


def numeric(value):
    need(type(value) in (float, int, str) and str(value).strip() != '', 'Invalid numeric evidence')
    number = float(value)
    need(math.isfinite(number), 'Nonfinite numeric evidence')
    return number


def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, 'Duplicate JSON key')
        out[key] = value
    return out


def decode(content):
    def invalid(_):
        raise ValueError('Nonfinite JSON')
    return json.loads(content, object_pairs_hook=unique_pairs, parse_constant=invalid)


def private_bytes(file, root):
    file, root = Path(file).absolute(), Path(root).absolute()
    need(root.resolve() == root, 'Symlinked evidence root')
    need(file.parent == root, 'Evidence must be directly within private root')
    directory = root.lstat()
    need(stat.S_ISDIR(directory.st_mode) and not directory.st_mode & 0o077
         and directory.st_uid == os.getuid(), 'Private evidence directory required')
    # NOFOLLOW prevents a symlink swap at the file-open boundary.
    fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        need(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077
             and info.st_uid == os.getuid(), 'Private evidence file required')
        need(info.st_size <= 32 * 1024 * 1024, 'Evidence file unexpectedly large')
        return stream.read()


def canonical_rows(rows):
    need(isinstance(rows, list), 'Broker rows unavailable')
    return sorted(json.dumps(r, sort_keys=True, allow_nan=False) for r in rows)


def position_keys(rows):
    need(isinstance(rows, list), 'Positions unavailable')
    out = []
    for row in rows:
        need(isinstance(row, dict) and str(row.get('securityId', '')).isdigit()
             and isinstance(row.get('exchangeSegment'), str) and isinstance(row.get('productType'), str),
             'Position identity unavailable')
        quantity = numeric(row['netQty'])
        need(quantity.is_integer(), 'Noninteger position quantity')
        item = {key: row.get(key) for key in POSITION_KEYS}
        item['securityId'], item['netQty'] = str(row['securityId']), int(quantity)
        out.append(item)
    return out


def assess_manifest(manifest_file, *, root=ROOT, now=None):
    """Return a read-only input receipt; no workflow state or ledger is changed."""
    now = now or dt.datetime.now(dt.timezone.utc)
    result = {'mode': 'OBSERVE', 'provenance': 'OBSERVED', 'status': 'BLOCKED',
              'account_verified': False, 'account_state': 'UNVERIFIED',
              'trading_ready': False, 'orders_sent': False, 'jobs_scheduled': False,
              'production_ledger_written': False, 'blockers': [],
              'missing_layers': ['NEWS_FILTER', 'HF_RV', 'EXACT_CANDIDATE_QUOTES_AND_MARGIN',
                                 'COST_BOUNDS', 'STRATEGY_OWNERSHIP']}
    try:
        manifest = decode(private_bytes(manifest_file, root))
        need(manifest.get('format') == FORMAT+'.manifest' and manifest.get('mode') == 'READ_ONLY'
             and manifest.get('provenance') == 'OBSERVED', 'Observed manifest required')
        cid = str(uuid.UUID(manifest['collection_id']))
        need(cid == manifest['collection_id'], 'Invalid collection ID')
        need(Path(manifest_file).name == cid+'.manifest.json', 'Manifest name mismatch')
        expected_file = Path(root)/f'{cid}.json'
        need(manifest['evidence_file'] == str(expected_file), 'Evidence path mismatch')
        content = private_bytes(expected_file, root)
        need(hmac.compare_digest(hashlib.sha256(content).hexdigest(), manifest['sha256']), 'Evidence hash mismatch')
        evidence = decode(content)
        need(evidence.get('format') == FORMAT and evidence.get('mode') == 'READ_ONLY'
             and evidence.get('provenance') == 'OBSERVED' and evidence.get('collection_id') == cid,
             'Observed evidence identity mismatch')
        need(evidence.get('capabilities') == {'orders': False, 'scheduling': False, 'financial_ledger': False}
             and evidence.get('trading_ready') is False, 'Unexpected mutation capability')
        need(evidence['completed_at'] == manifest['completed_at'], 'Manifest clock mismatch')
        completion = timestamp(evidence['completed_at'])
        need(0 <= (now-completion).total_seconds() <= 30, 'Stale/future observation')
        endpoints = evidence['endpoints']
        for name in REQUIRED:
            endpoint = endpoints.get(name, {})
            need(endpoint.get('status') == 'OK', 'Missing/unavailable endpoint: '+name)
            began, ended = timestamp(endpoint['requested_at']), timestamp(endpoint['received_at'])
            need(began <= ended <= completion <= now and (now-began).total_seconds() <= 30,
                 'Stale/incoherent endpoint: '+name)
        need(all(endpoints[n]['data'].get('identity_verified') is True
                 for n in ('profile_before', 'profile_after')), 'Account identity unverified')
        data = lambda n: endpoints[n]['data']
        before, after = position_keys(data('positions_before')), position_keys(data('positions_after'))
        need(canonical_rows(before) == canonical_rows(after), 'Positions changed during acquisition')
        need(canonical_rows(data('orders_before')) == canonical_rows(data('orders_after')), 'Orders changed during acquisition')
        need(numeric(data('funds_before')['available_rupees']) == numeric(data('funds_after')['available_rupees']),
             'Funds changed during acquisition')
        need(isinstance(data('trades'), list), 'Trade evidence unavailable')
        orders = data('orders_after')
        need(all(isinstance(o, dict) and o.get('orderStatus') in KNOWN for o in orders), 'Unknown order status')
        need(evidence['account'].get('verified') is True, 'Collector did not verify account')
        open_count = sum(p['netQty'] != 0 for p in after)
        pending_count = sum(o['orderStatus'] not in TERMINAL for o in orders)
        flat = open_count == 0 and pending_count == 0
        need(evidence['account'].get('verified_flat') is flat, 'Flatness summary mismatch')
        need(evidence['account'].get('open_position_count') == open_count
             and evidence['account'].get('pending_order_count') == pending_count, 'Account count mismatch')
        result.update(status='READ_ONLY_INPUT_CONNECTED', account_verified=True,
                      account_state='OUTSTANDING_ORDERS' if pending_count else 'EXPOSURE_PRESENT' if open_count else 'VERIFIED_FLAT',
                      evidence_manifest=str(manifest_file), evidence_sha256=manifest['sha256'],
                      observed_at=evidence['completed_at'])
        result['market_data'] = {}
        for symbol in ('NIFTY', 'BANKNIFTY', 'SENSEX'):
            item = evidence.get('markets', {}).get(symbol, {})
            chain_endpoint = endpoints.get(symbol+':chain', {})
            snapshot = item.get('normalized_snapshot')
            captured = (isinstance(snapshot, dict) and chain_endpoint.get('status') == 'OK'
                        and chain_endpoint.get('data') == snapshot and snapshot.get('symbol') == symbol
                        and snapshot.get('expiry') == item.get('expiry')
                        and isinstance(snapshot.get('chain'), list) and bool(snapshot['chain']))
            result['market_data'][symbol] = {'captured': captured,
                                            'actionable_freshness_verified': False}
        if evidence.get('scope') == 'MARKET' and not all(x['captured'] for x in result['market_data'].values()):
            result['status'] = 'READ_ONLY_INPUT_PARTIAL'
        result['acquisition_blockers'] = evidence.get('blockers', [])
        # No automatic geometry adoption, pseudo fills, candidate or HOLD decision.
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        # Do not surface private broker payloads; errors here are local schema checks.
        result['blockers'] = [str(error) if not isinstance(error, OSError) else 'Private evidence unavailable or unsafe']
    return result


def capture(scope='account'):
    need(scope in {'account', 'market', 'position'}, 'Invalid capture scope')
    try:
        proc = subprocess.run(['node', str(COLLECTOR), '--scope', scope],
                              cwd=COLLECTOR.parent.parent, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return {'mode': 'OBSERVE', 'status': 'BLOCKED', 'blockers': ['Collector unavailable or timed out'],
                'account_verified': False, 'trading_ready': False, 'orders_sent': False,
                'jobs_scheduled': False, 'production_ledger_written': False}
    try:
        receipt = decode(proc.stdout)
    except (ValueError, TypeError):
        return {'mode': 'OBSERVE', 'status': 'BLOCKED', 'blockers': ['Collector returned no valid receipt'],
                'account_verified': False, 'trading_ready': False, 'orders_sent': False,
                'jobs_scheduled': False, 'production_ledger_written': False}
    if receipt.get('manifest_file'):
        return assess_manifest(receipt['manifest_file'])
    # CLI only emits sanitized error codes; never forward raw stdout/stderr.
    code = receipt.get('code', 'READ_ONLY_CAPTURE_FAILED')
    if not isinstance(code, str) or not code.replace('_', '').isalnum() or len(code) > 100:
        code = 'READ_ONLY_CAPTURE_FAILED'
    return {'mode': 'OBSERVE', 'status': 'BLOCKED', 'blockers': [code], 'account_verified': False,
            'trading_ready': False, 'orders_sent': False, 'jobs_scheduled': False, 'production_ledger_written': False}


def verified_account_evidence(manifest_file, *, root=ROOT, now=None):
    """Return independently verified account evidence, never trust a caller receipt."""
    receipt = assess_manifest(manifest_file, root=root, now=now)
    need(receipt['account_verified'] is True, 'ACCOUNT_MANIFEST_UNVERIFIED')
    manifest = decode(private_bytes(manifest_file, root))
    content = private_bytes(manifest['evidence_file'], root)
    need(hmac.compare_digest(hashlib.sha256(content).hexdigest(), receipt['evidence_sha256']),
         'ACCOUNT_CHANGED_AFTER_VERIFICATION')
    return receipt, decode(content)
