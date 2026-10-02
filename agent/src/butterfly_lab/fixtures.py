"""Deterministic safe fixtures, always labelled synthetic rather than historical."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import sha256_file


def generate_spot_fixture(path: Path) -> dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(811)
    dates = (
        list(pd.bdate_range("2023-09-01", periods=60))
        + list(pd.bdate_range("2024-02-01", periods=35))
        + list(pd.bdate_range("2025-02-01", periods=40))
    )
    rows = []
    for day in dates:
        level = 20000.0
        drift = rng.normal(0, 0.000035)
        scale = rng.uniform(0.00008, 0.0003)
        for timestamp in pd.date_range(
            day.strftime("%Y-%m-%d") + " 09:15", periods=81, freq="min", tz="Asia/Kolkata"
        ):
            change = rng.normal(drift, scale)
            previous = level
            level *= math.exp(change)
            rows.append(
                {
                    "datetime": timestamp.isoformat(),
                    "open": previous,
                    "high": max(level, previous),
                    "low": min(level, previous),
                    "close": level,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)
    return {
        "id": "synthetic-spot-v1",
        "kind": "spot_bars",
        "source_path": str(path.resolve()),
        "source_sha256": sha256_file(path),
        "fidelity": "F0",
        "provenance": "SYNTHETIC",
        "capabilities": ["spot_bars", "spot_excursion", "past_only_rv", "past_only_drift"],
        "bar_label": "start",
        "availability_lag_seconds": 60,
        "partition": "development",
        "prior_exposed": True,
        "timestamp_convention_verified": True,
        "session_dates": [d.strftime("%Y-%m-%d") for d in dates],
        "metadata": {
            "bar_seconds": 60,
            "sessions": {
                d.strftime("%Y-%m-%d"): {"open": "09:15:00", "close": "15:30:00"} for d in dates
            },
            "fixture_seed": 811,
        },
    }


def generate_option_fixture(path: Path, sessions: int = 40) -> dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    dates = list(pd.bdate_range("2025-01-02", periods=sessions))
    for day_index, day in enumerate(dates):
        session = day.strftime("%Y-%m-%d")
        for minute, timestamp in enumerate(
            pd.date_range(session + " 10:00", periods=32, freq="min", tz="Asia/Kolkata")
        ):
            spot = 10000.0 + (500.0 if minute >= 15 else 0.0)
            for strike in [9000, 9500, 10000, 10500, 11000, 11500]:
                for option_type in ["CE", "PE"]:
                    intrinsic = max(spot - strike if option_type == "CE" else strike - spot, 0)
                    time_value = (
                        max(1, 100 - 0.1 * abs(strike - spot)) * (1 - minute / 100)
                        + day_index * 0.001
                    )
                    mark = intrinsic + time_value
                    rows.append(
                        {
                            "event_at": timestamp.isoformat(),
                            "receive_at": timestamp.isoformat(),
                            "available_at": timestamp.isoformat(),
                            "contract_id": f"FIXTURE:NIFTY:2025-12-30:{strike}:{option_type}",
                            "underlying": "NIFTY",
                            "expiry": "2025-12-30",
                            "strike": strike,
                            "option_type": option_type,
                            "lot_size": 10,
                            "spot": spot,
                            "bid": max(0.001, mark - 0.25),
                            "ask": mark + 0.25,
                            "bid_size": 100,
                            "ask_size": 100,
                        }
                    )
    pd.DataFrame(rows).to_parquet(path, index=False)
    fees = [
        {
            "effective_from": "2020-01-01",
            "effective_to": "2030-12-31",
            "brokerage_per_fill": 1.0,
            "exchange_rate": 0.0,
            "regulatory_rate": 0.0,
            "gst_rate": 0.0,
            "sell_tax_rate": 0.0,
            "buy_stamp_rate": 0.0,
            "source": "deliberately simplified synthetic fixture fees, not historical Indian charges",
        }
    ]
    return {
        "id": "synthetic-fourleg-v1",
        "kind": "option_quotes",
        "source_path": str(path.resolve()),
        "source_sha256": sha256_file(path),
        "fidelity": "F0",
        "provenance": "SYNTHETIC",
        "capabilities": [
            "identified_contracts",
            "dated_lot_units",
            "two_sided_quotes",
            "displayed_size",
        ],
        "bar_label": "event",
        "availability_lag_seconds": 0,
        "timestamp_convention_verified": True,
        "prior_exposed": True,
        "session_dates": [d.strftime("%Y-%m-%d") for d in dates],
        "metadata": {
            "fee_schedule": fees,
            "contract_specs": [
                {
                    "underlying": "NIFTY",
                    "effective_from": "2020-01-01",
                    "effective_to": "2030-12-31",
                    "lot_size": 10,
                }
            ],
            "sessions": {
                d.strftime("%Y-%m-%d"): {"open": "09:15:00", "close": "15:30:00"} for d in dates
            },
        },
    }


def default_ironfly_parameters() -> dict[str, Any]:
    return {
        "management": "recenter",
        "management_after_minutes": 15,
        "entry_time": "10:00:00",
        "hold_minutes": 30,
        "width_floor": 500,
        "lots": 1,
        "capital_inr": 1000000,
        "margin_per_cycle_inr": 10000,
        "margin_basis": "explicit synthetic fixed capital proxy, not expiry maximum loss",
        "latency_seconds": 0,
        "leg_spacing_seconds": 0,
        "max_quote_age_seconds": 60,
        "max_chain_skew_seconds": 2,
        "max_fill_wait_seconds": 60,
    }
