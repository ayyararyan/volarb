"""Read-only adapter for identified, sparse-delta historical option feeds.

This adapter does not turn rolling ATM lanes into contracts or assign F3. Its
caller must bind feed/clock provenance, fingerprint sources, and qualify outputs.
A null field is an unchanged field under the explicitly declared delta contract;
zero is an observed value, never a missing-value shortcut. Local receipt time is
the availability clock. No original row is modified and no future value is filled.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .data import DataQualificationError, sha256_file

_WEEKLY = re.compile(r"^(NIFTY|BANKNIFTY|SENSEX)(\d{2})([1-9OND])(\d{2})(\d+)(CE|PE)$")
_TOP = {"bp1": "bid", "sp1": "ask", "bq1": "bid_size", "sq1": "ask_size"}
_STATIC = ("ts", "tk", "ls")


@dataclass
class OptionSnapshotResult:
    snapshots: pd.DataFrame
    decisions: pd.DataFrame
    audit: dict[str, Any]


def parse_weekly_symbol(symbol: str) -> dict[str, Any]:
    """Parse only exchange symbols containing an explicit weekly expiry date.

    Monthly names require a verified historical calendar; last-Thursday or
    current-calendar guesses are deliberately unsupported.
    """
    match = _WEEKLY.fullmatch(symbol)
    if match is None:
        raise DataQualificationError("explicit-date weekly option symbol required")
    underlying, yy, month, dd, strike, side = match.groups()
    month_number = {"O": 10, "N": 11, "D": 12}.get(month)
    if month_number is None:
        month_number = int(month)
    try:
        expiry = date(2000 + int(yy), month_number, int(dd))
    except ValueError as exc:
        raise DataQualificationError("invalid option expiry date") from exc
    if int(strike) <= 0:
        raise DataQualificationError("positive option strike required")
    return {
        "underlying": underlying,
        "expiry": expiry.isoformat(),
        "strike": float(strike),
        "option_type": side,
        "contract_id": symbol,
    }


def _present(value: Any) -> bool:
    return value is not None and not pd.isna(value) and str(value) not in {"", "None"}


def _number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DataQualificationError(f"invalid numeric field {field}") from exc
    if not math.isfinite(number):
        raise DataQualificationError(f"nonfinite numeric field {field}")
    return number


def _receipt(value: Any, timezone: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            raise ValueError("missing timestamp")
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize(timezone)
        return stamp.tz_convert("UTC")
    except (TypeError, ValueError) as exc:
        raise DataQualificationError("invalid receipt clock") from exc


def reconstruct_option_snapshots(
    raw: pd.DataFrame,
    decision_times: Iterable[Any],
    *,
    source_id: str,
    receipt_timezone: str,
    sparse_delta_verified: bool,
    max_field_age_seconds: float = 5.0,
    max_message_age_seconds: float = 5.0,
    clock_tolerance_seconds: float = 0.0,
    expected_symbol: str | None = None,
    deduplicate_states: bool = True,
) -> OptionSnapshotResult:
    """Select past-only states at an aware grid, retaining actual source clocks.

    The five-second component bound is a conservative modeling restriction, not
    a claim that an unchanged price is a stale book. Every rejected grid point is
    recorded. ``quote_state_id`` binds component update rows; repeated grids do
    not create new displayed capacity. ``source_event_id`` binds the latest raw
    message. Cross-instrument synchronization and shared-capacity fills remain
    the caller/evaluator's responsibilities.

    Input errors, ambiguous tied receipts and inconsistent identity fail the
    source, rather than silently omitting inconvenient rows or sessions.
    """
    if not sparse_delta_verified or not receipt_timezone or not source_id:
        raise DataQualificationError("explicit sparse-delta, clock and source provenance required")
    limits = (max_field_age_seconds, max_message_age_seconds, clock_tolerance_seconds)
    if any(not math.isfinite(x) or x < 0 for x in limits):
        raise DataQualificationError("finite nonnegative clock/freshness bounds required")
    required = {"timestamp", "ft", "t", *_STATIC, *_TOP}
    if not required.issubset(raw.columns) or raw.empty:
        raise DataQualificationError("sparse option feed required fields missing or empty")
    frame = raw.loc[:, list(required)].copy()
    frame["_receipt"] = [_receipt(v, receipt_timezone) for v in frame.timestamp]
    frame["_row"] = range(len(frame))
    frame = frame.sort_values("_receipt", kind="stable")
    if frame._receipt.duplicated().any():
        raise DataQualificationError("ambiguous tied receipt clocks; sequence evidence required")
    identity: dict[str, str] = {}
    for field in _STATIC:
        unique = {str(v) for v in frame[field] if _present(v)}
        if len(unique) != 1:
            raise DataQualificationError(f"nonunique or missing contract identity: {field}")
        identity[field] = next(iter(unique))
    parsed = parse_weekly_symbol(identity["ts"])
    if expected_symbol is not None and identity["ts"] != expected_symbol:
        raise DataQualificationError("filename/request and observed symbol disagree")
    lot = _number(identity["ls"], "ls")
    if lot <= 0 or not lot.is_integer():
        raise DataQualificationError("positive integer historical ls lot size required")
    for stamp in frame._receipt:
        if stamp.tz_convert(receipt_timezone).date() > date.fromisoformat(parsed["expiry"]):
            raise DataQualificationError("option source continues after its explicit expiry")
    # Preflight every row, including observations after the requested grids.
    records = frame.to_dict("records")
    for row in records:
        row["_event"] = None
        if _present(row["ft"]):
            epoch = _number(row["ft"], "ft")
            if not epoch.is_integer():
                raise DataQualificationError("feed epoch must be integral seconds")
            row["_event"] = pd.Timestamp(epoch, unit="s", tz="UTC")
            if row["_event"] > row["_receipt"] + pd.Timedelta(seconds=clock_tolerance_seconds):
                raise DataQualificationError("feed clock later than receipt clock")
            if (
                row["_event"].tz_convert(receipt_timezone).date()
                != row["_receipt"].tz_convert(receipt_timezone).date()
            ):
                raise DataQualificationError("feed and receipt sessions disagree")
        if str(row["t"]) not in {"dk", "df"}:
            raise DataQualificationError("unsupported message type/reset semantics")
        for field in _TOP:
            if _present(row[field]):
                row[field] = _number(row[field], field)
                if row["_event"] is None:
                    raise DataQualificationError("quote update has no source event clock")
    grids = []
    for value in decision_times:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:
            raise DataQualificationError("timezone-aware decision grid required")
        grids.append(stamp.tz_convert("UTC"))
    if len(grids) != len(set(grids)):
        raise DataQualificationError("duplicate decision times")
    grids.sort()
    state: dict[str, Any] = {}
    updates: dict[str, tuple[pd.Timestamp, pd.Timestamp, int]] = {}
    known: dict[str, Any] = {}
    known_received: dict[str, pd.Timestamp] = {}
    current_session = None
    latest = None
    cursor = 0
    accepted: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    used_states: set[str] = set()
    for grid in grids:
        session = grid.tz_convert(receipt_timezone).date()
        while cursor < len(records) and records[cursor]["_receipt"] <= grid:
            row = records[cursor]
            row_session = row["_receipt"].tz_convert(receipt_timezone).date()
            if row_session != current_session or row["t"] == "dk":
                state, updates, known, known_received = {}, {}, {}, {}
                latest = None
                current_session = row_session
            for field in _STATIC:
                if _present(row[field]):
                    known[field] = row[field]
                    known_received[field] = row["_receipt"]
            for field in _TOP:
                if _present(row[field]):
                    state[field] = row[field]
                    updates[field] = (row["_receipt"], row["_event"], row["_row"])
            if row["_event"] is not None:
                latest = row
            cursor += 1
        reason = None
        if current_session != session or latest is None:
            reason = "NO_PAST_SESSION_EVENT"
        elif not all(k in known for k in _STATIC) or len(state) != len(_TOP):
            reason = "UNINITIALIZED"
        elif latest["_event"] > grid or any(u[1] > grid for u in updates.values()):
            reason = "NOT_YET_AVAILABLE"
        elif state["bp1"] <= 0 or state["sp1"] <= 0:
            reason = "NONPOSITIVE_PRICE"
        elif state["sp1"] < state["bp1"]:
            reason = "CROSSED_BOOK"
        elif state["bq1"] < lot or state["sq1"] < lot:
            reason = "INSUFFICIENT_ONE_LOT_SIZE"
        elif (grid - latest["_receipt"]).total_seconds() > max_message_age_seconds:
            reason = "STALE_MESSAGE"
        elif any((grid - u[0]).total_seconds() > max_field_age_seconds for u in updates.values()):
            reason = "STALE_COMPONENT"
        if reason:
            decisions.append({"decision_at": grid, "status": reason})
            continue
        assert latest is not None
        state_key = source_id + ":" + ":".join(str(updates[k][2]) for k in sorted(_TOP))
        state_id = hashlib.sha256(state_key.encode()).hexdigest()
        if deduplicate_states and state_id in used_states:
            decisions.append({"decision_at": grid, "status": "REUSED_SOURCE_STATE"})
            continue
        used_states.add(state_id)
        snapshot = {
            **parsed,
            "security_id": identity["tk"],
            "lot_size": int(lot),
            "session": session.isoformat(),
            "decision_at": grid,
            "event_at": latest["_event"],
            "receive_at": max(latest["_receipt"], *known_received.values()),
            "available_at": max(
                grid, latest["_event"], latest["_receipt"], *known_received.values()
            ),
            "quote_state_id": state_id,
            "source_event_id": f"{source_id}:{latest['_row']}",
            "source_id": source_id,
        }
        for raw_field, canonical in _TOP.items():
            capture, event, index = updates[raw_field]
            snapshot[canonical] = state[raw_field]
            snapshot[canonical + "_updated_at"] = capture
            snapshot[canonical + "_event_at"] = event
            snapshot[canonical + "_age_seconds"] = (grid - capture).total_seconds()
            snapshot[canonical + "_source_row"] = index
        accepted.append(snapshot)
        decisions.append({"decision_at": grid, "status": "ACCEPTED", "quote_state_id": state_id})
    return OptionSnapshotResult(
        pd.DataFrame(accepted),
        pd.DataFrame(decisions),
        {
            "source_id": source_id,
            "source_rows": len(frame),
            "decision_count": len(grids),
            "accepted_count": len(accepted),
            "receipt_timezone": receipt_timezone,
            "max_field_age_seconds": max_field_age_seconds,
            "max_message_age_seconds": max_message_age_seconds,
            "clock_tolerance_seconds": clock_tolerance_seconds,
            "historical_lot_field": "ls (not ml)",
            "identity": parsed,
            "limitations": [
                "Sparse-delta and receipt-clock provenance is a caller-supplied verified contract.",
                "No queue position, fill guarantee, or higher fidelity is inferred.",
                "Unchanged-component age cutoff is an explicit conservative research assumption.",
                "Caller must prevent capacity reuse across quote states and synchronize legs.",
            ],
        },
    )


def read_option_snapshots(
    path: Path, decision_times: Iterable[Any], *, expected_sha256: str, **kwargs: Any
) -> OptionSnapshotResult:
    """Fingerprint before and after bounded source read; filesystem errors propagate."""
    if sha256_file(path) != expected_sha256:
        raise DataQualificationError("option archive fingerprint mismatch")
    raw = pd.read_parquet(path)
    if sha256_file(path) != expected_sha256:
        raise DataQualificationError("option archive changed during read")
    return reconstruct_option_snapshots(raw, decision_times, source_id=expected_sha256, **kwargs)
