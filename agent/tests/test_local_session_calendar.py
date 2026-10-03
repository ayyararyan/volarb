"""Offline calendar preparation must not erase entirely uncaptured sessions."""

import hashlib
import importlib
import json
from pathlib import Path

import pandas as pd
import pytest

from butterfly_lab.data import sha256_file
from butterfly_lab.schemas import DatasetManifest


@pytest.fixture
def examples(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "examples"))
    return tuple(
        importlib.import_module(name)
        for name in (
            "local_session_calendar",
            "prepare_local_spot",
            "prepare_local_options_batch",
        )
    )


def calendar_file(root, value):
    path = root / "calendar.json"
    path.write_text(json.dumps(value))
    return path


def captured_spot(root):
    directory = root / "january_2026" / "2026_01_02"
    directory.mkdir(parents=True)
    path = directory / "NIFTY50_2026_01_02.parquet"
    stamp = pd.Timestamp("2026-01-02T10:00:00+05:30")
    pd.DataFrame(
        [
            {
                "ft": str(int(stamp.timestamp())),
                "timestamp": "2026-01-02T10:00:00.250000",
                "lp": "26000",
                "tk": "26000",
                "e": "NSE",
                "ts": "Nifty 50",
            }
        ]
    ).to_parquet(path, index=False)
    return path


@pytest.mark.parametrize(
    "value",
    [
        [],
        {},
        {"expected_sessions": "2026-01-02"},
        ["2026-01-02", "2026-01-02"],
        ["2026-02-10", "2026-02-01"],
        ["2026-2-01"],
        ["2026-02-29"],
        ["2025-12-31"],
        ["2026-03-01"],
        [True],
        {"expected_sessions": ["2026-01-02"], "references": "not a list"},
        {"expected_sessions": ["2026-01-02"], "references": [{"url": "https://example.org"}]},
        {
            "expected_sessions": ["2026-01-02"],
            "references": [{"url": "https://example.org", "sha256": "invalid"}],
        },
        {
            "expected_sessions": ["2026-01-02"],
            "references": [{"url": "file:///private/calendar.pdf", "sha256": "a" * 64}],
        },
    ],
)
def test_invalid_calendar_fails_before_any_output(examples, tmp_path, value):
    _, spot, _ = examples
    path = calendar_file(tmp_path, value)
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        spot.prepare(tmp_path / "raw", output, tmp_path / "runtime", "test", path)
    assert not output.exists()


def test_explicit_calendar_preserves_budget_sunday_and_entire_missing_month(examples, tmp_path):
    helper, spot, _ = examples
    raw = tmp_path / "raw"
    source = captured_spot(raw)
    original_hash = sha256_file(source)
    dates = ["2026-01-02", "2026-02-01", "2026-02-10"]
    references = [{"url": "https://example.org/public-calendar", "sha256": "a" * 64}]
    calendar = calendar_file(tmp_path, {"expected_sessions": dates, "references": references})
    output = tmp_path / "output"
    spot.prepare(raw, output, tmp_path / "runtime", "test-calendar", calendar)
    manifest = json.loads((output / "dataset.json").read_text())
    ledger = json.loads((output / "expected-session-ledger.json").read_text())
    assert manifest["session_dates"] == dates
    assert [record["session"] for record in ledger] == dates
    assert [record["status"] for record in ledger] == [
        "QUALIFIED_SOURCE",
        "MISSING_DATA",
        "MISSING_DATA",
    ]
    assert all(record["reason"] == "source_directory_absent" for record in ledger[1:])
    coverage = manifest["metadata"]["session_calendar"]
    assert coverage["calendar_sha256"] == hashlib.sha256(calendar.read_bytes()).hexdigest()
    assert coverage["references"] == references
    assert str(tmp_path) not in json.dumps(coverage)
    assert sha256_file(source) == original_hash
    assert helper.read_calendar(calendar)[0] == dates


