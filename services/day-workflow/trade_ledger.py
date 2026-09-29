#!/usr/bin/env python3
"""Offline evidence-ledger for recorded options events; never connects to a broker."""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile

FIELDS = """schema_version event_id recorded_at event_time trading_date broker account_alias
event_type source_record_id source_revision source_ref source_sha256 source_kind provenance
supersedes_event_id reference_event_id exchange segment security_id symbol underlying expiry
strike option_type product broker_order_id broker_fill_id side quantity_units lot_size_units
quantity_lots price_per_unit gross_cashflow currency cost_component strategy_id cycle_id
strategy_version leg_id lifecycle_role linkage_provenance basis_status basis_evidence_ref notes""".split()
TYPES = {"FILL", "OPENING_BALANCE", "POSITION_SNAPSHOT", "SETTLEMENT", "COST", "ASSIGNMENT", "VOID"}
INSTRUMENT_TYPES = {"FILL", "OPENING_BALANCE", "POSITION_SNAPSHOT", "SETTLEMENT"}
SOURCES = {"BROKER_EXPORT", "CONTRACT_NOTE", "EXCHANGE_STATEMENT", "USER_RECORD"}
LIFECYCLES = {"ENTRY", "EXIT", "RECENTER_OPEN", "RECENTER_CLOSE", "SETTLEMENT", "CARRY_BASELINE", "UNKNOWN"}
COSTS = {"TOTAL", "BROKERAGE", "STT", "EXCHANGE_FEES", "SEBI_FEES", "GST", "STAMP_DUTY", "OTHER"}
from volarb_paths import TRADING_ROOT
DEFAULT_LEDGER = TRADING_ROOT / "ledger" / "tradelog.csv"
INSTRUMENT_KEY_FIELDS = ("broker", "account_alias", "exchange", "segment", "security_id", "product", "currency", "underlying", "expiry", "strike", "option_type")


class LedgerError(ValueError):
    pass


def fail(message):
    raise LedgerError(message)


