#!/usr/bin/env python3
"""Build a forecast_intraday_rv.py input from the office-Mac HF sampler evidence.

The read-only sampler (``node src/workflow-data-cli.mjs --scope hf`` in the
local dhan-chatgpt-mcp project, run directly on the office Mac, never through a
remote node) writes an evidence file whose ``hf_quotes`` map holds one list of
``{timestamp, bid, ask}`` quotes per index. This helper selects one symbol,
attaches the surface anchor, the normalized news packet and the decision clock,
and writes the exact input the forecaster expects.

Nothing here is a forecast. The output must still pass forecast_intraday_rv.py.

Usage:
    python scripts/build_rv_input.py \
        --hf-evidence /path/to/hf-evidence.json --symbol NIFTY \
        --spot 22714.45 --atm-iv 0.118 --atm-straddle 300.0 \
        --news-packet news.json --horizon-minutes 30 \
        [--surface-start surface_a.json --surface-end surface_b.json] \
        [--asof 2026-09-30T09:45:00+05:30] --output rv_input.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _quotes(evidence: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    quotes = (evidence.get("hf_quotes") or {}).get(symbol)
    if not isinstance(quotes, list):
        raise SystemExit(f"hf_quotes for {symbol} not found in evidence; scope={evidence.get('scope')}")
    out = []
    for q in quotes:
        if not isinstance(q, dict):
            continue
        bid, ask = q.get("bid"), q.get("ask")
        ts = q.get("timestamp")
        if ts and bid is not None and ask is not None:
            out.append({"timestamp": ts, "bid": float(bid), "ask": float(ask)})
    if not out:
        raise SystemExit(f"no usable bid/ask quotes for {symbol}")
    return out


def build(args: argparse.Namespace) -> Dict[str, Any]:
    evidence = _load(args.hf_evidence)
    if str(evidence.get("scope", "")).upper() != "HF":
        raise SystemExit("evidence scope is not HF; run the sampler with --scope hf")
    symbol = args.symbol.upper()
    quotes = _quotes(evidence, symbol)
    news = _load(args.news_packet) if args.news_packet else None
    surface = [s for s in (_load(p) for p in (args.surface_start, args.surface_end) if p) if isinstance(s, dict)]
    asof = args.asof or datetime.now(timezone.utc).isoformat()
    payload: Dict[str, Any] = {
        "symbol": symbol,
        "asof": asof,
        "horizon_minutes": args.horizon_minutes,
        "hf_quotes": quotes,
        "surface_snapshots": surface,
        "current": {"spot": args.spot, "atm_iv": args.atm_iv, "atm_straddle": args.atm_straddle,
                    "model_free_implied_vol": args.model_free_implied_vol},
        "news_filter": news,
        "provenance": {
            "hf_collection_id": evidence.get("collection_id"),
            "hf_started_at": evidence.get("started_at"),
            "hf_completed_at": evidence.get("completed_at"),
            "hf_failures": evidence.get("failures", []),
            "instrument": next((i for i in evidence.get("instruments", []) if i.get("symbol") == symbol), None),
        },
    }
    if news is None:
        payload.pop("news_filter")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hf-evidence", required=True)
    parser.add_argument("--symbol", required=True, choices=["NIFTY", "BANKNIFTY", "SENSEX", "nifty", "banknifty", "sensex"])
    parser.add_argument("--spot", type=float, required=True)
    parser.add_argument("--atm-iv", type=float, required=True, help="annualized decimal, e.g. 0.118")
    parser.add_argument("--atm-straddle", type=float, required=True)
    parser.add_argument("--model-free-implied-vol", type=float, default=None)
    parser.add_argument("--news-packet", default=None, help="normalized market-news-signal-filter packet JSON")
    parser.add_argument("--surface-start", default=None)
    parser.add_argument("--surface-end", default=None)
    parser.add_argument("--horizon-minutes", type=float, default=30.0)
    parser.add_argument("--asof", default=None, help="decision clock, offset-aware ISO 8601; default now")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = build(args)
    Path(args.output).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(json.dumps({"written": args.output, "symbol": payload["symbol"], "hf_quotes": len(payload["hf_quotes"]),
                      "surface_snapshots": len(payload["surface_snapshots"]),
                      "news_packet": "PRESENT" if "news_filter" in payload else "MISSING", "asof": payload["asof"]}))


if __name__ == "__main__":
    main()
