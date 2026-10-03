"""Closed experiment language. There is deliberately no eval/exec or generated Python."""

from __future__ import annotations

from datetime import date, time
import math
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


class DatasetExecutionScopeError(ValueError):
    """The immutable dataset does not support the proposed execution contract."""


def validate_dataset_execution_scope(spec: ExperimentSpec | dict, dataset: dict) -> None:
    """Restrict a fixed archive subset; metadata can never expand the DSL.

    An absent scope preserves existing datasets. A present scope is complete,
    fail-closed and evaluated against the protected evaluator's actual defaults.
    A shared entry spot only supports one fixed B0 entry and hold/close policies,
    never a dynamically recentered structure.
    """
    meta = dataset.get("metadata", {})
    if "execution_scope" not in meta:
        return

    def fail(reason: str) -> None:
        raise DatasetExecutionScopeError("dataset execution_scope: " + reason)

    obj = spec.model_dump(mode="json") if isinstance(spec, ExperimentSpec) else spec
    try:
        validate_dsl(obj)
    except (ValueError, KeyError, TypeError) as error:
        fail("protected DSL rejected proposal: " + str(error))
    scope = meta["execution_scope"]
    fields = {
        "entry_time",
        "width_floor",
        "hold_minutes",
        "management",
        "management_after_minutes",
        "lots",
        "shared_selection_spot",
    }
    if not isinstance(scope, dict) or set(scope) != fields:
        fail("malformed or incomplete registered subset contract")
    if (
        obj.get("evaluator") != "iron_butterfly"
        or obj.get("baseline_id", "B0-simple") != "B0-simple"
    ):
        fail("fixed selection requires the protected iron_butterfly/B0-simple evaluator")
    if scope["shared_selection_spot"] is not True:
        fail("shared_selection_spot must explicitly bind the fixed construction")

    def number(value: Any) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and value > 0
        )

    def clock(value: Any) -> time:
        try:
            parsed = time.fromisoformat(value)
            if parsed.tzinfo is not None:
                raise ValueError("offset clock")
            return parsed
        except (ValueError, TypeError):
            fail("entry_time must be a naive local ISO clock")
            raise AssertionError("unreachable")

    entry = clock(scope["entry_time"])
    if (
        not number(scope["width_floor"])
        or not number(scope["hold_minutes"])
        or scope["hold_minutes"] > 375
    ):
        fail("invalid registered width or intraday holding horizon")
    if not number(scope["lots"]) or scope["lots"] != 1:
        fail("registered subset cannot expand the one-lot research covenant")
    policies = scope["management"]
    if (
        not isinstance(policies, list)
        or not policies
        or any(not isinstance(value, str) or value not in {"hold", "close"} for value in policies)
        or len(set(policies)) != len(policies)
    ):
        fail("fixed entry spot permits only explicitly registered hold/close policies")
    reviews = scope["management_after_minutes"]
    if (
        not isinstance(reviews, list)
        or not reviews
        or any(not number(value) or value >= scope["hold_minutes"] for value in reviews)
        or len(set(reviews)) != len(reviews)
    ):
        fail("invalid registered management times")
    params = {**obj.get("parameters", {}), **obj.get("dsl", {})}
    if clock(params.get("entry_time", "10:00:00")) != entry:
        fail("entry time differs from the captured construction")
    for key, default in (("width_floor", 500), ("hold_minutes", 30), ("lots", 1)):
        value = params.get(key, default)
        if not number(value) or value != scope[key]:
            fail(key + " differs from the registered subset")
    if params.get("management", "hold") not in policies:
        fail("management policy is not supported by the fixed archive subset")
    if params.get("management_after_minutes", 15) not in reviews:
        fail("management time is outside the captured execution windows")
    if "expiry" in params:
        constructed_expiry = meta.get("construction", {}).get("expiry")
        if not constructed_expiry or params["expiry"] != constructed_expiry:
            fail("expiry override is not bound to the captured construction")
    if "opportunities" in params:
        opportunities = params["opportunities"]
        if not isinstance(opportunities, list) or not opportunities:
            fail("explicit opportunities must preserve one registered entry per session")
        seen = set()
        registered_sessions = set(dataset.get("session_dates", []))
        for opportunity in opportunities:
            if not isinstance(opportunity, dict):
                fail("malformed opportunity override")
            session = opportunity.get("session")
            if (
                not isinstance(session, str)
                or session not in registered_sessions
                or session in seen
            ):
                fail("opportunity override changes the registered session/entry allocation")
            if clock(opportunity.get("entry", "10:00:00")) != entry:
                fail("opportunity override changes the captured entry time")
            seen.add(session)
        if seen != registered_sessions:
            fail("opportunity override omits registered source sessions")


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
        nonnegative = {
            "width_floor",
            "capital_inr",
            "available_capital_inr",
            "margin_per_cycle_inr",
            "reserve_inr",
            "latency_seconds",
            "leg_spacing_seconds",
            "max_quote_age_seconds",
            "max_chain_skew_seconds",
            "max_fill_wait_seconds",
            "max_spot_disagreement",
            "slippage_points",
            "assumed_spread_points",
            "assumed_size_units",
            "hold_minutes",
            "management_after_minutes",
        }
        for key in nonnegative & set(combined):
            value = combined[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError("execution assumption must be finite and nonnegative: " + key)
        for key in ("capital_inr", "margin_per_cycle_inr", "hold_minutes", "assumed_size_units"):
            if key in combined and combined[key] <= 0:
                raise ValueError("execution assumption must be positive: " + key)
        if "hold_minutes" in combined and combined["hold_minutes"] > 375:
            raise ValueError("holding horizon exceeds intraday evaluator scope")
        if "entry_time" in combined:
            try:
                time.fromisoformat(combined["entry_time"])
            except (ValueError, TypeError):
                raise ValueError("entry_time must be an explicit ISO clock time") from None
    return {"status": "PASS", "compiled_hash": digest(obj), "language_version": "1"}


def admission(hypothesis: HypothesisSpec, dataset: dict, qualification: dict) -> dict:
    if (
        qualification.get("status") in ("FAIL", "DATA_LIMITED", "UNSUPPORTED")
        or qualification.get("qualified") is False
    ):
        return {
            "admitted": False,
            "outcome": "DATA_LIMITED",
            "reasons": qualification.get(
                "errors", qualification.get("reasons", ["dataset qualification failed"])
            ),
        }
    available = set(qualification.get("capabilities", dataset.get("capabilities", [])))
    missing = sorted(set(hypothesis.minimum_data) - available)
    if missing:
        return {
            "admitted": False,
            "outcome": "DATA_LIMITED",
            "reasons": [f"missing capability: {x}" for x in missing],
        }
    # A hypothesis cannot weaken the built-in evaluator's independently known
    # data needs by declaring an optimistic or unrelated minimum_data list.
    required: set[str] = set()
    data_reasons = []
    if hypothesis.evaluator == "controlled":
        required = {"controlled_sessions"}
        if dataset.get("provenance") != "SYNTHETIC" or dataset.get("fidelity") != "F0":
            data_reasons.append("controlled evaluator requires synthetic F0 observations")
    elif hypothesis.evaluator == "exp001":
        required = {"spot_bars", "spot_excursion", "past_only_rv", "past_only_drift"}
        if dataset.get("kind") != "spot_bars":
            data_reasons.append("EXP001 requires spot-bar observations")
        if (
            not dataset.get("timestamp_convention_verified")
            or dataset.get("availability_lag_seconds") != 60
            or dataset.get("metadata", {}).get("bar_seconds", 60) != 60
        ):
            data_reasons.append(
                "EXP001 requires verified one-minute bars and sixty-second availability lag"
            )
    elif hypothesis.evaluator == "iron_butterfly":
        kind = dataset.get("kind")
        if kind not in {"option_quotes", "option_bars", "model"}:
            data_reasons.append(
                "four-leg evaluator requires identified option quotes/bars or registered model paths"
            )
        if kind in {"option_quotes", "option_bars"}:
            required = {"identified_contracts", "dated_lot_units"}
        if kind == "option_quotes":
            required |= {"two_sided_quotes", "displayed_size"}
        meta = dataset.get("metadata", {})
        if kind == "model" and not meta.get("contracts"):
            data_reasons.append("model paths require explicit registered contract definitions")
        if not meta.get("fee_schedule") or not meta.get("contract_specs"):
            data_reasons.append("dated fee schedule and contract-lot specifications are required")
    data_reasons.extend(
        "evaluator requires missing capability: " + cap for cap in sorted(required - available)
    )
    if data_reasons:
        return {"admitted": False, "outcome": "DATA_LIMITED", "reasons": data_reasons}
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


def methodological_admission(
    hypothesis: HypothesisSpec,
    dataset: dict,
    qualification: dict,
    draft: ExperimentSpec,
    *,
    original: ExperimentSpec | None = None,
) -> dict:
    """Enforce executable science independently of any LLM recommendation.

    This does not pretend to prove every conceptual claim in critic prose. It
    checks the actual protected evaluator, frozen lineage, permitted parameters,
    timing and inference contract before any numerical execution can be registered.
    """
    report = admission(hypothesis, dataset, qualification)
    if not report["admitted"]:
        return report
    reasons = []
    if (
        draft.hypothesis_id != hypothesis.id
        or draft.campaign_id != hypothesis.campaign_id
        or draft.dataset_id != dataset["id"]
    ):
        reasons.append("experiment escaped original hypothesis/campaign/dataset lineage")
    if draft.evaluator != hypothesis.evaluator or draft.baseline_id != hypothesis.baseline_id:
        reasons.append("protected evaluator or baseline differs from the original hypothesis")
    if draft.informed_by_result_ids != hypothesis.informed_by_result_ids:
        reasons.append("prior exposed-result search lineage changed")
    if draft.fidelity != dataset["fidelity"]:
        reasons.append("experiment fidelity differs from registered data")
    if draft.inference.practical_effect != hypothesis.practical_effect:
        reasons.append("practical-effect scoring threshold differs from original hypothesis")
    supported_robustness = {"block_length"}
    if draft.evaluator == "iron_butterfly":
        supported_robustness.add("cost_stress")
    if set(draft.robustness) - supported_robustness:
        reasons.append("robustness declaration is not implemented by the selected evaluator")
    required_robustness = {"block_length"}
    if original is not None:
        required_robustness |= set(original.robustness) & supported_robustness
    if not required_robustness <= set(draft.robustness):
        reasons.append("revision removed a required registered numerical robustness check")
    if original is not None:
        immutable = (
            "id",
            "campaign_id",
            "hypothesis_id",
            "trial_id",
            "dataset_id",
            "evaluator",
            "baseline_id",
            "parameters",
            "relation",
            "parent_experiment_id",
            "informed_by_result_ids",
            "seed",
            "resources",
            "implementation_hash",
            "environment_hash",
            "approval_scope_id",
        )
        if any(getattr(draft, field) != getattr(original, field) for field in immutable):
            reasons.append("revision changed protected execution scope or lineage")
        if (
            draft.inference.alpha != original.inference.alpha
            or draft.inference.minimum_sessions != original.inference.minimum_sessions
            or draft.inference.confirmation_family != original.inference.confirmation_family
        ):
            reasons.append("revision changed deterministic scoring or confirmation criteria")
    try:
        validate_dsl(draft)
        validate_dataset_execution_scope(draft, dataset)
    except ValueError as error:
        reasons.append(str(error))
    combined = {**draft.parameters, **draft.dsl}
    for key, value in combined.items():
        if key == "evaluator":
            continue
        domain = hypothesis.parameter_domain.get(key)
        if domain is not None and value not in domain:
            reasons.append("parameter outside registered domain: " + key)
        if (
            key in hypothesis.proposed_dsl
            and value != hypothesis.proposed_dsl[key]
            and domain is None
        ):
            reasons.append("undeclared parameter change from original hypothesis: " + key)
        # Missing numeric generator defaults are allowed only when they reproduce
        # the already registered manifest/default, not a new search point.
        if (
            key not in hypothesis.proposed_dsl
            and domain is None
            and draft.evaluator == "controlled"
        ):
            defaults = {"effect": 0.0, "noise": 0.1, "n_sessions": 48}
            expected = dataset.get("metadata", {}).get(key, defaults.get(key))
            if value != expected:
                reasons.append("unregistered controlled generator parameter: " + key)
        elif (
            key not in hypothesis.proposed_dsl
            and domain is None
            and key not in (original.parameters if original else {})
        ):
            reasons.append("new parameter has no original search-scope registration: " + key)
    for key, value in hypothesis.proposed_dsl.items():
        if (
            key != "evaluator"
            and key in ALLOWED.get(hypothesis.evaluator, set())
            and key not in combined
        ):
            reasons.append("registered parameter omitted from executable draft: " + key)
    try:
        boundaries = [
            date.fromisoformat(getattr(draft.split, name))
            for name in ("train_end", "validation_end", "evaluation_end")
        ]
        if boundaries != sorted(boundaries) or len(set(boundaries)) < 3:
            reasons.append(
                "training/validation/evaluation boundaries must be strictly chronological"
            )
    except ValueError:
        reasons.append("split boundaries must be valid ISO dates")
    if draft.inference.bootstrap_samples > 10000 or draft.inference.block_length > 1000:
        reasons.append("inference exceeds bounded resampling primitives")
    if any(x < 1 or x > 1000 for x in draft.inference.robustness_block_lengths):
        reasons.append("robustness block lengths outside permitted bounds")
    if (
        not 1 <= len(draft.inference.robustness_block_lengths) <= 8
        or len(set(draft.inference.robustness_block_lengths))
        != len(draft.inference.robustness_block_lengths)
        or draft.inference.bootstrap_samples * (1 + len(draft.inference.robustness_block_lengths))
        > 50000
    ):
        reasons.append("robustness allocation exceeds finite registered resampling budget")
    if draft.evaluator != hypothesis.evaluator:
        return {"admitted": False, "outcome": "UNSUPPORTED_HYPOTHESIS", "reasons": reasons}
    if draft.evaluator == "controlled":
        if dataset.get("provenance") != "SYNTHETIC" or dataset["fidelity"] != "F0":
            return {
                "admitted": False,
                "outcome": "DATA_LIMITED",
                "reasons": ["controlled evaluator requires synthetic F0 data"],
            }
        if "controlled_sessions" not in qualification.get("capabilities", []):
            return {
                "admitted": False,
                "outcome": "DATA_LIMITED",
                "reasons": ["missing capability: controlled_sessions"],
            }
        params = {**dataset.get("metadata", {}), **combined}
        try:
            n, noise, effect = (
                params.get("n_sessions", 48),
                float(params.get("noise", 0.1)),
                float(params.get("effect", 0.0)),
            )
            if (
                isinstance(n, bool)
                or int(n) != n
                or not 5 <= int(n) <= 10000
                or not math.isfinite(noise)
                or noise < 0
                or not math.isfinite(effect)
            ):
                reasons.append("controlled generator parameters are invalid")
        except (ValueError, TypeError, OverflowError):
            reasons.append("controlled generator parameters are invalid")
    if draft.evaluator == "exp001":
        if (
            not dataset.get("timestamp_convention_verified")
            or dataset.get("availability_lag_seconds") != 60
        ):
            return {
                "admitted": False,
                "outcome": "DATA_LIMITED",
                "reasons": [
                    "EXP001 requires verified timestamp conventions and a 60-second availability lag"
                ],
            }
        if hypothesis.horizon_minutes != 30 or draft.baseline_id != "RV-only-regression":
            reasons.append(
                "EXP001 implements only the fixed 30-minute RV-only versus RV-plus-drift comparison"
            )
        if draft.split.availability_lag_seconds != 60:
            reasons.append("EXP001 inference declares an unsupported availability lag")
    if draft.evaluator == "iron_butterfly":
        if combined.get("hold_minutes", 30) != hypothesis.horizon_minutes:
            reasons.append("holding horizon differs from original hypothesis")
        if combined.get("management", "hold") == "hold":
            reasons.append(
                "candidate hold policy duplicates the protected hold baseline; no nontrivial comparison is specified"
            )
        if (
            not combined.get("capital_inr")
            or not combined.get("margin_per_cycle_inr")
            or not combined.get("margin_basis")
        ):
            reasons.append(
                "executable four-leg comparison requires declared capital, margin and margin basis"
            )
        if dataset.get("kind") == "option_bars" and (
            combined.get("bar_fill") != "available_close_adverse_spread"
            or combined.get("assumed_spread_points") is None
            or combined.get("assumed_size_units") is None
        ):
            reasons.append(
                "option-bar execution requires explicit fill, adverse spread and size assumptions"
            )
    return {
        "admitted": not reasons,
        "outcome": "UNSUPPORTED_HYPOTHESIS" if reasons else None,
        "reasons": reasons,
    }
