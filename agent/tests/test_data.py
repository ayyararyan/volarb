import zipfile

import pandas as pd
import pytest

from butterfly_lab.data import load_dataset, qualify_dataset
from butterfly_lab.fixtures import generate_option_fixture, generate_spot_fixture


def test_spot_csv_zip_parquet_consistency(tmp_path):
    manifest = generate_spot_fixture(tmp_path / "spot.csv")
    csv = load_dataset(manifest)
    raw = pd.read_csv(tmp_path / "spot.csv")
    raw.to_parquet(tmp_path / "spot.parquet", index=False)
    other = {**manifest, "source_path": str(tmp_path / "spot.parquet"), "source_sha256": None}
    pd.testing.assert_frame_equal(csv, load_dataset(other))
    with zipfile.ZipFile(tmp_path / "spot.zip", "w") as z:
        z.write(tmp_path / "spot.csv", "archive/yearly/2023.csv")
        z.write(tmp_path / "spot.csv", "archive/monthly/source.csv")
    other["source_path"] = str(tmp_path / "spot.zip")
    assert len(load_dataset(other)) == len(csv)  # never double counts monthly+yearly
    assert qualify_dataset(manifest)["status"] == "PASS"


@pytest.mark.parametrize("label,expected", [("start", "10:01"), ("end", "10:00")])
def test_bar_labels_and_conservative_availability(label, expected):
    dataset = {
        "kind": "spot_bars",
        "bar_label": label,
        "availability_lag_seconds": 60,
        "provenance": "SYNTHETIC",
        "fidelity": "F0",
        "metadata": {"rows": [{"datetime": "2025-01-02T10:00:00+05:30", "close": 100}]},
    }
    frame = load_dataset(dataset)
    assert frame.bar_end.iloc[0].tz_convert("Asia/Kolkata").strftime("%H:%M") == expected
    assert (frame.available_at.iloc[0] - frame.bar_end.iloc[0]).total_seconds() == 60


def test_timezone_naive_and_future_exchange_clock_rejected(tmp_path):
    dataset = generate_option_fixture(tmp_path / "q.parquet", 1)
    data = pd.read_parquet(tmp_path / "q.parquet")
    data["event_at"] = "2025-01-02T15:30:00+05:30"
    data.to_parquet(tmp_path / "bad.parquet")
    dataset.update(source_path=str(tmp_path / "bad.parquet"), source_sha256=None)
    assert "clock" in qualify_dataset(dataset)["errors"][0]
    data["event_at"] = "2025-01-02 10:00:00"
    data.to_parquet(tmp_path / "bad.parquet")
    assert "timezone" in qualify_dataset(dataset)["errors"][0]


def test_identity_duplicate_conflicts_and_lanes(tmp_path):
    dataset = generate_option_fixture(tmp_path / "q.parquet", 1)
    raw = pd.read_parquet(tmp_path / "q.parquet")
    dataset.update(source_sha256=None, source_path=str(tmp_path / "altered.parquet"))
    pd.concat([raw, raw.iloc[:1]]).to_parquet(tmp_path / "altered.parquet")
    assert qualify_dataset(dataset)["identical_duplicates_removed"] == 1
    bad = raw.iloc[:1].copy()
    bad["bid"] += 0.1
    pd.concat([raw, bad]).to_parquet(tmp_path / "altered.parquet")
    assert "conflicting" in qualify_dataset(dataset)["errors"][0]
    raw["contract_id"] = "WEEK1_ATM"
    raw.to_parquet(tmp_path / "altered.parquet")
    assert "rolling" in qualify_dataset(dataset)["errors"][0]


def test_contract_roll_and_missing_identity_rejected(tmp_path):
    dataset = generate_option_fixture(tmp_path / "q.parquet", 1)
    raw = pd.read_parquet(tmp_path / "q.parquet")
    dataset["source_sha256"] = None
    raw.loc[12, "strike"] += 50
    raw.to_parquet(tmp_path / "q.parquet")
    assert "roll" in qualify_dataset(dataset)["errors"][0]
    raw.drop(columns="contract_id").to_parquet(tmp_path / "q.parquet")
    assert "identity" in qualify_dataset(dataset)["errors"][0]


def test_hash_and_fidelity_ceiling(tmp_path):
    dataset = generate_spot_fixture(tmp_path / "spot.csv")
    dataset["source_sha256"] = "0" * 64
    assert qualify_dataset(dataset)["status"] == "DATA_LIMITED"
    dataset["source_sha256"] = None
    dataset.update(fidelity="F3", provenance="HISTORICAL")
    assert qualify_dataset(dataset)["status"] == "DATA_LIMITED"
    dataset["fidelity"] = "F2"
    assert qualify_dataset(dataset)["status"] == "PASS"
    assert "two_sided_quotes" not in qualify_dataset(dataset)["capabilities"]
    dataset["fidelity"] = "F4"
    assert qualify_dataset(dataset)["status"] == "UNSUPPORTED"


def test_session_closed_records_preserved():
    dataset = {
        "kind": "spot_bars",
        "bar_label": "start",
        "provenance": "SYNTHETIC",
        "fidelity": "F0",
        "metadata": {
            "rows": [{"datetime": "2025-01-02T10:00:00+05:30", "close": 100}],
            "sessions": {"2025-01-02": {"closed": True}},
        },
    }
    assert load_dataset(dataset).session_class.tolist() == ["closed"]


def test_f3_requires_receipt_and_non_crossed_books(tmp_path):
    dataset = generate_option_fixture(tmp_path / "q.parquet", 1)
    dataset.update(fidelity="F3", provenance="REPLAY")  # adapter contract test only
    assert qualify_dataset(dataset)["status"] == "PASS"
    raw = pd.read_parquet(tmp_path / "q.parquet")
    raw.loc[0, "ask"] = 0.0
    raw.to_parquet(tmp_path / "bad.parquet")
    dataset.update(source_path=str(tmp_path / "bad.parquet"), source_sha256=None)
    assert "book" in qualify_dataset(dataset)["errors"][0]
