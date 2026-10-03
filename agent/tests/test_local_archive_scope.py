"""Immutable local subsets cannot masquerade as broader execution datasets."""

from copy import deepcopy

import pytest

from butterfly_lab.compiler import (
    DatasetExecutionScopeError,
    methodological_admission,
    validate_dataset_execution_scope,
)
from butterfly_lab.evaluators import evaluate
from butterfly_lab.schemas import ExperimentSpec, HypothesisSpec


def scope():
    return {
        "entry_time": "10:00:00",
        "width_floor": 200,
        "hold_minutes": 30,
        "management": ["close"],
        "management_after_minutes": [10, 15, 20],
        "lots": 1,
        "shared_selection_spot": True,
    }


def dataset():
    return {
        "id": "fixed-archive",
        "kind": "option_quotes",
        "fidelity": "F3",
        "provenance": "HISTORICAL",
        "session_dates": ["2026-01-02", "2026-01-05"],
        "metadata": {
            "execution_scope": scope(),
            "fee_schedule": [{"source": "fixture"}],
            "contract_specs": [{"source": "fixture"}],
            "construction": {"expiry": "2026-01-06"},
        },
    }


def experiment(**overrides):
    params = {
        "entry_time": "10:00:00",
        "width_floor": 200,
        "hold_minutes": 30,
        "lots": 1,
        "management": "close",
        "management_after_minutes": 15,
        "capital_inr": 100000,
        "margin_per_cycle_inr": 50000,
        "margin_basis": "explicit fixture proxy",
    }
    params.update(overrides)
    return {
        "id": "scope-experiment",
        "campaign_id": "scope-campaign",
        "hypothesis_id": "scope-hypothesis",
        "trial_id": "scope-trial",
        "dataset_id": "fixed-archive",
        "evaluator": "iron_butterfly",
        "baseline_id": "B0-simple",
        "fidelity": "F3",
        "dsl": params,
    }


def hypothesis(obj):
    return HypothesisSpec(
        id=obj["hypothesis_id"],
        campaign_id=obj["campaign_id"],
        family_id="frozen-holding-comparison",
        mechanism="Closing the fixed held butterfly changes subsequent exposure and costs.",
        expected_direction="positive incremental net PnL",
        decision_change="Compare fixed closure with holding",
        observable_inputs=["identified_contracts"],
        horizon_minutes=obj["dsl"].get("hold_minutes", 30),
        outcome="paired net INR",
        baseline_id="B0-simple",
        primary_comparison="Registered close versus the same-entry holding baseline",
        primary_metric="paired_mean_pnl",
        practical_effect=0.01,
        risk_constraints=["One lot, captured-feed scope only"],
        minimum_data=["identified_contracts"],
        falsification_rule="Practical effect is unsupported by the paired interval.",
        alternative_explanations=["Sparse capture selection"],
        evaluator="iron_butterfly",
        proposed_dsl=obj["dsl"],
    )


def qualified():
    return {
        "status": "PASS",
        "capabilities": [
            "identified_contracts",
            "dated_lot_units",
            "two_sided_quotes",
            "displayed_size",
        ],
    }


@pytest.mark.parametrize("review_minute", [10, 15, 20])
def test_supported_registered_close_passes_both_scope_and_methodology(review_minute):
    obj = experiment(management_after_minutes=review_minute)
    validate_dataset_execution_scope(obj, dataset())
    report = methodological_admission(
        hypothesis(obj), dataset(), qualified(), ExperimentSpec(**obj)
    )
    assert report["admitted"] is True, report


@pytest.mark.parametrize(
    "changed",
    [
        {"management": "recenter"},
        {"entry_time": "10:05:00"},
        {"width_floor": 250},
        {"hold_minutes": 45},
        {"lots": 2},
        {"lots": True},
        {"management_after_minutes": 12},
        {"expiry": "2026-01-13"},
    ],
)
def test_forged_parameter_cannot_expand_source_and_is_methodologically_unsupported(changed):
    obj = experiment(**changed)
    with pytest.raises(DatasetExecutionScopeError):
        validate_dataset_execution_scope(obj, dataset())
    report = methodological_admission(
        hypothesis(obj), dataset(), qualified(), ExperimentSpec(**obj)
    )
    assert report["admitted"] is False
    assert report["outcome"] == "UNSUPPORTED_HYPOTHESIS"


