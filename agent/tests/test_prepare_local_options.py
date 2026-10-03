"""Contract selection/privacy tests for the offline historical subset builder."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from butterfly_lab.data import DataQualificationError
from butterfly_lab.accounting import fee_for_fill

script = Path(__file__).parents[1] / "examples" / "prepare_local_options.py"
spec = importlib.util.spec_from_file_location("prepare_local_options", script)
assert spec is not None and spec.loader is not None
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_historical_charges_include_ipft_once_and_tax_its_aggregate():
    schedule = builder.historical_fee_schedule()
    # On one lakh premium: brokerage20 + NSE35.03 + IPFT0.50 + SEBI0.10,
    # GST10.0134 plus buy stamp3 =>68.6434, rounded68.64.
    assert fee_for_fill(schedule, "2026-01-02T10:00:00+05:30", 1000, 100) == 68.64
    # Sell STT100 replaces buy stamp3 =>165.6434, rounded165.64.
    assert fee_for_fill(schedule, "2026-02-27T10:00:00+05:30", -1000, 100) == 165.64
    with pytest.raises(ValueError):
        fee_for_fill(schedule, "2026-03-01T10:00:00+05:30", 1000, 100)


def test_catalog_selection_uses_nearest_weekly_and_does_not_fallback_for_missing_wing(tmp_path):
    names = [
        "NIFTY2610626000CE",
        "NIFTY2610626000PE",
        "NIFTY2610626200CE",
        "NIFTY2610625800PE",
        "NIFTY26JAN26000CE",
        "NIFTY2611326000CE",
        "NIFTY2611326000PE",
    ]
    for name in names:
        (tmp_path / (name + "_2026_01_02.parquet")).touch()
    selected, construction = builder.select_contracts(tmp_path, "2026-01-02", 26010, 200)
    assert len(selected) == 4 and construction["expiry"] == "2026-01-06"
    assert construction["body"] == 26000
    with pytest.raises(DataQualificationError, match="wings missing"):
        builder.select_contracts(tmp_path, "2026-01-02", 26010, 250)


def test_spot_selection_has_no_future_price_or_metadata_backfill(tmp_path):
    entry = pd.Timestamp("2026-01-02T10:00:00+05:30")
    frame = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-02T09:59:59",
                "ft": str(int(entry.timestamp()) - 1),
                "ts": "Nifty 50",
                "tk": "26000",
                "e": "NSE",
                "lp": "26010",
            },
            {
                "timestamp": "2026-01-02T10:00:01",
                "ft": str(int(entry.timestamp()) + 1),
                "ts": None,
                "tk": "26000",
                "e": "NSE",
                "lp": "27000",
            },
        ]
    )
    path = tmp_path / "spot.parquet"
    frame.to_parquet(path)
    value, provenance = builder.selection_spot(path, entry)
    assert value == 26010 and provenance["source_row"] == 0
    frame.loc[0, "ts"] = None
    frame.loc[1, "ts"] = "Nifty 50"
    frame.to_parquet(path)
    with pytest.raises(DataQualificationError, match="identity not yet"):
        builder.selection_spot(path, entry)


def test_builder_cannot_overwrite_existing_runtime_or_use_unregistered_dates(tmp_path):
    output = tmp_path / "prior-run"
    output.mkdir()
    sentinel = output / "preserve.txt"
    sentinel.write_text("unchanged")
    with pytest.raises(FileExistsError):
        builder.prepare(tmp_path, "2026-01-02", output, "test", 200)
    assert sentinel.read_text() == "unchanged"
    with pytest.raises(ValueError, match="January"):
        builder.prepare(tmp_path, "2025-01-02", tmp_path / "new", "test", 200)


@pytest.mark.parametrize("field,bad", [("tk", "26009"), ("e", "BSE")])
def test_spot_wrong_token_or_exchange_cannot_masquerade_as_nifty(tmp_path, field, bad):
    entry = pd.Timestamp("2026-01-02T10:00:00+05:30")
    raw = {
        "timestamp": "2026-01-02T09:59:59",
        "ft": str(int(entry.timestamp()) - 1),
        "ts": "Nifty 50",
        "tk": "26000",
        "e": "NSE",
        "lp": "26010",
    }
    raw[field] = bad
    path = tmp_path / "wrong-identity.parquet"
    pd.DataFrame([raw]).to_parquet(path)
    with pytest.raises(DataQualificationError, match="token26000"):
        builder.selection_spot(path, entry)


def test_later_coarse_event_collision_cannot_retroactively_delete_earlier_quote():
    rows = pd.DataFrame(
        [
            {
                "event_at": "2026-01-02T04:30:00Z",
                "contract_id": "fixed",
                "available_at": "2026-01-02T04:30:00.5Z",
                "bid": 100,
            },
            {
                "event_at": "2026-01-02T04:30:00Z",
                "contract_id": "fixed",
                "available_at": "2026-01-02T04:30:01Z",
                "bid": 101,
            },
        ]
    )
    with pytest.raises(DataQualificationError, match="conflicting coarse"):
        builder.canonical_snapshots(rows)
    assert len(builder.canonical_snapshots(pd.concat([rows.iloc[:1], rows.iloc[:1]]))) == 1


def test_iso_source_accepts_explicit_seconds_with_or_without_fraction(tmp_path):
    entry = pd.Timestamp("2026-01-02T10:00:00+05:30")
    rows = [
        {
            "timestamp": "2026-01-02T09:59:58.123456",
            "ft": str(int(entry.timestamp()) - 2),
            "ts": "Nifty 50",
            "tk": "26000",
            "e": "NSE",
            "lp": "26010",
        },
        {
            "timestamp": "2026-01-02T09:59:59",
            "ft": str(int(entry.timestamp()) - 1),
            "ts": None,
            "tk": "26000",
            "e": "NSE",
            "lp": "26011",
        },
    ]
    path = tmp_path / "mixed-iso.parquet"
    pd.DataFrame(rows).to_parquet(path)
    price, _ = builder.selection_spot(path, entry)
    assert price == 26011
