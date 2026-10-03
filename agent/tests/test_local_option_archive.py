from __future__ import annotations

import pandas as pd
import pytest

from butterfly_lab.data import DataQualificationError, sha256_file
from butterfly_lab.local_option_archive import (
    parse_weekly_symbol,
    read_option_snapshots,
    reconstruct_option_snapshots,
)

SYMBOL = "NIFTY2610626000CE"


def row(second: int, **values):
    stamp = pd.Timestamp("2026-01-02 10:00:00", tz="Asia/Kolkata") + pd.Timedelta(seconds=second)
    return {
        "timestamp": stamp.tz_localize(None).isoformat(),
        "ft": str(int(stamp.timestamp())),
        "t": "df",
        "ts": None,
        "tk": "123",
        "ls": None,
        "ml": "1",
        "bp1": None,
        "sp1": None,
        "bq1": None,
        "sq1": None,
        **values,
    }


def raw_rows():
    return [
        row(0, t="dk", ts=SYMBOL, ls="65", bp1="100", sp1="101", bq1="130", sq1="65"),
        row(1, bp1="100.5", bq1="195"),
        row(4, sp1="102", sq1="130"),
    ]


def grid(*seconds):
    return [
        pd.Timestamp("2026-01-02 10:00:00", tz="Asia/Kolkata") + pd.Timedelta(seconds=s)
        for s in seconds
    ]


def adapt(rows=None, seconds=(1,), **kwargs):
    return reconstruct_option_snapshots(
        pd.DataFrame(raw_rows() if rows is None else rows),
        grid(*seconds),
        source_id="fixture-sha256",
        receipt_timezone="Asia/Kolkata",
        sparse_delta_verified=True,
        **kwargs,
    )


def test_weekly_identity_not_monthly_calendar_guess():
    assert parse_weekly_symbol(SYMBOL)["expiry"] == "2026-01-06"
    assert parse_weekly_symbol("SENSEX26O0180000PE")["expiry"] == "2026-10-01"
    for symbol in ["NIFTY26JAN26000CE", "ATM_CALL", "NIFTY2623026000CE"]:
        with pytest.raises(DataQualificationError):
            parse_weekly_symbol(symbol)


def test_reversed_sparse_archive_is_past_only_and_original_unchanged():
    rows = raw_rows()[::-1]
    frame = pd.DataFrame(rows)
    copy = frame.copy(deep=True)
    result = reconstruct_option_snapshots(
        frame,
        grid(1),
        source_id="fixture",
        receipt_timezone="Asia/Kolkata",
        sparse_delta_verified=True,
    )
    pd.testing.assert_frame_equal(frame, copy)
    r = result.snapshots.iloc[0]
    assert r.bid == 100.5 and r.ask == 101  # Never future 102.
    assert r.lot_size == 65  # ml=1 is not the historical lot size.
    assert r.ask_age_seconds == 1
    assert r.receive_at == grid(1)[0].tz_convert("UTC")
    assert r.event_at != grid(4)[0].tz_convert("UTC")


def test_no_future_backfill_of_identity_or_lot():
    rows = [row(0, bp1="100", sp1="101", bq1="130", sq1="130"), row(2, ts=SYMBOL, ls="65")]
    r = adapt(rows, seconds=(1, 2))
    assert list(r.decisions.status) == ["UNINITIALIZED", "ACCEPTED"]
    assert r.snapshots.iloc[0].available_at == grid(2)[0].tz_convert("UTC")


def test_each_session_and_reconnect_clear_prior_state():
    rows = raw_rows() + [row(5, t="dk", ts=SYMBOL, ls="65"), row(6, bp1="99")]
    assert adapt(rows, seconds=(6,)).decisions.status.iloc[0] == "UNINITIALIZED"
    rows = raw_rows()
    tomorrow = row(1, bp1="99")
    tomorrow["timestamp"] = "2026-01-03T10:00:01"
    tomorrow["ft"] = str(int(pd.Timestamp(tomorrow["timestamp"], tz="Asia/Kolkata").timestamp()))
    rows.append(tomorrow)
    r = reconstruct_option_snapshots(
        pd.DataFrame(rows),
        [pd.Timestamp("2026-01-03 10:00:02", tz="Asia/Kolkata")],
        source_id="x",
        receipt_timezone="Asia/Kolkata",
        sparse_delta_verified=True,
    )
    assert r.decisions.status.iloc[0] == "UNINITIALIZED"


