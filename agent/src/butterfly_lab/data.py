"""Read-only market adapters and conservative capability qualification.

No adapter infers a security from an ATM-relative lane. Raw files are never edited.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
import math
from pathlib import Path
from typing import Any

import pandas as pd


class DataQualificationError(ValueError):
    """A documented observation/identity limitation, not a missing implementation."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def metadata(dataset: dict[str, Any]) -> dict[str, Any]:
    return dataset.get("metadata", dataset.get("options", {})) or {}


def aware_times(values: Any, name: str) -> pd.Series:
    series = pd.Series(values)
    if series.isna().any():
        raise DataQualificationError(f"{name}: missing timestamps")
    parsed = []
    for value in series:
        t = pd.Timestamp(value)
        if t.tzinfo is None:
            raise DataQualificationError(f"{name}: timezone offset required")
        parsed.append(t.tz_convert("UTC"))
    return pd.Series(parsed, index=series.index, dtype="datetime64[ns, UTC]")


def _read_file(path: Path, meta: dict[str, Any]) -> pd.DataFrame:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = meta.get("members")
            if members is None:
                names = [
                    n
                    for n in archive.namelist()
                    if n.endswith(".csv") and "MANIFEST" not in n.upper()
                ]
                yearly = [n for n in names if "/yearly/" in n]
                members = yearly or names
            if not members:
                raise DataQualificationError("ZIP has no selected CSV members")
            frames = []
            for member in sorted(members):
                body = archive.read(member)  # zipfile verifies member CRC on read
                expected = meta.get("member_sha256", {}).get(member)
                if expected and hashlib.sha256(body).hexdigest() != expected:
                    raise DataQualificationError("ZIP member hash mismatch")
                frame = pd.read_csv(io.BytesIO(body))
                frame["source_member"] = member
                frames.append(frame)
            return pd.concat(frames, ignore_index=True)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix in {".csv", ".gz"}:
        return pd.read_csv(path)
    if path.suffix == ".json":
        obj = json.loads(path.read_text())
        return pd.DataFrame(obj.get("rows", obj) if isinstance(obj, dict) else obj)
    if path.suffix == ".jsonl":
        return pd.read_json(path, lines=True, convert_dates=False)
    raise DataQualificationError(f"unsupported source extension: {path.suffix}")


