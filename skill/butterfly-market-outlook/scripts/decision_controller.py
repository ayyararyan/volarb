#!/usr/bin/env python3
"""Deterministic precedence controller for the butterfly skill.

This script does not calculate market metrics. It consumes normalized gate
outputs produced by the other workflow modules and enforces the canonical
"first terminal gate wins" policy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


SEVERE_NEW_OVERNIGHT_REGIMES = {"LATENT_JUMP_RISK", "ACTIVE_STRESS", "UNKNOWN"}


def _status(data: Dict[str, Any], key: str, default: str = "PASS") -> str:
    value = data.get(key, default)
    return str(value).upper()


def decide(data: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(data.get("mode", "")).upper()
    branch = str(data.get("branch", "")).upper()
    warnings: List[str] = []

    if mode not in {"OPEN_POSITION", "CANDIDATE"}:
        raise ValueError("mode must be OPEN_POSITION or CANDIDATE")

    allowed_branches = {
        "OPEN_INTRADAY",
        "OPEN_CARRY_GATE",
        "LOCKED_OVERNIGHT",
        "CANDIDATE_INTRADAY",
        "CANDIDATE_OVERNIGHT",
    }
    if branch not in allowed_branches:
        raise ValueError(f"branch must be one of {sorted(allowed_branches)}")

    if mode == "CANDIDATE":
        data_health = str(data.get("data_health", "UNKNOWN")).upper()
        if data_health in {"INVALID", "STALE"}:
            return _result("NO_TRADE", "DATA_HEALTH", warnings)

    if branch == "LOCKED_OVERNIGHT":
        return _result("LOCKED_OVERNIGHT", "POST_CLOSE", warnings)

    crosses_close = branch in {"OPEN_CARRY_GATE", "CANDIDATE_OVERNIGHT"}
    if crosses_close:
        regime = str(data.get("market_regime", "UNKNOWN")).upper()
        proposed_new = bool(data.get("proposed_new_structure", mode == "CANDIDATE"))

        if proposed_new and regime in SEVERE_NEW_OVERNIGHT_REGIMES:
            action = "NO_TRADE" if mode == "CANDIDATE" else "SQUARE_OFF"
            return _result(action, "MARKET_REGIME", warnings)

        if regime in {"TRANSITION", "LATENT_JUMP_RISK", "ACTIVE_STRESS", "UNKNOWN"}:
            warnings.append(f"regime={regime}; use regime-adjusted overnight thresholds")

        gap = _status(data, "recent_gap_gate", "UNKNOWN")
        if mode == "CANDIDATE" and gap in {"BLOCK", "FAIL", "UNKNOWN"}:
            return _result("NO_TRADE", "RECENT_GAP", warnings)
        if mode == "OPEN_POSITION" and gap in {"BLOCK", "FAIL"}:
            return _result("SQUARE_OFF", "RECENT_GAP", warnings)
        if gap in {"WARN", "UNKNOWN"}:
            warnings.append(f"recent_gap_gate={gap}")

        broker = _status(data, "broker_rms_gate", "UNKNOWN")
        if mode == "CANDIDATE" and broker != "PASS":
            return _result("NO_TRADE", "BROKER_RMS", warnings)
        if mode == "OPEN_POSITION" and broker in {"BLOCK", "FAIL", "WARN"}:
            return _result("SQUARE_OFF", "BROKER_RMS", warnings)
        if broker == "UNKNOWN":
            warnings.append("broker_rms_gate=UNKNOWN")

        event = _status(data, "event_latency_gate", "PASS")
        if event in {"BLOCK", "FAIL"}:
            action = "NO_TRADE" if mode == "CANDIDATE" else "SQUARE_OFF"
            return _result(action, "EVENT_LATENCY", warnings)
        if event in {"WARN", "UNKNOWN"}:
            warnings.append(f"event_latency_gate={event}")

        stress = _status(data, "joint_stress_gate", "PASS")
        if mode == "CANDIDATE" and stress in {"BLOCK", "FAIL", "UNKNOWN"}:
            return _result("NO_TRADE", "JOINT_GAP_IV_STRESS", warnings)
        if mode == "OPEN_POSITION" and stress in {"BLOCK", "FAIL"}:
            return _result("SQUARE_OFF", "JOINT_GAP_IV_STRESS", warnings)
        if stress in {"WARN", "UNKNOWN"}:
            warnings.append(f"joint_stress_gate={stress}")

    hard_risk = _status(data, "hard_risk_gate", "PASS")
    if hard_risk in {"BLOCK", "FAIL"}:
        action = "NO_TRADE" if mode == "CANDIDATE" else "SQUARE_OFF"
        return _result(action, "HARD_EVENT_TAIL_LIQUIDITY", warnings)

    if mode == "OPEN_POSITION":
        expiry_gate = _status(data, "expiry_exit_gate", "PASS")
        if expiry_gate in {"BLOCK", "FAIL", "EXIT"}:
            return _result("SQUARE_OFF", "EXPIRY_EXIT", warnings)

        recenter = _status(data, "recenter_gate", "NOT_APPLICABLE")
        if recenter == "PASS":
            return _result("RECENTRE", "RECENTER", warnings)

        if branch == "OPEN_CARRY_GATE":
            return _result("CARRY", "DEFAULT", warnings)
        return _result("HOLD", "DEFAULT", warnings)

    candidate_count = int(data.get("candidate_count", 0) or 0)
    if candidate_count <= 0:
        return _result("NO_TRADE", "OPTIMIZER", warnings)
    return _result("CANDIDATES", "OPTIMIZER", warnings)


def _result(action: str, terminal_gate: str, warnings: List[str]) -> Dict[str, Any]:
    return {
        "action": action,
        "terminal_gate": terminal_gate,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to controller JSON")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = decide(data)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
