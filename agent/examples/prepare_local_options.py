"""Prepare a private, immutable four-contract quote subset; never fetch market data.

Example (source location deliberately supplied by caller, never hard-coded):
    python examples/prepare_local_options.py --session-dir "$LOCAL_SESSION" \
      --session 2026-01-02 --output "$PRIVATE_NEW_DIRECTORY" --dataset-id local-options-v1

Only exact-date NIFTY weekly contracts are supported. The fixed entry spot is a
construction input, not a contemporaneous dynamic underlying feed. Recentring,
multiple entry times and alternative wing widths require a new derived dataset.
"""

from __future__ import annotations

import argparse
import json
import math
import inspect
from pathlib import Path
from typing import Any

import pandas as pd

from butterfly_lab.data import DataQualificationError, qualify_dataset, sha256_file
from butterfly_lab.local_option_archive import parse_weekly_symbol, read_option_snapshots
from butterfly_lab.schemas import DatasetManifest

TZ = "Asia/Kolkata"
SOURCES = {
    "feed_semantics": "https://www.shoonya.com/api-documentation/subscribe-market-feed",
    "depth_semantics": "https://github.com/Shoonya-Dev/ShoonyaApi-py",
    "historical_lot": "https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf",
    "ipft": "https://archives.nseindia.com/content/circulars/FA56129.pdf",
    "fee_breakdown_confirmation": "https://nsearchives.nseindia.com/content/circulars/FA73061.pdf",
}


def historical_fee_schedule() -> list[dict[str, Any]]:
    """Jan–Feb 2026: NSE transaction3503 + IPFT50 per crore of premium.

    The existing evaluator applies GST to its exchange-rate component, so bind
    the combined NSE/IPFT rate here. Do not silently omit IPFT or count it twice.
    Brokerage and per-fill rounding remain explicit research assumptions.
    """
    return [
        {
            "effective_from": "2026-01-01",
            "effective_to": "2026-02-28",
            "brokerage_per_fill": 20.0,
            "exchange_rate": 0.0003553,
            "regulatory_rate": 0.000001,
            "gst_rate": 0.18,
            "sell_tax_rate": 0.001,
            "buy_stamp_rate": 0.00003,
            "source": (
                "Jan-Feb2026 NSE transaction3503 + IPFT50 per crore of premium; "
                "SEBI10 per crore separately; brokerage20/fill modeled; "
                "aggregate paise rounding approximation. FA56129 and FA73061."
            ),
        }
    ]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")


def selection_spot(path: Path, entry: pd.Timestamp) -> tuple[float, dict[str, Any]]:
    fingerprint = sha256_file(path)
    frame = pd.read_parquet(path)
    if sha256_file(path) != fingerprint:
        raise DataQualificationError("spot source changed during read")
    required = {"timestamp", "ft", "lp", "ts", "tk", "e"}
    if not required.issubset(frame):
        raise DataQualificationError("spot feed missing required fields")
    symbols = frame.ts.dropna().astype(str).unique().tolist()
    if (
        symbols != ["Nifty 50"]
        or set(frame.tk.dropna().astype(str)) != {"26000"}
        or set(frame.e.dropna().astype(str)) != {"NSE"}
    ):
        raise DataQualificationError("NIFTY spot requires symbol Nifty50, token26000, exchangeNSE")
    receipts = pd.to_datetime(frame.timestamp, format="ISO8601", errors="raise")
    if receipts.dt.tz is None:
        receipts = receipts.dt.tz_localize(TZ)
    receipts = receipts.dt.tz_convert("UTC")
    if receipts.duplicated().any():
        raise DataQualificationError("ambiguous spot receipt clock ties")
    feed = pd.to_datetime(pd.to_numeric(frame.ft, errors="raise"), unit="s", utc=True)
    if (feed > receipts).any():
        raise DataQualificationError("spot feed later than receipt")
    prices = pd.to_numeric(frame.lp.replace({"None": None, "": None}), errors="raise")
    eligible = (receipts <= entry) & (feed <= entry) & prices.notna()
    if not eligible.any():
        raise DataQualificationError("no past-available entry spot")
    selected = receipts.loc[eligible].idxmax()
    price = float(prices.loc[selected])
    if (
        not math.isfinite(price)
        or price <= 0
        or (entry - receipts.loc[selected]).total_seconds() > 5
    ):
        raise DataQualificationError("invalid or stale observed construction spot")
    # Identity must itself have been available, not inferred from future metadata.
    known = frame.loc[(receipts <= entry) & frame.ts.notna(), "ts"]
    if (
        known.empty
        or known.iloc[0] != "Nifty 50"
        or not frame.loc[receipts <= entry, "tk"].eq("26000").any()
        or not frame.loc[receipts <= entry, "e"].eq("NSE").any()
    ):
        raise DataQualificationError("spot identity not yet observed")
    return price, {
        "source_path": str(path.resolve()),
        "source_sha256": fingerprint,
        "source_rows": len(frame),
        "source_row": int(selected),
        "event_at": feed.loc[selected].isoformat(),
        "receive_at": receipts.loc[selected].isoformat(),
        "available_at": max(feed.loc[selected], receipts.loc[selected]).isoformat(),
        "spot": price,
    }