def load_dataset(dataset: dict[str, Any]) -> pd.DataFrame:
    meta = metadata(dataset)
    if "rows" in meta:
        if dataset.get("provenance") not in {"SYNTHETIC", "MODEL"}:
            raise DataQualificationError("inline rows require SYNTHETIC or MODEL provenance")
        frame = pd.DataFrame(meta["rows"])
    else:
        path = Path(dataset.get("source_path", ""))
        if not str(dataset.get("source_path", "")) or not path.exists():
            raise DataQualificationError("source is unavailable")
        if path.is_dir():
            files = sorted(path.glob(meta.get("glob", "*.parquet")))
            if not files:
                raise DataQualificationError("source directory has no selected files")
            frame = pd.concat([_read_file(p, meta) for p in files], ignore_index=True)
        else:
            expected = dataset.get("source_sha256")
            if expected and sha256_file(path) != expected:
                raise DataQualificationError("source hash mismatch")
            frame = _read_file(path, meta)
    if frame.empty:
        raise DataQualificationError("empty observations")
    rename = meta.get("column_map", {})
    frame = frame.rename(columns=rename)
    if "instrument_id" in frame and "contract_id" not in frame:
        frame["contract_id"] = frame.instrument_id
    if "event_at" not in frame:
        for name in ("datetime", "timestamp", "exchange_ts"):
            if name in frame:
                frame["event_at"] = frame[name]
                break
    if "event_at" not in frame:
        raise DataQualificationError("event timestamp missing")
    if meta.get("timestamp_unit"):
        frame["event_at"] = pd.to_datetime(frame.event_at, unit=meta["timestamp_unit"], utc=True)
    frame["event_at"] = aware_times(frame.event_at, "event_at")
    kind = dataset.get("kind")
    if kind in {"spot_bars", "option_bars"}:
        label = dataset.get("bar_label", meta.get("bar_label"))
        if label not in {"start", "end"}:
            raise DataQualificationError("explicit start/end bar label required")
        seconds = int(meta.get("bar_seconds", 60))
        if seconds <= 0:
            raise DataQualificationError("positive bar duration required")
        frame["bar_end"] = frame.event_at + pd.to_timedelta(
            seconds if label == "start" else 0, unit="s"
        )
    else:
        frame["bar_end"] = frame.event_at
    lag = float(dataset.get("availability_lag_seconds", 0))
    if lag < 0:
        raise DataQualificationError("availability lag cannot be negative")
    if "receive_at" not in frame and "receive_ts" in frame:
        frame["receive_at"] = frame.receive_ts
    if "receive_at" in frame:
        frame["receive_at"] = aware_times(frame.receive_at, "receive_at")
        tolerance = float(meta.get("clock_tolerance_seconds", 1))
        if (frame.event_at > frame.receive_at + pd.to_timedelta(tolerance, unit="s")).any():
            raise DataQualificationError(
                "event clock is later than receipt: clock semantics unresolved"
            )
    if "available_at" in frame:
        frame["available_at"] = aware_times(frame.available_at, "available_at")
    else:
        frame["available_at"] = frame.bar_end + pd.to_timedelta(lag, unit="s")
        if "receive_at" in frame:
            frame["available_at"] = frame[["available_at", "receive_at"]].max(axis=1)
    earliest = frame.bar_end + pd.to_timedelta(lag, unit="s")
    if (frame.available_at < earliest).any() or (
        "receive_at" in frame and (frame.available_at < frame.receive_at).any()
    ):
        raise DataQualificationError(
            "availability precedes observed bar/receipt plus registered lag"
        )
    timezone = meta.get("timezone", "Asia/Kolkata")
    frame["session"] = frame.event_at.dt.tz_convert(timezone).dt.strftime("%Y-%m-%d")
    # Explicit identity records, not inferred ATM lanes or current-contract maps.
    identity_map = meta.get("identity_map", {})
    if "contract_id" in frame and identity_map:
        for field in ("underlying", "expiry", "strike", "option_type", "lot_size"):
            if field not in frame:
                frame[field] = frame.contract_id.map(
                    lambda key: identity_map.get(str(key), {}).get(field)
                )
    # DAT market-event adapter: top-of-book only, never pretend to consume depth.
    if "bids" in frame and "asks" in frame:
        for plural, side in (("bids", "bid"), ("asks", "ask")):
            if side not in frame:
                frame[side] = frame[plural].map(
                    lambda levels: (
                        float(levels[0]["price"]) if levels is not None and len(levels) else None
                    )
                )
                frame[side + "_size"] = frame[plural].map(
                    lambda levels: (
                        int(levels[0]["quantity"]) if levels is not None and len(levels) else None
                    )
                )
        # Non-book OI/control messages remain outside book observations; count
        # them explicitly rather than interpreting empty depth as a zero price.
        if "event_type" in frame:
            control = frame.event_type.isin(["open_interest", "heartbeat", "subscription"])
            control_count = int(control.sum())
            frame = frame[~control].copy()
            frame.attrs["non_book_messages"] = control_count
    frame["session_class"] = "regular"
    local = frame.event_at.dt.tz_convert(timezone)
    clocks = local.dt.strftime("%H:%M:%S")
    opening = meta.get("session_open", "09:15:00")
    closing = meta.get("session_close", "15:30:00")
    frame.loc[(clocks < opening) | (clocks >= closing), "session_class"] = "outside_regular"
    for date, specification in meta.get("sessions", {}).items():
        mask = frame.session.eq(date)
        if specification.get("closed"):
            frame.loc[mask, "session_class"] = "closed"
        else:
            frame.loc[mask, "session_class"] = "regular"
            frame.loc[
                mask
                & (
                    (clocks < specification.get("open", opening))
                    | (clocks >= specification.get("close", closing))
                ),
                "session_class",
            ] = "outside_registered"
    keys = ["event_at"]
    if kind in {"option_quotes", "option_bars"} or "contract_id" in frame:
        required = {"contract_id", "underlying", "expiry", "strike", "option_type", "lot_size"}
        if not required <= set(frame):
            raise DataQualificationError(
                "fixed contract identity/expiry/strike/lot fields required; rolling lanes inadmissible"
            )
        if frame[list(required)].isna().any().any():
            raise DataQualificationError("null contract identity")
        if (
            frame.contract_id.astype(str)
            .str.contains(r"ATM|WEEK[123]|MONTH[123]", regex=True)
            .any()
        ):
            raise DataQualificationError("rolling lane cannot identify a held security")
        if not frame.option_type.isin(["CE", "PE"]).all():
            raise DataQualificationError("option_type must be CE or PE")
        frame["expiry"] = frame.expiry.astype(str).str[:10]
        pd.to_datetime(frame.expiry, format="%Y-%m-%d", errors="raise")
        if (frame.expiry < frame.session).any():
            raise DataQualificationError("observation after contract expiry")
        if ((pd.to_numeric(frame.lot_size) <= 0) | (pd.to_numeric(frame.lot_size) % 1 != 0)).any():
            raise DataQualificationError("invalid lot units")
        identity = ["underlying", "expiry", "strike", "option_type"]
        if (frame.groupby("contract_id")[identity].nunique() > 1).any().any():
            raise DataQualificationError("contract roll or conflicting identity")
        keys.append("contract_id")
    compare = [c for c in frame if c not in {"source_member", "bids", "asks", "quality_flags"}]
    unique = frame.drop_duplicates(subset=compare)
    if unique.duplicated(keys).any():
        raise DataQualificationError("conflicting duplicate observation keys")
    unique = unique.sort_values(keys).reset_index(drop=True)
    unique.attrs["identical_duplicates_removed"] = len(frame) - len(unique)
    for name in ("open", "high", "low", "close", "bid", "ask", "spot", "strike"):
        if name in unique:
            unique[name] = pd.to_numeric(unique[name], errors="raise")
            if (
                unique[name].isna().any()
                or not unique[name].map(math.isfinite).all()
                or (unique[name] < 0).any()
            ):
                raise DataQualificationError(f"invalid {name}")
    if {"open", "high", "low", "close"} <= set(unique):
        if (
            (unique.high < unique[["open", "close", "low"]].max(axis=1))
            | (unique.low > unique[["open", "close", "high"]].min(axis=1))
        ).any():
            raise DataQualificationError("OHLC inequalities violated")
    return unique


