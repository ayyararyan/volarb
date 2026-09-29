#!/usr/bin/env python3
"""One lifetime summary per butterfly, projected from the canonical audit; never fills."""
import argparse
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import io
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

FIELDS = ['Butterfly ID', 'Trade', 'State', 'Opened (IST)', 'Closed (IST)',
          'Booked P&L (gross INR)', 'Open P&L (gross INR)', 'Charges (INR)',
          'Net P&L (INR)', 'Updated (IST)', 'Accounting status', 'Review reference']
from volarb_paths import TRADING_ROOT
EXPECTED_ROOT = TRADING_ROOT


def amount(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        v = Decimal(str(value))
    except InvalidOperation:
        return None
    return v if v.is_finite() else None


def money(v):
    return 'Unknown' if v is None else format(v.quantize(Decimal('0.01')), 'f')


def stamp(value):
    v = dt.datetime.fromisoformat(value)
    if v.tzinfo is None:
        raise ValueError('Accounting timestamp needs a timezone')
    return v


def local_time(value):
    return stamp(value).astimezone(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S') if value else 'Unknown'


def accounting(row):
    a = row.get('analytics_json') or {}
    if isinstance(a, str):
        a = json.loads(a)
    value = a.get('accounting', {})
    if not isinstance(value, dict):
        raise ValueError('analytics_json.accounting must be an object')
    return value


def held_butterfly(row):
    s = row.get('structure', '').upper()
    return row.get('record_type') == 'REVIEW' and 'BUTTERFLY' in s and not any(
        x in s for x in ('CANDIDATE', 'NOT_HELD', 'FLAT'))


def grouped(rows):
    """Resolve explicit cycle IDs; legacy records inherit only unambiguous identity.

    Never group by strikes, centre or expiry. A new entry after closure needs a
    new cycle ID, even when its contracts match. Rows remain in the audit untouched.
    """
    groups, strategies, ids = {}, {}, {}
    for row in rows:
        if row.get('record_type') != 'REVIEW':
            continue
        a = accounting(row)
        if not held_butterfly(row) and a.get('state') != 'CLOSED':
            continue
        strategy = row.get('strategy_id')
        if not strategy:
            raise ValueError('Butterfly review needs strategy_id')
        known = strategies.get(strategy, set())
        cycle = a.get('cycle_id')
        if not cycle:
            if len(known) > 1:
                raise ValueError('Ambiguous cycle: supply accounting.cycle_id')
            cycle = next(iter(known)) if known else strategy
        if not isinstance(cycle, str) or not cycle.strip():
            raise ValueError('Nonempty string cycle_id required')
        if not held_butterfly(row) and cycle not in groups:
            raise ValueError('Closure must reference an existing butterfly cycle')
        prior = ids.get(row.get('supersedes_review_id'))
        if prior and prior != cycle:
            raise ValueError('Correction cannot move a review to another cycle')
        if groups.get(cycle):
            first = groups[cycle][0]
            for k in ('underlying', 'expiry'):
                if row.get(k) and first.get(k) and row[k] != first[k]:
                    raise ValueError('A butterfly cycle cannot cross underlying/expiry')
        groups.setdefault(cycle, []).append(row)
        strategies.setdefault(strategy, set()).add(cycle)
        ids[row['review_id']] = cycle
    return groups


def latest(group, superseded):
    active = [r for r in group if r['review_id'] not in superseded]
    # Correction of an older observation must not overwrite a newer observation.
    return max(active, key=lambda r: (stamp(r.get('review_as_of_ist') or r['recorded_at_ist']),
                                     stamp(r['recorded_at_ist']))) if active else None


def validate_accounting(event, rows):
    """Pre-append checks, also used by projection. Evidence matching remains required."""
    if event.get('record_type') != 'REVIEW':
        return
    a = accounting(event)
    if not held_butterfly(event) and a.get('state') != 'CLOSED':
        return
    groups = grouped(rows)
    if not a.get('cycle_id') and not any(
            r.get('strategy_id') == event.get('strategy_id') for group in groups.values() for r in group):
        raise ValueError('New butterfly requires analytics_json.accounting.cycle_id')
    combined = grouped([*rows, event])
    cycle, group = next((c, g) for c, g in combined.items() if event in g)
    asof = stamp(event.get('review_as_of_ist') or event['recorded_at_ist'])
    state = a.get('state', 'OPEN')
    if state not in {'OPEN', 'CLOSED'}:
        raise ValueError('Accounting state must be OPEN or CLOSED')
    if a.get('opened_at'):
        if not a.get('entry_source_ref') or stamp(a['opened_at']) > asof:
            raise ValueError('Entry time needs evidence and cannot be after observation')
    if state == 'CLOSED':
        if cycle not in groups or any(x in event.get('structure', '').upper() for x in ('CANDIDATE', 'NOT_HELD')):
            raise ValueError('Closure needs a previously owned butterfly cycle')
        if (not a.get('closure_source_ref') or not a.get('closed_at') or
                isinstance(a.get('remaining_units'), bool) or a.get('remaining_units') != 0):
            raise ValueError('Closure needs evidence, closed_at and verified remaining_units=0')
        if amount(event.get('broker_open_pnl_inr')) != 0:
            raise ValueError('Closed butterfly must have verified zero open P&L')
        closed = stamp(a['closed_at'])
        if closed > asof or (a.get('opened_at') and closed < stamp(a['opened_at'])):
            raise ValueError('Invalid closure time')
    elif a.get('closed_at'):
        raise ValueError('Open butterfly cannot have a closure time')
    superseded = {r.get('supersedes_review_id') for r in [*rows, event]}
    prior = latest([r for r in group if r is not event], superseded)
    if prior and accounting(prior).get('state') == 'CLOSED' and state != 'CLOSED' and asof >= stamp(
            prior.get('review_as_of_ist') or prior['recorded_at_ist']):
        raise ValueError('Re-entry after closure requires a new cycle_id')


def project(rows):
    result = []
    superseded = {r.get('supersedes_review_id') for r in rows if r.get('supersedes_review_id')}
    for cycle, group in grouped(rows).items():
        r = latest(group, superseded)
        if r is None:
            continue
        a = accounting(r)
        # Revalidate explicit lifecycle metadata even during standalone rebuild.
        if a:
            validate_accounting(r, [x for x in rows if x is not r])
        booked = amount(r.get('prior_realized_pnl_inr'))
        opened = amount(r.get('broker_open_pnl_inr'))
        charges = amount(r.get('charges_inr'))
        reconciled = all(r.get(k, '').upper() == 'RECONCILED' for k in
                         ('basis_status', 'prior_realized_status', 'charges_status'))
        complete = reconciled and all(v is not None for v in (booked, opened, charges))
        net = booked + opened - charges if complete else None
        closed = a.get('state') == 'CLOSED'
        status = ['Reconciled' if complete else 'Provisional']
        if not closed:
            status.append('broker mark, not exit value')
            quote = r.get('quote_status', '').upper()
            if 'HISTORICAL' in quote or 'NOT EXECUTABLE' in quote or 'NOT_EXECUTABLE' in quote:
                status.append('historical prices' + (' ' + r['price_session'] if r.get('price_session') else ''))
            elif quote != 'EXECUTABLE':
                status.append('price timing unverified')
        if not a.get('cycle_id'):
            status.append('legacy cycle identity')
        trade = ' '.join(filter(None, [r.get('underlying'), r.get('expiry'),
                         'centre ' + r['short_put_strike'] if r.get('short_put_strike') else None]))
        result.append(dict(zip(FIELDS, [cycle, trade or r['strategy_id'],
            'Completed' if closed else 'Open at last check', local_time(a.get('opened_at')),
            local_time(a.get('closed_at')) if closed else '', money(booked), money(opened), money(charges),
            money(net), local_time(r.get('review_as_of_ist') or r['recorded_at_ist']),
            '; '.join(status), r['review_id']])))
    return result


def details(rows, trade_rows, cycle):
    """Drill down without duplicating raw evidence or guessing leg assignments."""
    from trade_ledger import validate_rows
    groups = grouped(rows)
    if cycle not in groups:
        raise ValueError('Unknown butterfly ID')
    active = validate_rows(trade_rows)
    assignments = {r['reference_event_id']: r for r in active if r['event_type'] == 'ASSIGNMENT'}
    linked, unassigned = [], []
    for r in active:
        if r['event_type'] == 'ASSIGNMENT':
            continue
        link = assignments.get(r['event_id'], r)
        if link.get('cycle_id') == cycle:
            linked.append(r)
        elif not link.get('cycle_id'):
            unassigned.append(r['event_id'])
    return {'summary': next(r for r in project(rows) if r['Butterfly ID'] == cycle),
            'review_history_ids': [r['review_id'] for r in groups[cycle]],
            'active_linked_broker_events': linked,
            'unassigned_broker_event_ids': unassigned,
            'note': 'Unassigned events are not attributed to this butterfly. OPENING_BALANCE is not a fill. '
                    'Full original/corrected evidence remains in ledger/tradelog.csv; '
                    'reviews remain in ledger/butterfly_reviews.json.'}


def refresh(rows, root):
    # Caller holds canonical review lock. No mkdir and no alternate output location.
    root = Path(root)
    if root.resolve() != EXPECTED_ROOT.resolve() or not (root/'ledger/butterfly_reviews.json').is_file():
        raise OSError('STORAGE_UNAVAILABLE: canonical accounting ledger missing or wrong root')
    destination = root/'ledger/simple_ledger.csv'
    projected = project(rows)
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader(); writer.writerows(projected)
    content = buf.getvalue()
    if destination.exists() and destination.read_bytes() == content.encode('utf-8'):
        return {'status': 'UNCHANGED', 'rows': len(projected)}
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=destination.parent, prefix='.simple-write-', delete=False, encoding='utf-8', newline='') as f:
            name = f.name; f.write(content); f.flush(); os.fsync(f.fileno())
        os.replace(name, destination); name = None
    finally:
        if name: os.unlink(name)
    if destination.read_bytes() != content.encode('utf-8'):
        raise OSError('STORAGE_READBACK_FAILED: simple ledger')
    return {'status': 'READBACK_VERIFIED', 'rows': len(projected)}


if __name__ == '__main__':
    import fcntl
    from review_scorecard import ROOT, read_rows
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--details', metavar='BUTTERFLY_ID', help='Read linked broker events and review history; no writes')
    args = parser.parse_args()
    with (ROOT/'ledger/.butterfly_reviews.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.details:
            from trade_ledger import read_ledger
            if not (ROOT/'ledger/tradelog.csv').is_file():
                raise OSError('STORAGE_EVIDENCE_UNAVAILABLE: transaction ledger missing')
            result = details(read_rows(), read_ledger(ROOT/'ledger/tradelog.csv'), args.details)
        else:
            result = refresh(read_rows(), ROOT)
        print(json.dumps(result, indent=2))
