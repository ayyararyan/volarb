"""Bounded offline Jan/Feb option-source preparation with an explicit session denominator.

Creates immutable private subsets and aggregate manifests. At most two processes
perform data preparation; this script launches no economic evaluators or models.
A failed source/session remains a MISSING_DATA ledger entry, never zero P&L.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
from time import monotonic
from typing import Any

import pandas as pd

from butterfly_lab.data import qualify_dataset, sha256_file
from butterfly_lab.schemas import DatasetManifest
from prepare_local_options import prepare, write_json


def discover_sessions(archive_root: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for month in ("january_2026", "february_2026"):
        root = archive_root / month
        if not root.is_dir():
            raise FileNotFoundError(f"missing expected raw month: {month}")
        for path in sorted(root.iterdir()):
            if path.is_dir() and path.name.startswith("2026_"):
                stamp = pd.Timestamp(path.name.replace("_", "-"))
                if not "2026-01-01" <= stamp.strftime("%Y-%m-%d") <= "2026-02-28":
                    raise ValueError("session outside registered Jan-Feb2026 source scope")
                found.append((stamp.strftime("%Y-%m-%d"), path))
    if len(found) != len({session for session, _ in found}):
        raise ValueError("duplicate raw session directories")
    return sorted(found)


def build_one(task: tuple[str, str, str, int, list[int]]) -> dict[str, Any]:
    session, source, destination, width, management = task
    output = Path(destination)
    started = monotonic()
    record: dict[str, Any] = {"session": session, "width": width, "subset_path": destination}
    try:
        result = prepare(
            Path(source),
            session,
            output,
            f"local-nifty-w{width}-{session}-subset-v1",
            width,
            management,
        )
        record.update(status="QUALIFIED_SUBSET", result=result)
    except Exception as exc:
        record.update(status="MISSING_DATA", error_type=type(exc).__name__, reason=str(exc))
        # Do not touch an existing directory on accidental repeat invocation.
        if output.is_dir() and (output / "build-request.json").exists():
            write_json(output / "batch-failure.json", record)
    record["wall_seconds"] = monotonic() - started
    return record


def public_failure_reason(record: dict[str, Any]) -> str:
    """Keep raw source errors private; role-visible manifests need capability reasons."""
    reason = str(record.get("reason", "source qualification failed"))
    if record.get("error_type") == "DataQualificationError" and not any(
        root in reason for root in ("/Users/", "/Volumes/", "\\")
    ):
        return reason
    return (
        str(record.get("error_type", "SourceError"))
        + ": source unavailable or unreadable; details in private qualification ledger"
    )


def aggregate(
    root: Path,
    width: int,
    records: list[dict[str, Any]],
    expected: list[str],
    management: list[int],
) -> dict[str, Any]:
    output = root / f"width-{width}"
    output.mkdir(exist_ok=False)
    ledger = sorted([r for r in records if r["width"] == width], key=lambda r: r["session"])
    write_json(output / "expected-session-ledger.json", ledger)
    qualified = [r for r in ledger if r["status"] == "QUALIFIED_SUBSET"]
    failures = [r for r in ledger if r["status"] != "QUALIFIED_SUBSET"]
    if not qualified:
        result = {
            "width": width,
            "status": "DATA_LIMITED",
            "expected_sessions": len(expected),
            "qualified_sessions": 0,
        }
        write_json(output / "qualification.json", result)
        return result
    frames, manifests, transformations = [], [], []
    constructions = {}
    status_counts: dict[str, int] = {}
    for record in qualified:
        subset = Path(record["subset_path"])
        manifest = json.loads((subset / "dataset.json").read_text())
        if sha256_file(Path(manifest["source_path"])) != manifest["source_sha256"]:
            raise ValueError("prepared subset hash mismatch")
        frame = pd.read_parquet(manifest["source_path"])
        frames.append(frame)
        manifests.append(manifest)
        transformation = json.loads((subset / "transformation-manifest.json").read_text())
        transformations.append(
            {
                "session": record["session"],
                "manifest_sha256": sha256_file(subset / "dataset.json"),
                "transformation_sha256": sha256_file(subset / "transformation-manifest.json"),
                "subset_source_sha256": manifest["source_sha256"],
                "original_source_records": transformation["inputs"],
            }
        )
        constructions[record["session"]] = manifest["metadata"]["construction"]
        decisions = pd.read_parquet(subset / "grid-decisions.parquet")
        for status, count in decisions.status.value_counts().items():
            status_counts[str(status)] = status_counts.get(str(status), 0) + int(count)
    combined = pd.concat(frames, ignore_index=True).sort_values(["event_at", "contract_id"])
    if combined.duplicated(["event_at", "contract_id"]).any():
        raise ValueError("cross-session aggregate has conflicting source observation keys")
    data_path = output / "option-quotes.parquet"
    combined.to_parquet(data_path, index=False)
    digest = sha256_file(data_path)
    source_hashes = sorted({h for m in manifests for h in m["metadata"]["source_hashes"]})
    private_lineage = {
        "version": "local-option-session-batch-v1",
        "expected_sessions": expected,
        "subsets": transformations,
        "failed_session_records": failures,
        "original_source_hashes": source_hashes,
        "output_sha256": digest,
        "quote_rows": len(combined),
        "prior_exposed": True,
        "no_economics_or_model_calls": True,
    }
    write_json(output / "transformation-manifest.json", private_lineage)
    manifest = manifests[0].copy()
    manifest.update(
        id=f"local-nifty-weekly-w{width}-20260102-v1",
        source_path=str(data_path.resolve()),
        source_sha256=digest,
        session_dates=expected,
        exposure_history=[
            "All source history previously used in development; no pristine confirmation exists.",
            "January2 source/quote calibration and prior smoke outcomes already observed; retained in later exploratory program.",
        ],
        transformations=[
            {
                "version": "local-option-session-batch-v1",
                "output_sha256": digest,
                "input_subset_hashes": [m["source_sha256"] for m in manifests],
                "source_hashes": source_hashes,
                "transform_manifest_sha256": sha256_file(output / "transformation-manifest.json"),
            }
        ],
    )
    metadata = dict(manifests[0]["metadata"])
    metadata.pop("construction", None)
    metadata.pop("selection_spot_known_at", None)
    metadata.update(
        sessions={session: {"open": "09:15:00", "close": "15:30:00"} for session in expected},
        per_session_construction=constructions,
        source_hashes=source_hashes,
        expected_session_count=len(expected),
        observed_session_count=len(qualified),
        missing_sessions=[
            {"session": r["session"], "reason": public_failure_reason(r)} for r in failures
        ],
        missing_session_semantics="Missing observations; never a zero-return or loss outcome. All expected sessions retained.",
        supported_management_minutes=management,
        supported_exit_minutes=[*management, 30],
        wing_width=width,
        prior_calibration_sessions=["2026-01-02"],
        limitations=[
            x.replace("Prior-exposed one-session subset", "Prior-exposed multi-session subset")
            for x in metadata["limitations"]
        ]
        + [
            "Qualified observations do not certify complete eligible opportunity coverage; missing sessions and grids remain explicit.",
            "All39 source-session denominator is retained; numerical outcome ceiling must reflect data-limited opportunities.",
            "Only entry10:00, listed management times and exit10:30 have dense execution windows.",
        ],
    )
    manifest["metadata"] = metadata
    manifest = DatasetManifest.model_validate(manifest).model_dump(mode="json")
    qualification = qualify_dataset(manifest)
    manifest["capabilities"] = qualification.get("capabilities", [])
    write_json(output / "dataset.json", manifest)
    write_json(output / "qualification.json", qualification)
    report = {
        "dataset_id": manifest["id"],
        "width": width,
        "status": qualification["status"],
        "expected_sessions": len(expected),
        "qualified_subset_sessions": len(qualified),
        "missing_sessions": [r["session"] for r in failures],
        "rows": len(combined),
        "original_source_hash_count": len(source_hashes),
        "grid_status_counts_qualified_subsets": status_counts,
        "source_sha256": digest,
        "no_economics_or_model_calls": True,
    }
    write_json(output / "coverage-report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--widths", nargs="+", type=int, default=[200, 500])
    parser.add_argument("--management-minutes", nargs="+", type=int, default=[10, 15, 20])
    parser.add_argument("--workers", type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    sessions = discover_sessions(args.archive_root)
    args.output.mkdir(parents=True, exist_ok=False)
    widths = sorted(set(args.widths))
    management = sorted(set(args.management_minutes))
    write_json(
        args.output / "batch-request.json",
        {
            "archive_root": str(args.archive_root.resolve()),
            "widths": widths,
            "management_minutes": management,
            "workers": args.workers,
            "expected_sessions": [session for session, _ in sessions],
            "tasks": len(sessions) * len(widths),
            "batch_builder_sha256": sha256_file(Path(__file__)),
            "session_builder_sha256": sha256_file(
                Path(__file__).with_name("prepare_local_options.py")
            ),
            "no_economics_or_model_calls": True,
        },
    )
    tasks = [
        (
            session,
            str(path),
            str(args.output / "subsets" / f"w{width}" / session),
            width,
            management,
        )
        for width in widths
        for session, path in sessions
    ]
    records = []
    started = monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(build_one, task): task for task in tasks}
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            with (args.output / "session-progress.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\n")
            print(
                json.dumps(
                    {
                        "completed": len(records),
                        "total": len(tasks),
                        "session": record["session"],
                        "width": record["width"],
                        "status": record["status"],
                        "reason": record.get("reason"),
                    }
                ),
                flush=True,
            )
    write_json(
        args.output / "expected-session-ledger.json",
        sorted(records, key=lambda r: (r["width"], r["session"])),
    )
    reports = [
        aggregate(args.output, width, records, [session for session, _ in sessions], management)
        for width in widths
    ]
    write_json(
        args.output / "batch-summary.json",
        {
            "datasets": reports,
            "wall_seconds": monotonic() - started,
            "preparation_workers": args.workers,
            "model_calls": 0,
            "numerical_economic_jobs": 0,
        },
    )
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