def test_parameter_merge_and_real_defaults_cannot_evade_restriction():
    obj = experiment()
    obj["parameters"] = {"width_floor": 200}
    del obj["dsl"]["width_floor"]
    validate_dataset_execution_scope(obj, dataset())
    del obj["parameters"]["width_floor"]  # Protected default is 500, not adapter's 200.
    with pytest.raises(DatasetExecutionScopeError, match="width_floor"):
        validate_dataset_execution_scope(obj, dataset())
    obj = experiment()
    del obj["dsl"]["management"]  # Protected default hold is not this candidate close.
    with pytest.raises(DatasetExecutionScopeError, match="management"):
        validate_dataset_execution_scope(obj, dataset())
    obj = experiment()
    obj["parameters"] = {"management": "recenter"}
    with pytest.raises(DatasetExecutionScopeError, match="conflicting"):
        validate_dataset_execution_scope(obj, dataset())


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        [],
        {**scope(), "management": ["recenter"]},
        {**scope(), "lots": 2},
        {**scope(), "shared_selection_spot": "true"},
        {**scope(), "management_after_minutes": [True]},
        {**scope(), "management_after_minutes": [30]},
        {**scope(), "width_floor": float("nan")},
        {**scope(), "entry_time": "10:00:00+05:30"},
        {**scope(), "new_primitive": "permitted"},
    ],
)
def test_malformed_scope_never_expands_protected_language(bad):
    data = dataset()
    data["metadata"]["execution_scope"] = bad
    with pytest.raises(DatasetExecutionScopeError):
        validate_dataset_execution_scope(experiment(), data)


def test_no_scope_preserves_existing_dataset_behavior_and_inputs_are_unchanged():
    data, obj = dataset(), experiment()
    before = deepcopy((data, obj))
    validate_dataset_execution_scope(obj, data)
    assert (data, obj) == before
    del data["metadata"]["execution_scope"]
    validate_dataset_execution_scope(experiment(management="recenter"), data)


@pytest.mark.parametrize(
    "opportunities",
    [
        [{"session": "2026-01-02", "entry": "10:05:00"}],
        [{"session": "2026-01-02"}, {"session": "2026-01-02"}],
        [{"session": "2026-01-06"}],
        [{"session": "2026-01-02"}],
        None,
    ],
)
def test_opportunity_override_cannot_shift_duplicate_or_drop_registered_entries(opportunities):
    with pytest.raises(DatasetExecutionScopeError):
        validate_dataset_execution_scope(experiment(opportunities=opportunities), dataset())
    validate_dataset_execution_scope(
        experiment(opportunities=[{"session": "2026-01-02"}, {"session": "2026-01-05"}]),
        dataset(),
    )


def test_worker_entry_point_rejects_forged_scope_before_any_source_read(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Source qualification/economics must not be reached")

    monkeypatch.setattr("butterfly_lab.evaluators.qualify_dataset", forbidden)
    monkeypatch.setattr("butterfly_lab.evaluators.load_dataset", forbidden)
    result = evaluate(experiment(management="recenter"), dataset(), tmp_path)
    assert result["outcome"] == "UNSUPPORTED_HYPOTHESIS"
    assert result["metrics"] == result["artifacts"] == {}
    assert result["replication"]["status"] == "NOT_APPLICABLE"


def test_scope_does_not_authorize_another_evaluator_baseline_or_code():
    for override in [{"evaluator": "controlled"}, {"baseline_id": "B-policy"}]:
        with pytest.raises(DatasetExecutionScopeError):
            validate_dataset_execution_scope({**experiment(), **override}, dataset())
    with pytest.raises(DatasetExecutionScopeError, match="arbitrary execution"):
        validate_dataset_execution_scope(experiment(code="not executable"), dataset())