def qualify_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    if dataset.get("fidelity") == "F4":
        return {
            "status": "UNSUPPORTED",
            "errors": ["F4 depth/event fill replay is outside this release"],
            "capabilities": [],
        }
    try:
        if (
            dataset.get("kind") in {"synthetic", "session_panel"}
            and metadata(dataset).get("generator") == "controlled_session_panel_v1"
        ):
            if dataset.get("provenance") != "SYNTHETIC" or dataset.get("fidelity") != "F0":
                raise DataQualificationError("controlled generator requires SYNTHETIC/F0")
            return {
                "status": "PASS",
                "errors": [],
                "capabilities": ["controlled_sessions", "synthetic_session_outcomes"],
                "prior_exposed": True,
                "rows": int(metadata(dataset).get("n_sessions", 48)),
            }
        frame = load_dataset(dataset)
        kind = dataset.get("kind")
        fidelity = dataset.get("fidelity", "F0")
        if fidelity == "F3" and (
            kind != "option_quotes"
            or not {"bid", "ask", "bid_size", "ask_size", "receive_at"} <= set(frame)
        ):
            raise DataQualificationError(
                "F3 requires observed two-sided quotes, sizes and receipt timestamps"
            )
        if fidelity == "F2" and kind not in {"option_bars", "spot_bars"}:
            raise DataQualificationError(
                "F2 requires observed spot bars or identified option bars; spot grants no option execution capability"
            )
        if fidelity == "F1" and dataset.get("provenance") != "MODEL":
            raise DataQualificationError("F1 requires explicit MODEL provenance")
        if fidelity == "F0" and dataset.get("provenance") != "SYNTHETIC":
            raise DataQualificationError("F0 cannot label historical data synthetic")
        capabilities = ["timestamped_observations"]
        if kind == "spot_bars":
            capabilities += ["spot_bars", "spot_excursion", "past_only_rv", "past_only_drift"]
        if "contract_id" in frame:
            capabilities += ["identified_contracts", "dated_lot_units"]
        if {"bid", "ask", "bid_size", "ask_size"} <= set(frame):
            if (
                (frame.ask < frame.bid)
                | (frame.bid <= 0)
                | (frame.bid_size < 0)
                | (frame.ask_size < 0)
            ).any():
                raise DataQualificationError("crossed/invalid book")
            capabilities += ["two_sided_quotes", "displayed_size"]
        return {
            "status": "PASS",
            "errors": [],
            "rows": len(frame),
            "sessions": int(frame.session.nunique()),
            "start": frame.event_at.min().isoformat(),
            "end": frame.event_at.max().isoformat(),
            "capabilities": capabilities,
            "identical_duplicates_removed": frame.attrs.get("identical_duplicates_removed", 0),
            "session_classes": frame.session_class.value_counts().to_dict(),
            "prior_exposed": dataset.get("prior_exposed", True),
            "limitations": [
                "Calendar defaults are classification rules, not independently certified exchange calendars"
            ]
            if not metadata(dataset).get("sessions")
            else [],
        }
    except (DataQualificationError, OSError, ValueError, KeyError) as exc:
        return {"status": "DATA_LIMITED", "errors": [str(exc)], "capabilities": []}


inspect_dataset = qualify_dataset
