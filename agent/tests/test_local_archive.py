import json

import pandas as pd
import pytest

from butterfly_lab.data import qualify_dataset, sha256_file
from butterfly_lab.local_archive import (
    ArchiveAdapterError,
    read_spot_archive,
    spot_updates_to_minutes,
)


def sparse_source():
    # Intentionally reverse ordered with two updates in the same feed second.
    records = []
    for clock, price, micros in [
        ("10:02:01", "105", 500000),
        ("10:00:02", None, 500000),
        ("10:00:01", "103", 800000),
        ("10:00:01", "99", 100000),
        ("10:00:00", "101", 500000),
    ]:
        event = pd.Timestamp("2026-01-02 " + clock, tz="Asia/Kolkata")
        records.append(
            {
                "ft": str(int(event.timestamp())),
                "timestamp": (
                    event.tz_localize(None) + pd.Timedelta(microseconds=micros)
                ).isoformat(),
                "lp": price,
                "tk": "26000",
                "e": "NSE",
                "ts": None,
            }
        )
    records[-1]["ts"] = "Nifty 50"
    return pd.DataFrame(records)


def options():
    return dict(
        source_sha256="a" * 64,
        instrument="NIFTY50",
        expected_token="26000",
        expected_exchange="NSE",
        expected_symbol="Nifty 50",
        expected_session="2026-01-02",
    )


def test_sparse_bars_preserve_observations_missingness_and_read_only_input():
    raw = sparse_source()
    original = raw.copy(deep=True)
    bars, report = spot_updates_to_minutes(raw, **options())
    pd.testing.assert_frame_equal(raw, original)
    assert len(bars) == 2  # No fabricated 10:01 bucket.
    assert bars.iloc[0][["open", "high", "low", "close"]].tolist() == [101, 103, 99, 103]
    assert json.loads(bars.source_row_ids.iloc[0]) == [4, 3, 2]
    assert report["non_price_source_rows"] == [1]
    assert report["source_feed_descending"] is True
    assert report["identity"]["observed_symbols"] == ["Nifty 50"]
    assert bars.event_at.iloc[0].isoformat() == "2026-01-02T04:30:00+00:00"
    assert bars.available_at.iloc[0] == bars.event_at.iloc[0] + pd.Timedelta(minutes=2)
    assert "2026-01-02T04:31:00+00:00" in report["missing_regular_minutes"]["2026-01-02"]


def test_late_actual_receipt_delays_bar_availability_without_dropping_price():
    raw = sparse_source()
    raw.loc[2, "timestamp"] = "2026-01-02T10:03:00"
    bars, report = spot_updates_to_minutes(raw, **options())
    assert bars.available_at.iloc[0] == pd.Timestamp("2026-01-02T10:03:00+05:30")
    assert report["receipt_minus_feed_seconds"]["over_60_seconds"] == 1
    assert report["price_updates"] == 4


@pytest.mark.parametrize("value", ["broken", "-1", "0", "inf", "NaN"])
def test_invalid_price_is_a_hard_source_error_with_offset(value):
    raw = sparse_source()
    raw.loc[2, "lp"] = value
    with pytest.raises(ArchiveAdapterError, match="invalid genuine") as error:
        spot_updates_to_minutes(raw, **options())
    assert error.value.report["error_source_rows"] == [2]
    assert error.value.report["status"] == "DATA_LIMITED"


def test_future_feed_even_on_control_row_is_not_silently_filtered():
    raw = sparse_source()
    raw.loc[1, "timestamp"] = "2026-01-02T09:59:00"
    with pytest.raises(ArchiveAdapterError, match="after capture") as error:
        spot_updates_to_minutes(raw, **options())
    assert error.value.report["error_source_rows"] == [1]


@pytest.mark.parametrize(
    "column,value",
    [("tk", "123"), ("e", "NFO"), ("ts", "Other index"), ("ft", "1.5"), ("timestamp", "bad clock")],
)
def test_invalid_identity_or_clock_fails_whole_source(column, value):
    raw = sparse_source()
    raw.loc[2, column] = value
    with pytest.raises(ArchiveAdapterError):
        spot_updates_to_minutes(raw, **options())


def test_indistinguishable_clock_price_conflict_fails_but_exact_repeats_are_retained():
    raw = sparse_source()
    raw.loc[2, "timestamp"] = raw.loc[3, "timestamp"]
    with pytest.raises(ArchiveAdapterError, match="ordering is unknown"):
        spot_updates_to_minutes(raw, **options())
    raw.loc[2, "lp"] = raw.loc[3, "lp"]
    bars, report = spot_updates_to_minutes(raw, **options())
    assert report["identical_clock_price_repeats"] == 1
    assert bars.observed_updates.iloc[0] == 3


def test_original_hash_bound_and_derived_output_passes_unchanged_gates(tmp_path):
    source = tmp_path / "source.parquet"
    sparse_source().to_parquet(source, index=False)
    source_hash = sha256_file(source)
    kwargs = options()
    kwargs.pop("source_sha256")
    bars, report = read_spot_archive(source, **kwargs)
    assert sha256_file(source) == source_hash == report["source_sha256"]
    assert bars.source_sha256.unique().tolist() == [source_hash]
    derived = tmp_path / "derived.parquet"
    bars.to_parquet(derived, index=False)
    result = qualify_dataset(
        dict(
            id="test",
            source_path=str(derived),
            source_sha256=sha256_file(derived),
            kind="spot_bars",
            provenance="HISTORICAL",
            fidelity="F2",
            bar_label="start",
            availability_lag_seconds=60,
            metadata={"bar_seconds": 60},
        )
    )
    assert result["status"] == "PASS"
    assert result["rows"] == 2


def test_outside_session_observations_are_retained_not_deleted():
    raw = sparse_source()
    raw.loc[0, "ft"] = str(int(pd.Timestamp("2026-01-02T16:00:00+05:30").timestamp()))
    raw.loc[0, "timestamp"] = "2026-01-02T16:00:00.1"
    bars, report = spot_updates_to_minutes(raw, **options())
    assert report["outside_regular_price_updates"] == 1
    assert bars.close.iloc[-1] == 105
