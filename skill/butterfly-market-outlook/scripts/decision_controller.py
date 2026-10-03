#!/usr/bin/env python3
"""Deterministic precedence controller for the butterfly skill.

This script does not calculate market metrics. It consumes normalized gate
outputs produced by the other workflow modules and enforces the canonical
"first terminal gate wins" policy.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


SEVERE_NEW_OVERNIGHT_REGIMES = {"LATENT_JUMP_RISK", "ACTIVE_STRESS", "UNKNOWN"}


def _status(data: Dict[str, Any], key: str, default: str = "PASS") -> str:
    value = data.get(key, default)
    return str(value).upper()


def margin_pass(packet: Dict[str, Any], scope: str = "ENTRY_ONLY") -> bool:
    """Accept a fresh, complete MCP entry preflight, never a bare status flag."""
    try:
        if packet.get("status") != "PASS" or packet.get("scope") != scope or packet.get("blockers") != []:
            return False
        now = datetime.now(timezone.utc)
        asof = datetime.fromisoformat(packet["asof"].replace("Z", "+00:00"))
        until = datetime.fromisoformat(packet["validUntil"].replace("Z", "+00:00"))
        if not (0 <= (now - asof).total_seconds() <= 30 and now <= until
                and 0 < (until - asof).total_seconds() <= 30):
            return False
        names = ("availableFundsRupees", "peakRequiredRupees", "reserveRupees", "headroomAfterReserveRupees")
        values = [packet[n] for n in names]
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in values):
            return False
        available, peak, reserve, headroom = values
        return peak > 0 and reserve >= 0 and headroom >= 0 and abs(available - peak - reserve - headroom) < 0.01
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _rupees(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v >= 0 else None


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

    # Owner daily loss budget. Loss is positive rupees; realized plus bankable
    # (executable-close) P&L for the current session. Missing evidence is a
    # warning in this normalized controller, including candidate mode. Callers
    # must supply/validate both inputs before proposing a new structure; this
    # warning is not evidence that the operational entry requirement passed.
    budget = _rupees(data.get("daily_loss_budget_rupees"))
    session_loss = _rupees(data.get("session_loss_rupees"))
    if budget is not None and session_loss is not None and session_loss >= budget:
        action = "NO_TRADE" if mode == "CANDIDATE" else "SQUARE_OFF"
        return _result(action, "LOSS_BUDGET", warnings)
    if budget is None or session_loss is None:
        warnings.append("loss budget not evaluated: supply daily_loss_budget_rupees and session_loss_rupees")

    if mode == "CANDIDATE":
        # Session-level variance risk premium. A new butterfly exists to harvest
        # VRP; without evidence of a premium there is nothing to harvest.
        vrp_state = str(data.get("session_vrp_state", "UNKNOWN")).upper()
        if vrp_state != "FAVOURABLE":
            return _result("NO_TRADE", "SESSION_VRP", warnings)
        if bool(data.get("re_entry_after_square_off", False)) and not bool(data.get("fresh_candidate_pass", False)):
            return _result("NO_TRADE", "RE_ENTRY_REQUIRES_FRESH_PASS", warnings)

    if branch in {"OPEN_INTRADAY", "CANDIDATE_INTRADAY"}:
        rv_state = str(data.get("intraday_rv_state", "INSUFFICIENT_DATA")).upper()
        rv_conf = str(data.get("intraday_rv_confidence", "low")).lower()
        if mode == "CANDIDATE" and rv_state != "FAVOURABLE":
            return _result("NO_TRADE", "INTRADAY_RV_DRIFT", warnings)
        if mode == "OPEN_POSITION" and rv_state == "UNFAVOURABLE" and rv_conf in {"medium", "high"}:
            return _result("SQUARE_OFF", "INTRADAY_RV_DRIFT", warnings)
        if rv_state == "MARGINAL":
            warnings.append("intraday_rv_state=MARGINAL; shorten next review")
        elif rv_state in {"INSUFFICIENT_DATA", "UNKNOWN"}:
            warnings.append("intraday_rv_state=INSUFFICIENT_DATA; do not interpret missing HF data as benign")

    crosses_close = branch in {"OPEN_CARRY_GATE", "CANDIDATE_OVERNIGHT"}
    if crosses_close:
        regime = str(data.get("market_regime", "UNKNOWN")).upper()
        proposed_new = bool(data.get("proposed_new_structure", mode == "CANDIDATE"))
        news_required = bool(data.get("news_filter_required", False))
        news_status = str(data.get("news_filter_status", "CURRENT" if not news_required else "UNAVAILABLE")).upper()
        if news_required and proposed_new and news_status in {"UNAVAILABLE", "INVALID"}:
            action = "NO_TRADE" if mode == "CANDIDATE" else "SQUARE_OFF"
            return _result(action, "NEWS_FILTER", warnings)
        if news_status == "STALE_CALIBRATION":
            warnings.append("news_filter=STALE_CALIBRATION; use live cross-asset confirmation and lower confidence")

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
            # ENTRY_ONLY checks cannot authorize an overlapping close/reopen path.
            # Reconcile closure first, then run a fresh candidate entry check.
            if margin_pass(data.get("recenter_margin_check", {}), scope="RECENTRE"):
                return _result("RECENTRE", "RECENTER", warnings)
            warnings.append("recenter blocked: entry-only margin preflight does not verify close/reopen sequence; reassess exit independently")

        if branch == "OPEN_CARRY_GATE":
            return _result("CARRY", "DEFAULT", warnings)
        return _result("HOLD", "DEFAULT", warnings)

    candidate_count = int(data.get("candidate_count", 0) or 0)
    if candidate_count <= 0:
        return _result("NO_TRADE", "OPTIMIZER", warnings)
    checks = data.get("candidate_margin_checks", {})
    candidate_ids = data.get("candidate_ids", [])
    specs = data.get("candidate_specs", {})
    eligible = [cid for cid in candidate_ids if isinstance(cid, str) and isinstance(checks, dict)
                and isinstance(checks.get(cid), dict) and isinstance(specs, dict)
                and isinstance(specs.get(cid), dict) and set(specs[cid]) == {"symbol", "expiry", "lower", "center", "upper", "lots"}
                and specs[cid] == checks[cid].get("candidate") and margin_pass(checks[cid])]
    if not eligible:
        return _result("NO_TRADE", "MARGIN_AFFORDABILITY", warnings)
    result = _result("CANDIDATES", "OPTIMIZER", warnings)
    result["margin_eligible_candidate_ids"] = list(dict.fromkeys(eligible))
    return result


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