def decimal(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{field}: expected finite decimal, got {value!r}")
    if not number.is_finite():
        fail(f"{field}: non-finite values prohibited")
    return number


def number_text(value):
    return format(value.normalize(), "f") if value else "0"


def timestamp(value, field):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        fail(f"{field}: require ISO-8601 timezone-aware timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(f"{field}: timezone offset is mandatory")
    return parsed


def date(value, field):
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return dt.date.fromisoformat(value)
    except (ValueError, TypeError):
        fail(f"{field}: require YYYY-MM-DD")


def require(row, *fields):
    for field in fields:
        if not row[field]:
            fail(f"{row['event_type'] or 'row'}: required field {field} missing")


def instrument_key(row):
    # Vendor security IDs can be recycled; the dated full contract remains distinct.
    return tuple(row[f] for f in INSTRUMENT_KEY_FIELDS)


def identity(row):
    """Broker fills deduplicate independently of export filename or source row ID."""
    base = [row["broker"], row["account_alias"], row["event_type"]]
    kind = row["event_type"]
    if kind == "FILL":
        base += [row["trading_date"], row["exchange"], row["segment"], row["broker_fill_id"]]
    elif kind == "COST":
        base += [row["trading_date"], row["currency"], row["cost_component"]]
    else:
        base += [row["source_record_id"]]
    return tuple(base)


def event_id(row):
    payload = json.dumps([identity(row), row["source_revision"]], separators=(",", ":"))
    return "evt_" + hashlib.sha256(payload.encode()).hexdigest()[:32]


def normalize(raw):
    if not isinstance(raw, dict):
        fail("Each event must be an object")
    extra = set(raw) - set(FIELDS)
    if extra:
        fail(f"Unknown fields: {sorted(map(str, extra))}")
    if any(isinstance(value, (dict, list, bool)) for value in raw.values()):
        fail("Event fields must be scalar strings/numbers or null, not nested objects/lists/booleans")
    row = {field: "" if raw.get(field) is None else str(raw.get(field, "")).strip() for field in FIELDS}
    row["schema_version"] = row["schema_version"] or "1"
    if row["schema_version"] != "1":
        fail("Unsupported schema_version")
    row["source_revision"] = row["source_revision"] or "1"
    if not row["source_revision"].isdigit() or int(row["source_revision"]) < 1:
        fail("source_revision must be positive integer")
    row["source_revision"] = str(int(row["source_revision"]))
    require(row, "event_type", "event_time", "trading_date", "broker", "account_alias", "source_record_id", "source_ref", "source_sha256", "source_kind", "provenance")
    if row["event_type"] not in TYPES:
        fail("Unsupported event_type")
    timestamp(row["event_time"], "event_time")
    date(row["trading_date"], "trading_date")
    if not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"]):
        fail("source_sha256 must be lower-case SHA-256 of preserved evidence")
    if row["source_kind"] not in SOURCES:
        fail("Unsupported source_kind")
    expected_provenance = "USER_RECORDED" if row["source_kind"] == "USER_RECORD" else "OBSERVED"
    if row["provenance"] != expected_provenance:
        fail("provenance must distinguish observed source from user record; estimates/proxies prohibited")
    if row["event_type"] in {"FILL", "SETTLEMENT", "COST"} and row["source_kind"] == "USER_RECORD":
        fail("FILL/SETTLEMENT/COST require broker/exchange evidence, not a user reconstruction")
    kind = row["event_type"]
    if kind in INSTRUMENT_TYPES:
        require(row, "exchange", "segment", "security_id", "symbol", "underlying", "expiry", "strike", "option_type", "product", "quantity_units", "currency")
        date(row["expiry"], "expiry")
        if row["option_type"] not in {"CE", "PE"}:
            fail("option_type must be CE or PE")
        quantity = decimal(row["quantity_units"], "quantity_units")
        if quantity != quantity.to_integral_value():
            fail("quantity_units must be a signed integer number of underlying units")
        row["quantity_units"] = number_text(quantity)
        strike = decimal(row["strike"], "strike")
        if strike <= 0:
            fail("strike must be positive")
        row["strike"] = number_text(strike)
        if row["lot_size_units"]:
            lot = decimal(row["lot_size_units"], "lot_size_units")
            if lot <= 0 or lot != lot.to_integral_value():
                fail("lot_size_units must be a positive integer from contract evidence")
            row["lot_size_units"] = number_text(lot)
            lots = quantity / lot
            if row["quantity_lots"] and decimal(row["quantity_lots"], "quantity_lots") != lots:
                fail("quantity_lots inconsistent with units / lot size")
            row["quantity_lots"] = number_text(lots)
        elif row["quantity_lots"]:
            fail("quantity_lots cannot be populated without recorded lot size")
        if kind in {"FILL", "SETTLEMENT"}:
            require(row, "price_per_unit")
            price = decimal(row["price_per_unit"], "price_per_unit")
            if price < 0 or quantity == 0:
                fail("Execution/settlement requires nonzero units and nonnegative price")
            if kind == "FILL":
                require(row, "broker_fill_id", "broker_order_id", "side")
                if row["side"] != ("BUY" if quantity > 0 else "SELL"):
                    fail("BUY must have positive units; SELL negative units")
            elif row["side"]:
                fail("SETTLEMENT has no synthetic buy/sell side")
            if kind == "SETTLEMENT" and (row["broker_fill_id"] or row["broker_order_id"]):
                fail("SETTLEMENT must not invent executed order/fill IDs")
            gross = -quantity * price
            if row["gross_cashflow"] and decimal(row["gross_cashflow"], "gross_cashflow") != gross:
                fail("gross_cashflow must equal -signed units * price, excluding costs")
            row["gross_cashflow"] = number_text(gross)
            row["price_per_unit"] = number_text(price)
        else:
            if any(row[f] for f in ("side", "broker_order_id", "broker_fill_id", "price_per_unit", "gross_cashflow")):
                fail("Opening balances/snapshots are inventory observations, never synthetic executions, prices or cash flows")
        if kind == "OPENING_BALANCE":
            row["basis_status"] = row["basis_status"] or "UNKNOWN"
            if row["basis_status"] not in {"UNKNOWN", "RECONCILED"}:
                fail("basis_status must be UNKNOWN or RECONCILED")
            if row["basis_status"] == "RECONCILED":
                require(row, "basis_evidence_ref")
    else:
        if any(row[f] for f in ("quantity_units", "lot_size_units", "quantity_lots", "price_per_unit", "side", "broker_fill_id", "broker_order_id")):
            fail(f"{kind} must not contain execution/quantity fields")
        if kind == "COST":
            require(row, "currency", "gross_cashflow", "cost_component")
            if row["cost_component"] not in COSTS:
                fail("Unsupported cost_component")
            row["gross_cashflow"] = number_text(decimal(row["gross_cashflow"], "gross_cashflow"))
            if row["strategy_id"]:
                fail("COST records are account-day totals, not guessed strategy allocations")
        elif row["gross_cashflow"]:
            fail(f"{kind} has no cash flow")
    if row["currency"] and not re.fullmatch(r"[A-Z]{3}", row["currency"]):
        fail("currency must be three upper-case letters")
    if kind != "COST" and row["cost_component"]:
        fail("Cost components belong only in COST events")
    if kind != "OPENING_BALANCE" and (row["basis_status"] or row["basis_evidence_ref"]):
        fail("Opening basis metadata belongs only in OPENING_BALANCE events")
    if kind != "ASSIGNMENT" and row["reference_event_id"]:
        fail("reference_event_id belongs only in ASSIGNMENT events")
    if kind == "ASSIGNMENT":
        require(row, "reference_event_id", "strategy_id")
        if row["source_kind"] != "USER_RECORD":
            fail("ASSIGNMENT must be explicitly user-recorded linkage, not broker-inferred")
    if kind == "VOID":
        require(row, "supersedes_event_id")
    if row["strategy_id"]:
        require(row, "cycle_id", "strategy_version", "leg_id", "lifecycle_role", "linkage_provenance")
        if row["linkage_provenance"] not in {"USER_CONFIRMED", "RECORDED_STRATEGY_ORDER"}:
            fail("Strategy linkage must be confirmed or explicitly recorded, never inferred")
        if row["lifecycle_role"] not in LIFECYCLES:
            fail("Unsupported lifecycle_role")
    elif any(row[f] for f in ("cycle_id", "strategy_version", "leg_id", "lifecycle_role", "linkage_provenance")):
        fail("Do not partially assign a strategy: supply all linkage fields or leave them blank")
    row["recorded_at"] = row["recorded_at"] or dt.datetime.now(dt.timezone.utc).isoformat()
    timestamp(row["recorded_at"], "recorded_at")
    expected_id = event_id(row)
    if row["event_id"] and row["event_id"] != expected_id:
        fail("event_id does not match deterministic source identity/revision")
    row["event_id"] = expected_id
    return row


def active_rows(rows):
    retired = {row["supersedes_event_id"] for row in rows if row["supersedes_event_id"]}
    return [row for row in rows if row["event_id"] not in retired and row["event_type"] != "VOID"]


def validate_rows(rows):
    known, latest = {}, {}
    for raw in rows:
        row = normalize(raw)
        if row != raw:
            fail(f"Stored row is not normalized: {row['event_id']}")
        eid, key = row["event_id"], identity(row)
        if eid in known:
            fail(f"Duplicate event_id {eid}")
        prior = row["supersedes_event_id"]
        if prior:
            if prior not in known:
                fail("Correction/void must reference an earlier event in this ledger")
            original = known[prior]
            if original["broker"] != row["broker"] or original["account_alias"] != row["account_alias"]:
                fail("Correction/void cannot cross broker/account")
            if any(r["supersedes_event_id"] == prior for r in known.values()):
                fail("Cannot supersede an already-superseded event")
            if row["event_type"] != "VOID":
                if identity(original) != key:
                    fail("Correction must preserve economic identity")
                if int(row["source_revision"]) <= int(original["source_revision"]):
                    fail("Correction revision must increase")
        if key in latest and row["event_type"] != "VOID" and prior != latest[key]:
            fail("Economic identity already exists; use explicit correction with increased revision")
        if row["event_type"] == "ASSIGNMENT":
            target = known.get(row["reference_event_id"])
            if not target or target["event_type"] not in {"FILL", "OPENING_BALANCE", "SETTLEMENT"}:
                fail("ASSIGNMENT must reference an earlier recorded fill/baseline/settlement")
            if target["broker"] != row["broker"] or target["account_alias"] != row["account_alias"]:
                fail("ASSIGNMENT cannot cross account")
        known[eid], latest[key] = row, eid
    active = active_rows(rows)
    opening = set()
    assignments = set()
    costs = {}
    for row in active:
        kind = row["event_type"]
        if kind == "OPENING_BALANCE":
            if instrument_key(row) in opening:
                fail("Only one active opening baseline per instrument; correct rather than add")
            opening.add(instrument_key(row))
        elif kind == "COST":
            scope = tuple(row[f] for f in ("broker", "account_alias", "trading_date", "currency"))
            costs.setdefault(scope, set()).add(row["cost_component"])
        elif kind == "ASSIGNMENT":
            ref = row["reference_event_id"]
            if ref in assignments:
                fail("Multiple active assignments to one event; correct existing assignment")
            assignments.add(ref)
    for components in costs.values():
        if "TOTAL" in components and len(components) > 1:
            fail("Aggregate and itemized costs would double-count the same account/trading-day/currency")
    return active


def read_ledger(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            fail(f"Existing CSV schema mismatch: {path}; never overwrite/migrate implicitly")
        rows = list(reader)
    validate_rows(rows)
    return rows


@contextlib.contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def atomic_write(path, rows):
    fd, temp_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def comparable(row):
    # Same fill in a later export remains the same event, not another execution.
    excluded = {"recorded_at", "source_ref", "source_sha256", "source_record_id", "notes"}
    return {k: v for k, v in row.items() if k not in excluded}


def import_rows(path, raw_rows):
    incoming = [normalize(row) for row in raw_rows]
    with locked(path):
        rows = read_ledger(path)
        by_id = {row["event_id"]: row for row in rows}
        added, duplicates = [], 0
        for row in incoming:
            if row["event_id"] in by_id:
                if comparable(row) != comparable(by_id[row["event_id"]]):
                    fail(f"Conflicting duplicate {row['event_id']}: preserve evidence and add explicit correction")
                duplicates += 1
                continue
            rows.append(row)
            by_id[row["event_id"]] = row
            added.append(row["event_id"])
        validate_rows(rows)
        if added or not path.exists():
            atomic_write(path, rows)
        return {"added": len(added), "duplicates": duplicates, "total_rows": len(rows), "event_ids": added}


def summary(rows):
    active = validate_rows(rows)
    assignments = {r["reference_event_id"]: r for r in active if r["event_type"] == "ASSIGNMENT"}
    cashflows, positions, unassigned = {}, {}, []
    for row in active:
        kind = row["event_type"]
        if kind in {"FILL", "SETTLEMENT", "COST"}:
            currency = row["currency"]
            cashflows.setdefault(currency, {"gross_execution_and_settlement": Decimal(0), "recorded_cost_cashflow": Decimal(0)})
            category = "recorded_cost_cashflow" if kind == "COST" else "gross_execution_and_settlement"
            cashflows[currency][category] += Decimal(row["gross_cashflow"])
        if kind in INSTRUMENT_TYPES:
            positions.setdefault(instrument_key(row), []).append(row)
        if kind in {"FILL", "OPENING_BALANCE", "SETTLEMENT"} and not row["strategy_id"] and row["event_id"] not in assignments:
            unassigned.append(row["event_id"])
    states = []
    for key, events in sorted(positions.items()):
        opening = next((r for r in events if r["event_type"] == "OPENING_BALANCE"), None)
        executions = [r for r in events if r["event_type"] in {"FILL", "SETTLEMENT"}]
        state = dict(zip(INSTRUMENT_KEY_FIELDS, key))
        state.update({"recorded_execution_delta_units": number_text(sum((Decimal(r["quantity_units"]) for r in executions), Decimal(0))), "opening_event_id": opening["event_id"] if opening else None, "basis_status": opening["basis_status"] if opening else "UNKNOWN", "derived_units_since_baseline": None, "snapshot_quantity_match": None})
        observations = [r for r in events if r["event_type"] in {"OPENING_BALANCE", "POSITION_SNAPSHOT"}]
        if observations:
            latest_observation = max(observations, key=lambda r: timestamp(r["event_time"], "event_time"))
            state["latest_observed_quantity_units"] = latest_observation["quantity_units"]
            state["latest_observation_time"] = latest_observation["event_time"]
            state["latest_observation_event_id"] = latest_observation["event_id"]
        if opening:
            after = [r for r in executions if timestamp(r["event_time"], "event_time") > timestamp(opening["event_time"], "event_time")]
            units = Decimal(opening["quantity_units"]) + sum((Decimal(r["quantity_units"]) for r in after), Decimal(0))
            state["derived_units_since_baseline"] = number_text(units)
            state["executions_at_or_before_baseline_not_readded"] = len(executions) - len(after)
            snapshots = [r for r in events if r["event_type"] == "POSITION_SNAPSHOT" and timestamp(r["event_time"], "event_time") >= timestamp(opening["event_time"], "event_time")]
            if snapshots:
                latest = max(snapshots, key=lambda r: timestamp(r["event_time"], "event_time"))
                snapshot_time = timestamp(latest["event_time"], "event_time")
                units_at_snapshot = Decimal(opening["quantity_units"]) + sum((Decimal(r["quantity_units"]) for r in after if timestamp(r["event_time"], "event_time") <= snapshot_time), Decimal(0))
                state["snapshot_event_id"] = latest["event_id"]
                state["snapshot_quantity_match"] = units_at_snapshot == Decimal(latest["quantity_units"])
        states.append(state)
    active_ids = {r["event_id"] for r in active}
    orphaned = [r["event_id"] for r in active if r["event_type"] == "ASSIGNMENT" and r["reference_event_id"] not in active_ids]
    return {"rows": len(rows), "active_rows": len(active), "unassigned_event_ids": unassigned, "orphaned_assignment_event_ids": orphaned, "positions": states, "recorded_cashflows_by_currency": {ccy: {k: number_text(v) for k, v in amounts.items()} for ccy, amounts in cashflows.items()}, "realized_pnl": None, "realized_pnl_status": "NOT_CALCULATED: no reconciled fill-matching, basis, settlement and cost engine is supplied", "inventory_status": "Derived only from imported evidence; completeness is not inferred from a matching snapshot", "cost_status": "Recorded costs only; missing costs are unknown, not zero"}


def load_input(path):
    data = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".csv":
        return list(csv.DictReader(io.StringIO(data)))
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in data.splitlines() if line.strip()]
    value = json.loads(data)
    return value if isinstance(value, list) else [value]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create header only if absent; validate existing file without replacing it")
    for name in ("import", "append"):
        item = sub.add_parser(name, help="Import normalized CSV / JSON / JSONL evidence events; append requires one event")
        item.add_argument("input", type=Path)
    sub.add_parser("validate")
    sub.add_parser("summary")
    sub.add_parser("schema")
    args = parser.parse_args(argv)
    try:
        if args.command == "schema":
            result = {"schema_version": 1, "fields": FIELDS, "event_types": sorted(TYPES), "default_ledger": str(DEFAULT_LEDGER)}
        elif args.command == "init":
            result = import_rows(args.ledger, [])
        elif args.command in {"import", "append"}:
            incoming = load_input(args.input)
            if args.command == "append" and len(incoming) != 1:
                fail("append requires exactly one event; use import for a batch")
            result = import_rows(args.ledger, incoming)
        else:
            with locked(args.ledger):
                if not args.ledger.exists():
                    fail("Ledger is absent; run init")
                rows = read_ledger(args.ledger)
                result = summary(rows) if args.command == "summary" else {"valid": True, "rows": len(rows), "active_rows": len(active_rows(rows)), "sha256": hashlib.sha256(args.ledger.read_bytes()).hexdigest()}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (LedgerError, OSError, json.JSONDecodeError, csv.Error) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
