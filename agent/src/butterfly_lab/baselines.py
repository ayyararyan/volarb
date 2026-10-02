"""Separate observed-source replay, intended policy, and deliberately simple control."""

from __future__ import annotations

from typing import Any
from datetime import datetime
from threading import Lock

import pandas as pd
from . import observed_controller_v26

from .accounting import Contract, validate_iron_butterfly


BASELINE_VERSION = "1.0.0"
_CLOCK_LOCK = Lock()
BASELINES = {
    "B0-simple": {
        "description": "New one-lot research control, not the live strategy",
        "hold_minutes": 30,
        "deadline": "15:00",
        "recenter": False,
    },
    "B-policy": {
        "description": "Explicit research interpretation of intended first-terminal policy",
        "deadline": "15:00",
        "loss_budget_inr": 1000.0,
        "reserve_inr": 1000.0,
    },
    "B-as-observed": {
        "description": "Frozen source/input/output decision replay, including integration omissions",
        "requires": ["source_sha256", "input_sha256", "observed_action"],
    },
}


def policy_decision(packet: dict[str, Any], baseline_id: str = "B-policy") -> dict[str, str]:
    if baseline_id not in BASELINES:
        raise ValueError("unknown baseline")
    if baseline_id == "B-as-observed":
        if "controller_input" not in packet:
            return {"action": "BLOCKED", "reason": "observed_controller_input_unavailable"}
        return observed_decision(packet["controller_input"], packet["decision_at"])
    timestamp = pd.Timestamp(packet["decision_at"])
    if timestamp.tzinfo is None:
        raise ValueError("timezone required")
    clock = timestamp.tz_convert("Asia/Kolkata").strftime("%H:%M")
    held = bool(packet.get("held"))
    if clock >= "15:00":
        return {"action": "CLOSE" if held else "NO_TRADE", "reason": "intraday_deadline"}
    if baseline_id == "B0-simple":
        return {"action": "HOLD" if held else "ENTRY", "reason": "simple_control"}

    # Explicit intended-policy reconstruction; unlike the observed source,
    # missing required evidence blocks. Gate precedence follows v2.6.
    def gate(name):
        value = packet.get(name)
        if value not in {"PASS", "MARGINAL", "FAIL"}:
            return {"action": "BLOCKED", "reason": name + "_unavailable"}
        if value == "FAIL":
            return {"action": "CLOSE" if held else "NO_TRADE", "reason": name}
        return None

    failed = gate("data_health")
    if failed:
        return failed
    if packet.get("crosses_close", False):
        return {"action": "CLOSE" if held else "NO_TRADE", "reason": "intraday_only"}
    if packet.get("loss_inr") is None:
        return {"action": "BLOCKED", "reason": "loss_evidence_unavailable"}
    if float(packet["loss_inr"]) >= 1000:
        return {"action": "CLOSE" if held else "NO_TRADE", "reason": "loss_budget"}
    if not held:
        failed = gate("session_vrp")
        if failed:
            return failed
        if packet["session_vrp"] != "PASS":
            return {"action": "NO_TRADE", "reason": "session_vrp"}
        if packet.get("re_entry", False) and not packet.get("fresh_full_pass", False):
            return {"action": "NO_TRADE", "reason": "reentry_requires_fresh_pass"}
    for name in ("intraday_rv", "drift", "event_tail", "liquidity", "expiry"):
        failed = gate(name)
        if failed:
            return failed
        if not held and packet[name] == "MARGINAL" and name in {"intraday_rv", "drift"}:
            return {"action": "NO_TRADE", "reason": name}
    if held:
        if packet.get("recenter_requested", False):
            if packet.get("recenter_margin_scope") != "RECENTRE" or not packet.get(
                "recenter_margin_verified", False
            ):
                return {"action": "HOLD", "reason": "recenter_transition_margin_unverified"}
            return {"action": "RECENTER", "reason": "recenter_verified_transition"}
        return {"action": "HOLD", "reason": "all_research_policy_gates_pass"}
    if packet.get("candidate_count") is None:
        return {"action": "BLOCKED", "reason": "optimizer_evidence_unavailable"}
    if int(packet["candidate_count"]) <= 0:
        return {"action": "NO_TRADE", "reason": "optimizer"}
    if packet.get("peak_entry_margin_inr") is None or packet.get("free_cash_inr") is None:
        return {"action": "BLOCKED", "reason": "margin_unavailable"}
    if float(packet["free_cash_inr"]) < float(packet["peak_entry_margin_inr"]) + 1000:
        return {"action": "NO_TRADE", "reason": "cash_reserve"}
    return {"action": "ENTRY", "reason": "all_research_policy_gates_pass"}