def select_contracts(
    session_dir: Path, session: str, spot: float, width: int
) -> tuple[list[tuple[Path, dict[str, Any]]], dict[str, Any]]:
    suffix = "_" + session.replace("-", "_") + ".parquet"
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(session_dir.glob("NIFTY*" + suffix)):
        symbol = path.name[: -len(suffix)]
        try:
            identity = parse_weekly_symbol(symbol)
        except DataQualificationError:
            continue  # Explicit-date-only universe; monthly/spot never mislabeled.
        if identity["underlying"] == "NIFTY" and identity["expiry"] >= session:
            candidates.append((path, identity))
    if not candidates:
        raise DataQualificationError("no exact-date weekly NIFTY contracts in source catalog")
    expiry = min(x[1]["expiry"] for x in candidates)
    chain = {
        (x[1]["strike"], x[1]["option_type"]): x for x in candidates if x[1]["expiry"] == expiry
    }
    calls = {k for k, side in chain if side == "CE"}
    puts = {k for k, side in chain if side == "PE"}
    if not calls & puts:
        raise DataQualificationError("nearest weekly expiry has no common CE/PE body")
    body = min(calls & puts, key=lambda strike: (abs(strike - spot), strike))
    keys = [(body, "CE"), (body, "PE"), (body + width, "CE"), (body - width, "PE")]
    if any(key not in chain for key in keys):
        raise DataQualificationError("fixed registered wings missing; no fallback to another body")
    return [chain[key] for key in keys], {
        "expiry": expiry,
        "body": body,
        "wing_width": width,
        "selection": "nearest common CE/PE strike to past-available entry spot, lower strike on ties",
        "universe": "nearest nonexpired explicitly dated weekly NIFTY catalog expiry",
        "contract_ids": [chain[key][1]["contract_id"] for key in keys],
    }


