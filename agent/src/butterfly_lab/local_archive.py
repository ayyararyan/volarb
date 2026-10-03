"""Read-only sparse index-update adapter; never reconstruct an option or quote book.

``ft`` is a feed epoch second and ``timestamp`` is a naive capture clock in the
explicitly supplied timezone. These semantics must be established for the source
before use. Bars contain only genuine ``lp`` observations: absent prices/buckets
are never filled. Source offsets and hashes permit reconstruction from originals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import DataQualificationError, sha256_file

ADAPTER_VERSION = "sparse-spot-minute-v1"


class ArchiveAdapterError(DataQualificationError):
    """A hard source error, retaining its row-level diagnostic instead of filtering."""

    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def spot_updates_to_minutes(
    raw: pd.DataFrame,
    *,
    source_sha256: str,
    instrument: str,
    expected_token: str,
    expected_exchange: str,
    expected_symbol: str | None = None,
    expected_session: str | None = None,
    capture_timezone: str = "Asia/Kolkata",
    clock_tolerance_seconds: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Construct left-labelled minute OHLC without mutating ``raw``.

    Equal feed seconds use capture timestamps for ordering. Conflicting prices
    at identical feed *and* capture clocks fail because their order is unknown;
    identical ties retain all source row offsets. Clock violations and invalid
    prices fail the whole file, rather than removing difficult observations.
    Non-price/control rows do not supply prices but their identities/clocks are
    still checked. Out-of-session prices are retained and counted, not excluded.
    """
    report: dict[str, Any] = {
        "adapter_version": ADAPTER_VERSION,
        "status": "CHECKING",
        "source_sha256": source_sha256,
        "source_rows": len(raw),
        "instrument": instrument,
        "bar_label": "start",
        "bar_seconds": 60,
        "availability_lag_seconds": 60,
        "capture_timezone": capture_timezone,
        "clock_tolerance_seconds": clock_tolerance_seconds,
        "price_forward_fill": False,
        "price_backward_fill": False,
        "limitations": [
            "Sparse observed index updates, not a certified complete exchange tick tape.",
            "Feed epoch and localized capture clocks are source semantics, not exchange-clock certification.",
            "Regular 09:15–15:30 classification is not exchange-calendar certification.",
            "Index observations provide no option identity, liquidity or execution capability.",
        ],
    }

    def fail(reason: str, rows: list[int] | None = None) -> None:
        report.update(status="DATA_LIMITED", error=reason, error_source_rows=rows or [])
        raise ArchiveAdapterError(reason, report)

    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        fail("an exact original source SHA256 is required")
    if not np.isfinite(clock_tolerance_seconds) or clock_tolerance_seconds < 0:
        fail("clock tolerance must be finite and nonnegative")
    required = {"ft", "timestamp", "lp", "tk", "e"}
    if not required <= set(raw) or raw.empty:
        fail("nonempty sparse source requires ft, timestamp, lp, tk and e")
    data = raw.reset_index(drop=True).copy(deep=True)
    data["source_row"] = np.arange(len(data))
    for column, expected in (("tk", expected_token), ("e", expected_exchange)):
        values = data[column].astype("string")
        bad = values.isna() | values.ne(expected)
        if bad.any():
            fail("source instrument identity mismatch: " + column, data.index[bad].tolist())
    symbols = sorted(data.ts.dropna().astype(str).unique().tolist()) if "ts" in data else []
    if len(symbols) > 1 or (expected_symbol is not None and symbols not in ([], [expected_symbol])):
        fail("source trading symbol identity mismatch")
    report["identity"] = {
        "token": expected_token,
        "exchange": expected_exchange,
        "observed_symbols": symbols,
        "symbol_observed": bool(symbols),
    }
    feed = pd.to_numeric(data.ft, errors="coerce")
    invalid_feed = feed.isna() | ~np.isfinite(feed) | feed.mod(1).ne(0)
    if invalid_feed.any():
        fail("invalid feed epoch second", data.index[invalid_feed].tolist())
    event = pd.to_datetime(feed, unit="s", utc=True, errors="coerce")
    try:
        capture = pd.to_datetime(data.timestamp, format="mixed", errors="coerce")
        if capture.dt.tz is not None:
            fail("expected explicitly localized naive source capture timestamps")
        receipt = capture.dt.tz_localize(capture_timezone).dt.tz_convert("UTC")
    except (ValueError, TypeError, AttributeError) as error:
        fail(
            "capture timestamp cannot be interpreted with the declared timezone: "
            + type(error).__name__
        )
    bad_clock = event.isna() | receipt.isna()
    if bad_clock.any():
        fail("missing or out-of-range source clock", data.index[bad_clock].tolist())
    delay = (receipt - event).dt.total_seconds()
    report["receipt_minus_feed_seconds"] = {
        "min": float(delay.min()),
        "median": float(delay.median()),
        "max": float(delay.max()),
        "over_60_seconds": int(delay.gt(60).sum()),
        "negative": int(delay.lt(0).sum()),
    }
    invalid_order = delay.lt(-clock_tolerance_seconds)
    if invalid_order.any():
        fail(
            "feed event occurs after capture beyond declared clock tolerance",
            data.index[invalid_order].tolist(),
        )
    data["event_at"] = event
    data["receive_at"] = receipt
    sessions = event.dt.tz_convert(capture_timezone).dt.strftime("%Y-%m-%d")
    if expected_session is not None and sessions.ne(expected_session).any():
        fail(
            "feed clock falls outside the declared source session",
            data.index[sessions.ne(expected_session)].tolist(),
        )
    report["sessions"] = sorted(sessions.unique().tolist())
    supplied = data.lp.notna()
    prices = pd.to_numeric(data.lp, errors="coerce")
    invalid_price = supplied & (prices.isna() | ~np.isfinite(prices) | prices.le(0))
    if invalid_price.any():
        fail("invalid genuine index-price update", data.index[invalid_price].tolist())
    report["non_price_source_rows"] = data.index[~supplied].tolist()
    report["non_price_updates"] = int((~supplied).sum())
    data["price"] = prices
    ticks = data.loc[supplied].copy()
    if ticks.empty:
        fail("no genuine index-price updates")
    counts = ticks.groupby(["event_at", "receive_at"]).price.nunique()
    if counts.gt(1).any():
        bad_keys = counts[counts.gt(1)].index
        bad = pd.MultiIndex.from_frame(ticks[["event_at", "receive_at"]]).isin(bad_keys)
        fail(
            "conflicting prices share both source clocks; ordering is unknown",
            ticks.loc[bad, "source_row"].tolist(),
        )
    report["identical_clock_price_repeats"] = int(
        ticks.duplicated(["event_at", "receive_at", "price"]).sum()
    )
    report["source_feed_descending"] = bool(event.is_monotonic_decreasing)
    ticks = ticks.sort_values(["event_at", "receive_at", "source_row"], kind="stable")
    ticks["minute"] = ticks.event_at.dt.floor("min")
    rows = []
    for minute, group in ticks.groupby("minute", sort=True):
        bar_end = minute + pd.Timedelta(minutes=1)
        receive_at = group.receive_at.max()
        rows.append(
            {
                "event_at": minute,
                "receive_at": receive_at,
                "available_at": max(bar_end + pd.Timedelta(seconds=60), receive_at),
                "open": float(group.price.iloc[0]),
                "high": float(group.price.max()),
                "low": float(group.price.min()),
                "close": float(group.price.iloc[-1]),
                "instrument": instrument,
                "source_sha256": source_sha256,
                "source_row_ids": json.dumps(group.source_row.tolist(), separators=(",", ":")),
                "observed_updates": len(group),
            }
        )
    bars = pd.DataFrame(rows)
    missing: dict[str, list[str]] = {}
    for session in report["sessions"]:
        expected = pd.date_range(
            session + " 09:15:00", session + " 15:29:00", freq="min", tz=capture_timezone
        ).tz_convert("UTC")
        missing[session] = [stamp.isoformat() for stamp in expected.difference(bars.event_at)]
    local_clock = ticks.event_at.dt.tz_convert(capture_timezone).dt.strftime("%H:%M:%S")
    report.update(
        status="BUILT",
        price_updates=len(ticks),
        bars=len(bars),
        missing_regular_minutes=missing,
        outside_regular_price_updates=int(
            ((local_clock < "09:15:00") | (local_clock >= "15:30:00")).sum()
        ),
        source_row_order="ascending feed epoch, capture clock, then original zero-based row offset",
        qualification="NOT_PERFORMED; run unchanged laboratory qualification gates",
    )
    return bars, report


def read_spot_archive(source: Path, **kwargs: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read one immutable Parquet file, hashing before and after the read."""
    source = Path(source)
    if not source.is_file() or source.is_symlink():
        raise DataQualificationError("spot archive source must be a regular non-symlink file")
    before = sha256_file(source)
    frame = pd.read_parquet(source)
    if sha256_file(source) != before:
        raise DataQualificationError("spot archive changed during read")
    return spot_updates_to_minutes(frame, source_sha256=before, **kwargs)