def observed_decision(controller_input: dict[str, Any], decision_at: str) -> dict[str, Any]:
    """Execute byte-identical observed controller with its clock explicitly frozen.

    Clock injection is the only runtime substitution. Actual gate ordering,
    defaults and known missing-loss permissiveness remain unchanged.
    """
    instant = datetime.fromisoformat(decision_at)
    if instant.tzinfo is None:
        raise ValueError("observed baseline requires offset-aware decision clock")

    class FrozenClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)

    with _CLOCK_LOCK:
        original = observed_controller_v26.datetime
        try:
            observed_controller_v26.datetime = FrozenClock
            return observed_controller_v26.decide(controller_input)
        finally:
            observed_controller_v26.datetime = original


def select_b0(
    chain: pd.DataFrame,
    *,
    spot: float,
    session: str,
    width_floor: float = 500,
    lots: int = 1,
    expiry: str | None = None,
) -> list[tuple[Contract, int]]:
    if lots <= 0 or int(lots) != lots or width_floor <= 0:
        raise ValueError("positive integer lots and wide floor required")
    valid = chain[chain.expiry >= session]
    if valid.empty:
        raise ValueError("no eligible expiry")
    chosen_expiry = expiry or sorted(valid.expiry.unique())[0]
    valid = valid[valid.expiry == chosen_expiry]
    call_strikes = set(valid.loc[valid.option_type.eq("CE"), "strike"])
    put_strikes = set(valid.loc[valid.option_type.eq("PE"), "strike"])
    bodies = call_strikes & put_strikes
    if not bodies:
        raise ValueError("no same-strike call/put body")
    body = min(bodies, key=lambda k: (abs(k - spot), k))
    lower = [x for x in put_strikes if x <= body - width_floor]
    upper = [x for x in call_strikes if x >= body + width_floor]
    if not lower or not upper:
        raise ValueError("wide protective wings unavailable")
    common_widths = {body - k for k in lower} & {k - body for k in upper}
    if not common_widths:
        raise ValueError("symmetric protective wings unavailable on the observed strike grid")
    width = min(common_widths)
    choices = [("PE", body - width, 1), ("PE", body, -1), ("CE", body, -1), ("CE", body + width, 1)]
    legs = []
    for typ, strike, sign in choices:
        row = valid[valid.option_type.eq(typ) & valid.strike.eq(strike)]
        if len(row) != 1:
            raise ValueError("ambiguous contract identity at selected strike")
        r = row.iloc[0]
        contract = Contract(
            str(r.contract_id),
            str(r.underlying),
            str(r.expiry),
            float(r.strike),
            str(r.option_type),
            int(r.lot_size),
        )
        legs.append((contract, sign * int(lots) * contract.lot_size))
    validate_iron_butterfly(legs)
    return legs


def recorded_selection(packet: dict[str, Any], key: str, decision_at) -> dict[str, Any]:
    """Require point-in-time selected legs; never substitute B0 for an observed policy."""
    selection = packet.get(key)
    if not isinstance(selection, dict) or not selection.get("selection_policy_id"):
        raise ValueError("recorded " + key + " and selection_policy_id required")
    instant = pd.Timestamp(selection.get("available_at"))
    if pd.isna(instant) or instant.tzinfo is None or instant > pd.Timestamp(decision_at):
        raise ValueError("recorded selection unavailable at decision timestamp")
    legs = selection.get("legs", [])
    if len(legs) != 4 or len({x.get("contract_id") for x in legs}) != 4:
        raise ValueError("four recorded fixed-contract legs required")
    if any(type(x.get("signed_lots")) is not int or abs(x["signed_lots"]) != 1 for x in legs):
        raise ValueError("recorded selection requires exactly one signed lot per leg")
    return selection