def canonical_snapshots(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Remove only identical full rows; conflicting coarse event keys fail closed."""
    result = (
        snapshots.drop_duplicates().sort_values(["event_at", "contract_id"]).reset_index(drop=True)
    )
    if result.duplicated(["event_at", "contract_id"]).any():
        raise DataQualificationError(
            "conflicting coarse feed event keys; source sequence unsupported"
        )
    return result


def prepare(
    session_dir: Path,
    session: str,
    output: Path,
    dataset_id: str,
    width: int,
    management_minutes: list[int] | None = None,
) -> dict[str, Any]:
    if not "2026-01-01" <= session <= "2026-02-28":
        raise ValueError(
            "this registered fee/contract schedule is limited to January–February 2026"
        )
    if width <= 0 or width % 50:
        raise ValueError("wing width must be a positive 50-point multiple")
    management = sorted(set([15] if management_minutes is None else management_minutes))
    if not management or any(m <= 0 or m >= 30 for m in management):
        raise ValueError("management minutes must be an explicit nonempty subset of 1..29")
    # Never overwrite a prior run, even if it failed. Caller must choose a new ID.
    output.mkdir(parents=True, exist_ok=False)
    write_json(
        output / "build-request.json",
        {
            "session_dir": str(session_dir.resolve()),
            "session": session,
            "dataset_id": dataset_id,
            "width": width,
            "management_minutes": management,
        },
    )
    entry = pd.Timestamp(session + " 10:00:00", tz=TZ).tz_convert("UTC")
    spot_path = session_dir / ("NIFTY50_" + session.replace("-", "_") + ".parquet")
    spot, spot_evidence = selection_spot(spot_path, entry)
    contracts, construction = select_contracts(session_dir, session, spot, width)
    grids = set(pd.date_range(session + " 10:01", session + " 10:29", freq="min", tz=TZ))
    for offset in [0, *management, 30]:
        start = entry + pd.Timedelta(minutes=offset)
        grids.update(pd.date_range(start, periods=61, freq="s").tz_convert(TZ))
    grid = sorted(grids)
    original_records = [spot_evidence]
    write_json(output / "original-sources.json", original_records)
    for path, identity in contracts:
        original_records.append(
            {
                "source_path": str(path.resolve()),
                "source_sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "contract_id": identity["contract_id"],
            }
        )
        write_json(output / "original-sources.json", original_records)
    snapshots: list[pd.DataFrame] = []
    dispositions: list[pd.DataFrame] = []
    adapter_audits = []
    for (path, identity), original in zip(contracts, original_records[1:], strict=True):
        fingerprint = original["source_sha256"]
        result = read_option_snapshots(
            path,
            grid,
            expected_sha256=fingerprint,
            receipt_timezone=TZ,
            sparse_delta_verified=True,
            expected_symbol=identity["contract_id"],
            max_field_age_seconds=5,
            max_message_age_seconds=5,
        )
        snapshots.append(result.snapshots)
        decisions = result.decisions.copy()
        decisions["contract_id"] = identity["contract_id"]
        dispositions.append(decisions)
        adapter_audits.append(result.audit)
        result.snapshots.to_parquet(
            output / (identity["contract_id"] + "-snapshots.parquet"), index=False
        )
        decisions.to_parquet(output / (identity["contract_id"] + "-decisions.parquet"), index=False)
        write_json(output / (identity["contract_id"] + "-audit.json"), result.audit)
    raw_snapshots = pd.concat(snapshots, ignore_index=True)
    if raw_snapshots.empty:
        raise DataQualificationError("no accepted quote states; retained source evidence required")
    if set(raw_snapshots.lot_size) != {65}:
        raise DataQualificationError("observed lot differs from registered historical NIFTY65")
    raw_snapshots["spot"] = spot
    raw_snapshots["selection_spot"] = spot
    raw_snapshots["selection_spot_available_at"] = pd.Timestamp(spot_evidence["available_at"])
    raw_snapshots.to_parquet(output / "all-adapter-snapshots.parquet", index=False)
    pd.concat(dispositions, ignore_index=True).to_parquet(
        output / "grid-decisions.parquet", index=False
    )
    # A coarse feed epoch may bind several distinct received states. Deleting
    # an earlier state on later evidence would retrospectively change eligibility.
    # Preserve every snapshot above and fail closed on any non-identical collision.
    canonical = canonical_snapshots(raw_snapshots)
    data_path = output / "option-quotes.parquet"
    canonical.to_parquet(data_path, index=False)
    data_hash = sha256_file(data_path)
    transformation = {
        "version": "local-option-sparse-snapshot-v2",
        "builder_sha256": sha256_file(Path(__file__)),
        "adapter_sha256": sha256_file(Path(inspect.getfile(read_option_snapshots))),
        "inputs": original_records,
        "output": {"path": str(data_path.resolve()), "sha256": data_hash, "rows": len(canonical)},
        "source_rows": sum(a["source_rows"] for a in adapter_audits),
        "all_snapshot_rows": len(raw_snapshots),
        "collapsed_duplicate_event_keys": len(raw_snapshots) - len(canonical),
        "selection_spot": spot_evidence,
        "construction": construction,
        "grid": [stamp.isoformat() for stamp in grid],
        "adapter_audits": adapter_audits,
        "raw_modified": False,
        "all_grid_dispositions_retained": True,
    }
    write_json(output / "transformation-manifest.json", transformation)
    limitations = [
        "F3 is a quote-simulation ceiling, not executable-price or queue-position evidence.",
        "Feed ft is provider feed time, not independently certified exchange-event time.",
        "Sparse state reconstruction relies on explicit dk/df omitted-fields-unchanged contract.",
        "Component change age <=5 seconds is a conservative registered sample-selection rule.",
        "Single fixed entry body/wing set and constant entry spot; recentering is unsupported.",
        "Dataset covers selected decision/fill/holding grids, not a complete executable tape.",
        "Brokerage20 per fill and aggregate paise rounding are research assumptions.",
        "No broker margin or capital is inferred from this dataset.",
        "Prior-exposed one-session subset is exploratory; no protected confirmation.",
    ]
    manifest = DatasetManifest(
        id=dataset_id,
        kind="option_quotes",
        source_path=str(data_path.resolve()),
        source_sha256=data_hash,
        fidelity="F3",
        provenance="HISTORICAL",
        timezone=TZ,
        bar_label="event",
        availability_lag_seconds=0,
        partition="development",
        prior_exposed=True,
        timestamp_convention_verified=True,
        session_dates=[session],
        exposure_history=[
            "Historical warehouse previously used for development; all new work exploratory."
        ],
        transformations=[
            {
                "version": transformation["version"],
                "source_hashes": [x["source_sha256"] for x in original_records],
                "output_sha256": data_hash,
                "builder_sha256": transformation["builder_sha256"],
                "adapter_sha256": transformation["adapter_sha256"],
                "transform_manifest_sha256": sha256_file(output / "transformation-manifest.json"),
                "duplicate_event_keys_collapsed": transformation["collapsed_duplicate_event_keys"],
            }
        ],
        metadata={
            "timezone": TZ,
            "clock_tolerance_seconds": 0,
            "source_refs": SOURCES,
            "source_hashes": [x["source_sha256"] for x in original_records],
            "sessions": {session: {"open": "09:15:00", "close": "15:30:00"}},
            "construction": construction,
            "selection_spot_known_at": spot_evidence["available_at"],
            "recentring_supported": False,
            "execution_scope": {
                "entry_time": "10:00:00",
                "width_floor": width,
                "hold_minutes": 30,
                "management": ["close"],
                "management_after_minutes": management,
                "lots": 1,
                "shared_selection_spot": True,
            },
            "supported_management_minutes": management,
            "supported_exit_minutes": [*management, 30],
            "fine_execution_windows_seconds": 60,
            "limitations": limitations,
            "fee_schedule": historical_fee_schedule(),
            "fee_components_per_crore_premium": {
                "nse_transaction": 3503,
                "nse_ipft": 50,
                "sebi": 10,
            },
            "contract_specs": [
                {
                    "underlying": "NIFTY",
                    "effective_from": "2026-01-01",
                    "effective_to": "2026-02-28",
                    "known_at": "2025-10-03",
                    "lot_size": 65,
                    "source": SOURCES["historical_lot"],
                }
            ],
        },
    )
    value = manifest.model_dump(mode="json")
    qualification = qualify_dataset(value)
    value["capabilities"] = qualification["capabilities"]
    write_json(output / "qualification.json", qualification)
    write_json(output / "dataset.json", value)
    write_json(
        output / "build-summary.json",
        {
            "dataset_id": dataset_id,
            "fidelity": "F3",
            "qualification": qualification,
            "source_files": len(original_records),
            "construction": construction,
            "rejected_grid_counts": pd.concat(dispositions).status.value_counts().to_dict(),
            "derived_source_sha256": data_hash,
            "limitations": limitations,
        },
    )
    if qualification["status"] != "PASS":
        raise DataQualificationError(
            "derived dataset failed qualification; retained private report"
        )
    return {
        "dataset_id": dataset_id,
        "qualification": qualification,
        "source_files": len(original_records),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--width", type=int, default=200)
    parser.add_argument("--management-minutes", type=int, nargs="+", default=[15])
    args = parser.parse_args()
    existed = args.output.exists()
    try:
        result = prepare(
            args.session_dir,
            args.session,
            args.output,
            args.dataset_id,
            args.width,
            args.management_minutes,
        )
    except Exception as exc:
        if not existed and args.output.is_dir():
            write_json(
                args.output / "build-failure.json", {"type": type(exc).__name__, "reason": str(exc)}
            )
        raise
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