def test_without_calendar_is_explicitly_captured_only(examples, tmp_path):
    helper, spot, batch = examples
    raw = tmp_path / "raw"
    captured_spot(raw)
    (raw / "february_2026").mkdir()
    output = tmp_path / "output"
    spot.prepare(raw, output, tmp_path / "runtime", "test-captured")
    manifest = json.loads((output / "dataset.json").read_text())
    assert manifest["session_dates"] == ["2026-01-02"]
    assert helper.CAPTURED_ONLY in manifest["metadata"]["limitations"]
    assert manifest["metadata"]["session_calendar"]["coverage_basis"] == helper.CAPTURED_ONLY
    assert [session for session, _ in batch.discover_sessions(raw)] == ["2026-01-02"]


def test_calendar_cannot_silently_exclude_captured_session(examples, tmp_path):
    helper, _, _ = examples
    raw = tmp_path / "raw"
    captured_spot(raw)
    calendar = calendar_file(tmp_path, ["2026-02-01"])
    with pytest.raises(ValueError, match="refusing silent exclusion"):
        helper.archive_sessions(raw, calendar)


def test_option_aggregate_keeps_missing_directories_in_manifest_and_ledger(
    examples, tmp_path, monkeypatch
):
    helper, _, batch = examples
    raw = tmp_path / "raw"
    captured_spot(raw)
    dates = ["2026-01-02", "2026-02-01", "2026-02-10"]
    calendar = calendar_file(tmp_path, dates)
    sessions, coverage = helper.archive_sessions(raw, calendar, require_months=True)
    assert [session for session, _ in batch.discover_sessions(raw, calendar)] == dates
    root = tmp_path / "output"
    subset = root / "subset"
    subset.mkdir(parents=True)
    quote_file = subset / "option-quotes.parquet"
    pd.DataFrame([{"event_at": "2026-01-02T04:30:00Z", "contract_id": "fixture"}]).to_parquet(
        quote_file, index=False
    )
    manifest = DatasetManifest(
        id="calendar-fixture",
        kind="option_quotes",
        source_path=str(quote_file),
        source_sha256=sha256_file(quote_file),
        fidelity="F0",
        provenance="SYNTHETIC",
        session_dates=[dates[0]],
        metadata={"construction": {}, "source_hashes": ["a" * 64], "limitations": []},
    )
    (subset / "dataset.json").write_text(manifest.model_dump_json())
    (subset / "transformation-manifest.json").write_text(json.dumps({"inputs": []}))
    pd.DataFrame([{"status": "fixture"}]).to_parquet(subset / "grid-decisions.parquet")
    records = [
        {
            "session": dates[0],
            "width": 200,
            "subset_path": str(subset),
            "status": "QUALIFIED_SUBSET",
        }
    ]
    for session, path in sessions[1:]:
        record = batch.build_one((session, str(path), str(root / session), 200, [15]))
        assert record["status"] == "MISSING_DATA"
        assert record["reason"] == "source_directory_absent"
        assert not (root / session).exists()
        records.append(record)
    # Test aggregation's session contract, not numerical/quote quality on this tiny fixture.
    monkeypatch.setattr(batch, "qualify_dataset", lambda _: {"status": "PASS", "capabilities": []})
    result = batch.aggregate(root, 200, records, dates, [15], coverage)
    assert result["expected_sessions"] == 3 and result["qualified_subset_sessions"] == 1
    aggregate = json.loads((root / "width-200" / "dataset.json").read_text())
    ledger = json.loads((root / "width-200" / "expected-session-ledger.json").read_text())
    assert aggregate["session_dates"] == dates
    assert [row["session"] for row in ledger] == dates
    assert [row["session"] for row in aggregate["metadata"]["missing_sessions"]] == dates[1:]
    assert aggregate["metadata"]["session_calendar"]["calendar_sha256"] == sha256_file(calendar)
    assert "never a zero-return" in aggregate["metadata"]["missing_session_semantics"]
    assert sha256_file(quote_file) == manifest.source_sha256


def test_calendar_digest_binds_exact_input_bytes(examples, tmp_path):
    helper, _, _ = examples
    calendar = calendar_file(tmp_path, ["2026-02-01"])
    _, first = helper.read_calendar(calendar)
    calendar.write_text(calendar.read_text() + "\n")
    dates, second = helper.read_calendar(calendar)
    assert dates == ["2026-02-01"]
    assert first["calendar_sha256"] != second["calendar_sha256"]