def select_recorded(chain: pd.DataFrame, selection: dict[str, Any]) -> list[tuple[Contract, int]]:
    legs = []
    for value in selection["legs"]:
        rows = chain[chain.contract_id.eq(value["contract_id"])]
        if len(rows) != 1:
            raise ValueError("recorded selected contract unavailable or ambiguous")
        row = rows.iloc[0]
        contract = Contract(
            str(row.contract_id),
            str(row.underlying),
            str(row.expiry),
            float(row.strike),
            str(row.option_type),
            int(row.lot_size),
        )
        legs.append((contract, value["signed_lots"] * contract.lot_size))
    validate_iron_butterfly(legs)
    return legs


def certify_baseline(baseline_id: str, fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    if baseline_id not in BASELINES or not fixtures:
        return {"status": "FAIL", "reason": "known baseline and golden cases required"}
    results = []
    for fixture in fixtures:
        actual = policy_decision(fixture["packet"], baseline_id)
        results.append(
            {
                "name": fixture["name"],
                "passed": actual["action"] == fixture["expected_action"],
                "actual": actual,
            }
        )
    return {
        "status": "PASS" if all(r["passed"] for r in results) else "FAIL",
        "baseline_id": baseline_id,
        "version": BASELINE_VERSION,
        "checks": results,
    }


def baseline_golden_cases(baseline_id: str) -> list[dict[str, Any]]:
    if baseline_id == "B-as-observed":
        return [
            {
                "name": "observed_missing_loss_warns_not_blocks",
                "packet": {
                    "decision_at": "2026-09-30T10:00:00+05:30",
                    "controller_input": {
                        "mode": "OPEN_POSITION",
                        "branch": "OPEN_INTRADAY",
                        "intraday_rv_state": "FAVOURABLE",
                        "intraday_rv_confidence": "high",
                    },
                },
                "expected_action": "HOLD",
            },
            {
                "name": "observed_vrp_before_hard_risk",
                "packet": {
                    "decision_at": "2026-09-30T10:00:00+05:30",
                    "controller_input": {
                        "mode": "CANDIDATE",
                        "branch": "CANDIDATE_INTRADAY",
                        "hard_risk_gate": "FAIL",
                    },
                },
                "expected_action": "NO_TRADE",
            },
        ]
    if baseline_id == "B0-simple":
        return [
            {
                "name": "new_simple_entry",
                "packet": {"decision_at": "2026-09-30T10:00:00+05:30", "held": False},
                "expected_action": "ENTRY",
            },
            {
                "name": "flat_deadline",
                "packet": {"decision_at": "2026-09-30T15:00:00+05:30", "held": False},
                "expected_action": "NO_TRADE",
            },
            {
                "name": "held_deadline",
                "packet": {"decision_at": "2026-09-30T15:00:00+05:30", "held": True},
                "expected_action": "CLOSE",
            },
        ]
    if baseline_id == "B-policy":
        base = {
            "decision_at": "2026-09-30T10:00:00+05:30",
            "loss_inr": 0,
            "candidate_count": 1,
            **{
                gate: "PASS"
                for gate in [
                    "data_health",
                    "event_tail",
                    "liquidity",
                    "expiry",
                    "session_vrp",
                    "intraday_rv",
                    "drift",
                ]
            },
        }
        return [
            {
                "name": "policy_missing_loss_blocked",
                "packet": {**base, "held": True, "loss_inr": None},
                "expected_action": "BLOCKED",
            },
            {
                "name": "policy_loss_limit",
                "packet": {**base, "held": True, "loss_inr": 1000},
                "expected_action": "CLOSE",
            },
            {
                "name": "policy_reserve_insufficient",
                "packet": {**base, "peak_entry_margin_inr": 10000, "free_cash_inr": 10999},
                "expected_action": "NO_TRADE",
            },
            {
                "name": "policy_reserve_exact",
                "packet": {**base, "peak_entry_margin_inr": 10000, "free_cash_inr": 11000},
                "expected_action": "ENTRY",
            },
        ]
    raise ValueError("unknown baseline")
