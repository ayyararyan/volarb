#!/usr/bin/env python3
"""Generate self-contained RV regression data; no feeds or historical input.

All prices, IVs, news labels and surfaces are invented. Sine waves provide
small deterministic fluctuations; a linear ramp and one transient step create the
trend and jump cases. Dates are arbitrary test clocks, not exchange sessions.
"""
import argparse
from datetime import datetime, timedelta
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
START = datetime.fromisoformat("2020-01-02T10:00:00+05:30")


def scenario(name):
    quotes = []
    for index in range(151):
        mid = 50000 + 5 * math.sin(index / 4) + 2 * math.sin(index / 7)
        if name == "trend":
            mid += 2 * index
        elif name == "jump" and 75 <= index < 80:
            mid += 50
        quotes.append({"timestamp": (START + timedelta(seconds=2 * index)).isoformat(),
                       "bid": round(mid - 0.5, 2), "ask": round(mid + 0.5, 2)})
    straddle = 160 if name == "mode_bucket_jump" else 250
    first = {"timestamp": START.isoformat(), "forward": 50002, "futures": 50000,
             "atm_straddle": straddle, "rnd_median": 50000, "rnd_mode": 50000}
    last = {**first, "timestamp": (START + timedelta(minutes=5)).isoformat(),
            "forward": 50005, "futures": 50003}
    if name == "trend":
        last.update(forward=50300, futures=50302, rnd_median=50300, rnd_mode=50300)
    elif name == "jump":
        last.update(forward=50008, futures=50006)
    elif name == "mode_bucket_jump":
        last["rnd_mode"] = 50100
    return {
        "provenance": {"kind": "synthetic", "generator": "generate_synthetic_fixtures.py",
                       "scenario": name, "observed_market_data": False},
        "asof": (START + timedelta(minutes=5, seconds=5)).isoformat(),
        "symbol": "BANKNIFTY", "horizon_minutes": 30, "hf_quotes": quotes,
        "surface_snapshots": [first, last],
        "current": {"spot": round((quotes[-1]["bid"] + quotes[-1]["ask"]) / 2, 2),
                    "atm_iv": 0.25 if name == "jump" else 0.22,
                    "atm_straddle": straddle},
        "news_filter": {"aggregate_state": "NOISY_BUT_BENIGN",
                        "max_butterfly_relevance": "watch", "max_latency_severity": "low"},
        "config": {"bucket_seconds": 5, "observation_minutes": 5,
                   "fast_window_seconds": 90, "jump_threshold_sigma": 4.0,
                   "jump_decay_minutes": 30},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()
    for name in ("stable", "trend", "jump", "mode_bucket_jump"):
        path = ROOT / f"test_{name}.json"
        content = json.dumps(scenario(name), indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Synthetic fixture differs from generator: {path.name}")
        else:
            path.write_text(content)
    print("Four synthetic fixtures verified" if args.check else "Four synthetic fixtures written")


if __name__ == "__main__":
    main()
