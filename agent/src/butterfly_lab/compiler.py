"""Closed experiment language. There is deliberately no eval/exec or generated Python."""

from __future__ import annotations

from typing import Any

from .schemas import ExperimentSpec, HypothesisSpec, digest

EVALUATORS = {"exp001", "iron_butterfly", "controlled"}
MANAGEMENT = {"hold", "close", "recenter"}
IRON_KEYS = {
    "entry_time",
    "hold_minutes",
    "width_floor",
    "lots",
    "expiry",
    "management",
    "management_after_minutes",
    "capital_inr",
    "available_capital_inr",
    "margin_per_cycle_inr",
    "margin_basis",
    "reserve_inr",
    "latency_seconds",
    "leg_spacing_seconds",
    "max_quote_age_seconds",
    "max_chain_skew_seconds",
    "max_fill_wait_seconds",
    "max_spot_disagreement",
    "slippage_points",
    "opportunities",
    "bar_fill",
    "assumed_spread_points",
    "assumed_size_units",
}
ALLOWED = {
    "exp001": set(),
    "controlled": {"n_sessions", "effect", "noise"},
    "iron_butterfly": IRON_KEYS,
}


def validate_dsl(spec: ExperimentSpec | dict) -> dict:
    obj = spec.model_dump(mode="json") if isinstance(spec, ExperimentSpec) else spec
    if obj["evaluator"] not in EVALUATORS:
        raise ValueError("unknown protected evaluator")
    dsl = obj.get("dsl", {})
    forbidden = {"python", "code", "shell", "command", "module", "import", "url"}

    def inspect(value: Any):
        if isinstance(value, dict):
            if forbidden.intersection(value):
                raise ValueError("arbitrary execution forbidden in experiment DSL")
            for item in value.values():
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)

    inspect(dsl)
    inspect(obj.get("parameters", {}))
    parameters = obj.get("parameters", {})
    overlap = set(parameters) & set(dsl)
    if any(parameters[key] != dsl[key] for key in overlap):
        raise ValueError("conflicting parameter and DSL values")
    if "evaluator" in dsl and dsl["evaluator"] != obj["evaluator"]:
        raise ValueError("DSL evaluator differs from frozen evaluator")
    unknown = (set(dsl) - {"evaluator"}) | set(parameters)
    unknown -= ALLOWED[obj["evaluator"]]
    if unknown:
        raise ValueError("unsupported scientific DSL keys: " + ", ".join(sorted(unknown)))
    combined = {**parameters, **dsl}
    if "management" in combined and combined["management"] not in MANAGEMENT:
        raise ValueError("unregistered management primitive")
    if obj["evaluator"] == "iron_butterfly":
        if combined.get("lots", 1) != 1:
            raise ValueError("release-one research covenant permits one lot total")
        if "stop_points" in combined:
            raise ValueError("intrabar stop primitive not implemented")
    return {"status": "PASS", "compiled_hash": digest(obj), "language_version": "1"}


def admission(hypothesis: HypothesisSpec, dataset: dict, qualification: dict) -> dict:
    available = set(qualification.get("capabilities", dataset.get("capabilities", [])))
    missing = sorted(set(hypothesis.minimum_data) - available)
    if missing:
        return {
            "admitted": False,
            "outcome": "DATA_LIMITED",
            "reasons": [f"missing capability: {x}" for x in missing],
        }
    if dataset.get("partition") == "confirmation":
        return {
            "admitted": False,
            "outcome": "UNSUPPORTED_HYPOTHESIS",
            "reasons": ["ordinary workers cannot access confirmation"],
        }
    if hypothesis.search_budget < 1:
        return {
            "admitted": False,
            "outcome": "UNSUPPORTED_HYPOTHESIS",
            "reasons": ["no search allocation"],
        }
    return {"admitted": True, "outcome": None, "reasons": []}
