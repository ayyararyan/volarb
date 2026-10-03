"""Create immutable private minute bars from an existing sparse index archive.

No downloads, model calls, source mutations or economic calculations. Existing
output directories are refused. All represented archive sessions are retained
in the expected-session ledger, including missing instrument files.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from butterfly_lab.data import qualify_dataset, sha256_file
from butterfly_lab.local_archive import read_spot_archive
from butterfly_lab.registry import Registry
from butterfly_lab.schemas import DatasetManifest
from local_session_calendar import archive_sessions


def prepare(
    raw_root: Path,
    output: Path,
    runtime: Path,
    dataset_id: str,
    calendar: Path | None = None,
) -> dict:
    days, coverage = archive_sessions(raw_root, calendar)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    frames, reports, sources, missing, ledger = [], [], [], [], []
    sessions = [session for session, _ in days]
    for session, day in days:
        source = day / f"NIFTY50_{day.name}.parquet"
        record = {"session": session, "source_path": str(source.resolve())}
        if not source.exists():
            reason = "source_file_absent" if day.is_dir() else "source_directory_absent"
            missing.append({"session": session, "reason": reason})
            ledger.append({**record, "status": "MISSING_DATA", "reason": reason})
            continue
        bars, report = read_spot_archive(
            source,
            instrument="NIFTY50",
            expected_token="26000",
            expected_exchange="NSE",
            expected_symbol="Nifty 50",
            expected_session=session,
        )
        frames.append(bars)
        reports.append(report)
        sources.append({"source_path": str(source.resolve()), "sha256": report["source_sha256"]})
        ledger.append({**record, "status": "QUALIFIED_SOURCE", "sha256": report["source_sha256"]})
    (output / "expected-session-ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
    if not frames:
        raise ValueError("No readable qualified index-update files")
    bars = pd.concat(frames, ignore_index=True).sort_values("event_at")
    target = output / "spot.parquet"
    bars.to_parquet(target, index=False)
    fingerprint = sha256_file(target)
    transformation = {
        "adapter_version": "sparse-spot-minute-v1",
        "sources": sources,
        "derived_sha256": fingerprint,
        "reports": reports,
        "missing_source_sessions": missing,
        "session_calendar": coverage,
        "originals_modified": False,
    }
    (output / "transformation.json").write_text(json.dumps(transformation, indent=2) + "\n")
    manifest = DatasetManifest(
        id=dataset_id,
        kind="spot_bars",
        source_path=str(target.resolve()),
        source_sha256=fingerprint,
        fidelity="F2",
        provenance="HISTORICAL",
        timezone="Asia/Kolkata",
        bar_label="start",
        availability_lag_seconds=60,
        prior_exposed=True,
        timestamp_convention_verified=True,
        session_dates=sessions,
        metadata={
            "instrument": "NIFTY50",
            "timezone": "Asia/Kolkata",
            "bar_seconds": 60,
            "source_type": "sparse observed index updates, not certified complete exchange tape",
            "bar_convention_evidence": "Own left-labelled 60-second aggregation of UNIX feed epochs; no inherited unknown candle convention",
            "capture_clock_evidence": "Explicit IST localization; all original feed/capture delays checked before transformation",
            "partition_plan": "January development/training; February exploratory later assessment. No pristine confirmation.",
            "missing_source_sessions": missing,
            "session_calendar": coverage,
            "limitations": [
                "Prior research exposure unknown in detail; conservatively exposed.",
                "No options or executable-fill capability.",
                coverage["coverage_basis"],
                "Calendar provenance is caller supplied; this builder does not fetch or certify exchange notices.",
            ],
        },
        transformations=[
            {
                "version": "sparse-spot-minute-v1",
                "source_hashes": [s["sha256"] for s in sources],
                "output_sha256": fingerprint,
                "description": "Actual lp updates only; no price forward/back fill; all source row references retained privately.",
                "session_calendar": coverage,
            }
        ],
        exposure_history=[
            "Existing archive used by prior research; entire history conservatively prior-exposed."
        ],
    )
    report = qualify_dataset(manifest.model_dump(mode="json"))
    registry = Registry(runtime)
    enriched = manifest.model_copy(
        update={
            "capabilities": report.get("capabilities", []),
            "qualification_ref": registry.artifacts.put_json(report),
        }
    )
    registry.put("datasets", enriched.id, enriched)
    (output / "dataset.json").write_text(enriched.model_dump_json(indent=2) + "\n")
    (output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    target.chmod(0o400)
    return {
        "dataset_id": dataset_id,
        "qualification": report,
        "source_files": len(sources),
        "missing_source_sessions": missing,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument(
        "--calendar", type=Path, help="Explicit Jan-Feb2026 session JSON; never inferred"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(args.raw_root, args.output, args.runtime, args.dataset_id, args.calendar),
            indent=2,
        )
    )
