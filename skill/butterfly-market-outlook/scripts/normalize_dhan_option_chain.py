#!/usr/bin/env python3
"""Normalize DhanHQ option-chain JSON for the butterfly surface analyzer.

Accepts either the raw Dhan /optionchain response or the extra {"data": ...}
wrapper returned by the Dhan MCP tools. Output matches the normalized schema used
by analyze_option_surface.py and optimize_butterflies.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except (TypeError, ValueError):
        return default


def normalize_iv(value: Any) -> Optional[float]:
    v = num(value)
    if v is None or v <= 0:
        return None
    return v / 100.0 if v > 2.0 else v


def unwrap(payload: Any) -> Dict[str, Any]:
    cur = payload
    for _ in range(5):
        if isinstance(cur, dict) and "oc" in cur and "last_price" in cur:
            return cur
        if isinstance(cur, dict) and isinstance(cur.get("data"), dict):
            cur = cur["data"]
            continue
        break
    raise ValueError("Could not find Dhan option-chain payload (expected last_price + oc)")


def side(raw: Dict[str, Any]) -> Dict[str, Any]:
    oi = int(num(raw.get("oi"), 0) or 0)
    previous_oi = int(num(raw.get("previous_oi"), 0) or 0)
    greeks = raw.get("greeks") or {}
    return {
        "security_id": int(num(raw.get("security_id"), 0) or 0),
        "ltp": num(raw.get("last_price")),
        "bid": num(raw.get("top_bid_price")),
        "ask": num(raw.get("top_ask_price")),
        "bid_qty": int(num(raw.get("top_bid_quantity"), 0) or 0),
        "ask_qty": int(num(raw.get("top_ask_quantity"), 0) or 0),
        "iv": normalize_iv(raw.get("implied_volatility")),
        "oi": oi,
        "previous_oi": previous_oi,
        "change_oi": oi - previous_oi,
        "volume": int(num(raw.get("volume"), 0) or 0),
        "previous_volume": int(num(raw.get("previous_volume"), 0) or 0),
        "average_price": num(raw.get("average_price")),
        "greeks": {
            "delta": num(greeks.get("delta")),
            "theta": num(greeks.get("theta")),
            "gamma": num(greeks.get("gamma")),
            "vega": num(greeks.get("vega")),
        },
    }


def pick_mid(s: Dict[str, Any]) -> Optional[float]:
    bid, ask = num(s.get("bid")), num(s.get("ask"))
    if bid is not None and ask is not None and bid > 0 and ask >= bid:
        return 0.5 * (bid + ask)
    ltp = num(s.get("ltp"))
    return ltp if ltp is not None and ltp > 0 else None


def weighted_median(values: Iterable[tuple[float, float]]) -> Optional[float]:
    rows = sorted((v, w) for v, w in values if math.isfinite(v) and math.isfinite(w) and w > 0)
    if not rows:
        return None
    total = sum(w for _, w in rows)
    acc = 0.0
    for value, weight in rows:
        acc += weight
        if acc >= total / 2.0:
            return value
    return rows[-1][0]


def estimate_forward(chain: list[Dict[str, Any]], spot: float) -> float:
    estimates = []
    for row in chain:
        strike = float(row["strike"])
        if abs(strike / spot - 1.0) > 0.04:
            continue
        c, p = pick_mid(row["call"]), pick_mid(row["put"])
        if c is None or p is None:
            continue
        # Near-expiry index options: discounting over a few days is tiny. The
        # downstream analyzer may apply its explicit rate/DF if provided.
        fwd = strike + c - p
        oi = float(row["call"].get("oi", 0)) + float(row["put"].get("oi", 0))
        volume = float(row["call"].get("volume", 0)) + float(row["put"].get("volume", 0))
        weight = max(1.0, math.log1p(oi) + math.log1p(volume))
        estimates.append((fwd, weight))
    return weighted_median(estimates) or spot


def normalize(payload: Dict[str, Any], symbol: str, expiry: str, retrieved_at: Optional[str] = None) -> Dict[str, Any]:
    raw = unwrap(payload)
    spot = float(raw["last_price"])
    chain = []
    for strike_text, row in (raw.get("oc") or {}).items():
        strike = num(strike_text)
        if strike is None:
            continue
        chain.append({
            "strike": strike,
            "call": side((row or {}).get("ce") or {}),
            "put": side((row or {}).get("pe") or {}),
        })
    chain.sort(key=lambda r: float(r["strike"]))
    if not chain:
        raise ValueError("Dhan option chain contained no strikes")
    retrieved_at = retrieved_at or dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "provider": "DhanHQ",
        "symbol": symbol.upper(),
        "expiry": expiry,
        "underlying_value": spot,
        "spot": spot,
        "forward": estimate_forward(chain, spot),
        "retrieved_at_utc": retrieved_at,
        "asof": retrieved_at,
        "chain": chain,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Normalize a DhanHQ option-chain response")
    ap.add_argument("--input", required=True, help="JSON file containing Dhan option-chain response")
    ap.add_argument("--symbol", required=True, help="NIFTY, BANKNIFTY or SENSEX")
    ap.add_argument("--expiry", required=True, help="Expiry YYYY-MM-DD")
    ap.add_argument("--output")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    payload = json.loads(Path(args.input).read_text())
    result = normalize(payload, args.symbol, args.expiry)
    text = json.dumps(result, indent=2 if args.pretty else None, sort_keys=False)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