def test_observed_zero_not_missing_and_crossed_book_recorded():
    rows = raw_rows() + [row(5, bp1="0"), row(6, bp1="103")]
    r = adapt(rows, seconds=(5, 6))
    assert list(r.decisions.status) == ["NONPOSITIVE_PRICE", "CROSSED_BOOK"]


def test_component_freshness_not_refreshed_by_unrelated_message():
    rows = raw_rows() + [row(7)]
    r = adapt(rows, seconds=(7,))
    assert r.decisions.status.iloc[0] == "STALE_COMPONENT"
    r = adapt(rows, seconds=(20,))
    assert r.decisions.status.iloc[0] == "STALE_MESSAGE"


def test_grid_not_fabricated_as_source_event_and_repeated_state_deduplicated():
    r = adapt(seconds=(1, 2, 3))
    assert list(r.decisions.status) == ["ACCEPTED", "REUSED_SOURCE_STATE", "REUSED_SOURCE_STATE"]
    r = adapt(seconds=(2,))
    assert r.snapshots.iloc[0].event_at == grid(1)[0].tz_convert("UTC")
    assert r.snapshots.iloc[0].decision_at == grid(2)[0].tz_convert("UTC")


@pytest.mark.parametrize("field,value", [("ts", "NIFTY2610626050CE"), ("tk", "999"), ("ls", "75")])
def test_global_inconsistent_identity_cannot_hide_after_decision(field, value):
    rows = raw_rows() + [row(10, **{field: value})]
    with pytest.raises(DataQualificationError, match="identity"):
        adapt(rows)


def test_ambiguous_ties_require_source_sequence_evidence():
    with pytest.raises(DataQualificationError, match="tied"):
        adapt(raw_rows() + [row(1, sp1="120")])


def test_feed_clock_cannot_precede_availability():
    rows = raw_rows()
    rows[1]["ft"] = str(int(grid(2)[0].timestamp()))
    with pytest.raises(DataQualificationError, match="later than receipt"):
        adapt(rows)
    r = adapt(rows, clock_tolerance_seconds=1)
    assert r.decisions.status.iloc[0] == "NOT_YET_AVAILABLE"


def test_unknown_metadata_not_defaulted_and_invalid_numeric_rejected():
    rows = raw_rows()
    rows[0]["ls"] = None
    with pytest.raises(DataQualificationError, match="identity"):
        adapt(rows)
    rows = raw_rows()
    rows[1]["bp1"] = "inf"
    with pytest.raises(DataQualificationError, match="nonfinite"):
        adapt(rows)


def test_quote_without_clock_and_insufficient_size_fail_closed():
    rows = raw_rows()
    rows[1]["ft"] = None
    with pytest.raises(DataQualificationError, match="no source event"):
        adapt(rows)
    rows = raw_rows() + [row(5, bq1="64")]
    assert adapt(rows, seconds=(5,)).decisions.status.iloc[0] == "INSUFFICIENT_ONE_LOT_SIZE"


def test_source_read_is_fingerprinted_and_missing_file_not_omitted(tmp_path):
    path = tmp_path / "original.parquet"
    pd.DataFrame(raw_rows()).to_parquet(path)
    digest = sha256_file(path)
    r = read_option_snapshots(
        path,
        grid(1),
        expected_sha256=digest,
        receipt_timezone="Asia/Kolkata",
        sparse_delta_verified=True,
    )
    assert len(r.snapshots) == 1
    assert sha256_file(path) == digest
    with pytest.raises(DataQualificationError, match="fingerprint"):
        read_option_snapshots(
            path,
            grid(1),
            expected_sha256="incorrect",
            receipt_timezone="Asia/Kolkata",
            sparse_delta_verified=True,
        )
    with pytest.raises(FileNotFoundError):
        read_option_snapshots(
            tmp_path / "missing.parquet",
            grid(1),
            expected_sha256=digest,
            receipt_timezone="Asia/Kolkata",
            sparse_delta_verified=True,
        )


def test_grid_selected_state_is_not_available_retroactively():
    r = adapt(seconds=(2,)).snapshots.iloc[0]
    assert r.receive_at == grid(1)[0].tz_convert("UTC")
    assert r.event_at == grid(1)[0].tz_convert("UTC")
    assert r.available_at == grid(2)[0].tz_convert("UTC")
