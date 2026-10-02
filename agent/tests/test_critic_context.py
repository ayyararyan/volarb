"""Inspect actual provider handoffs, not merely schema construction."""

import json

import pytest
from pydantic import ValidationError

from butterfly_lab.agents import AgentService, SpecificationOutput, _safe_context
from butterfly_lab.artifacts import ArtifactStore, digest as artifact_digest
from butterfly_lab.compiler import methodological_admission
from butterfly_lab.compiler import admission, validate_dsl
from butterfly_lab.providers import FixtureProvider, ProviderError
from butterfly_lab.registry import Registry
from butterfly_lab.review_context import build_critic_context
from butterfly_lab.schemas import (
    CampaignSpec,
    CriticContext,
    DatasetManifest,
    ExperimentSpec,
    HypothesisSpec,
    InferencePlan,
    digest,
)


def proposal():
    campaign = CampaignSpec(
        id="context-check",
        objective="Verify complete synthetic research role handoffs",
        approved=True,
        max_hypotheses=1,
        budget={"llm_calls": 12, "max_runs": 1},
        source_records=[
            {
                "id": "generator-v1",
                "title": "Controlled generator contract",
                "summary": "Unit baseline; fixed effect plus seeded normal noise.",
                "limitations": ["Engineering evidence only"],
            }
        ],
    ).model_dump(mode="json")
    hypothesis = HypothesisSpec(
        id="hyp-controlled",
        campaign_id=campaign["id"],
        family_id="paired-control",
        mechanism="The planted synthetic paired loss reduction is independently reconstructable.",
        expected_direction="positive relative loss reduction",
        decision_change="Verify the same fixed paired comparison without trading",
        observable_inputs=["synthetic_session_outcomes"],
        horizon_minutes=30,
        outcome="paired mean loss reduction",
        baseline_id="unit-loss",
        primary_comparison="Unit loss versus frozen controlled candidate on paired sessions",
        primary_metric="paired_loss_improvement",
        practical_effect=0.01,
        risk_constraints=["No trading; synthetic F0 only"],
        search_budget=1,
        minimum_data=["controlled_sessions"],
        falsification_rule="The confidence upper bound fails to reach the fixed practical hurdle.",
        alternative_explanations=["Finite sample generator noise"],
        evaluator="controlled",
        proposed_dsl={"evaluator": "controlled", "effect": 0.3, "noise": 0.1, "n_sessions": 64},
        source_refs=[{"uri": "/Users/private/source-paper.pdf", "sha256": "a" * 64}],
    )
    dataset = DatasetManifest(
        id="controlled-data",
        kind="synthetic",
        fidelity="F0",
        provenance="SYNTHETIC",
        capabilities=["controlled_sessions"],
        partition="development",
        metadata={
            "generator": "controlled_session_panel_v1",
            "n_sessions": 64,
            "raw_private_account_data": "never expose",
            "rows": [{"secret": "private"}],
        },
        source_path="/Users/private/data.json",
    ).model_dump(mode="json")
    qualification = {
        "status": "PASS",
        "rows": 64,
        "capabilities": ["controlled_sessions"],
        "limitations": ["Controlled data; no market prices"],
    }
    draft = ExperimentSpec(
        id="exp-control",
        campaign_id=campaign["id"],
        hypothesis_id=hypothesis.id,
        trial_id="trial-control",
        dataset_id=dataset["id"],
        evaluator="controlled",
        baseline_id=hypothesis.baseline_id,
        dsl=hypothesis.proposed_dsl,
        inference=InferencePlan(practical_effect=hypothesis.practical_effect),
        dataset_ref={"uri": "/private/registered/manifest.json", "sha256": "b" * 64},
    )
    return campaign, hypothesis, dataset, qualification, draft


def test_provider_receives_full_bounded_typed_review_contract_without_private_material():
    campaign, hypothesis, dataset, qualification, draft = proposal()
    seen = []

    def critic(request):
        seen.append(request)
        return {"notes": ["Complete experiment received"], "recommendation": "ADMIT"}

    context = build_critic_context(campaign, hypothesis, dataset, qualification, draft)
    AgentService(FixtureProvider({"critic": critic})).critique(context)
    actual = seen[0]["review_context"]
    CriticContext.model_validate(actual)
    assert actual["campaign"]["objective"] == campaign["objective"]
    assert actual["hypothesis"]["mechanism"] == hypothesis.mechanism
    assert actual["hypothesis_hash"] == hypothesis.digest()
    assert actual["data_context"]["fidelity"] == "F0"
    assert actual["data_context"]["qualification_status"] == "PASS"
    assert "Controlled data; no market prices" in actual["data_context"]["limitations"]
    assert actual["proposed_experiment"]["dsl"] == draft.dsl
    assert actual["proposed_experiment"]["evaluator"] == "controlled"
    assert "unit-loss" in actual["baseline"] and "Gaussian" in actual["candidate"]
    assert actual["inference"]["primary_metric"] == hypothesis.primary_metric
    assert actual["inference"]["practical_threshold"] == hypothesis.practical_effect
    assert actual["inference"]["unit_of_inference"] == "session"
    assert actual["inference"]["split"] == draft.split.model_dump(mode="json")
    assert actual["inference"]["plan"] == draft.inference.model_dump(mode="json")
    assert "No training" in actual["inference"]["training_evaluation_chronology"]
    assert "generator-v1" in actual["data_context"]["source_ids"]
    assert actual["sources"][0]["provenance_hash"] == digest(campaign["source_records"][0])
    assert actual["data_context"]["manifest_hash"] == digest(dataset)
    serialized = json.dumps(actual)
    for forbidden in (
        "/Users/private",
        "/private/registered",
        "source_path",
        "raw_private_account_data",
        "never expose",
        '"rows": [{',
        ".env",
        "oauth",
        "credentials_path",
    ):
        assert forbidden not in serialized
    assert actual["hypothesis"]["source_refs"][0]["uri"] == "sha256:" + "a" * 64
    assert actual["proposed_experiment"]["dataset_ref"]["uri"] == "sha256:" + "b" * 64
    assert actual["controlled_generator"]["n_sessions"] == 64
    assert actual["controlled_generator"]["noise_standard_deviation"] == 0.1
    assert "CI lower" in actual["inference"]["decision_rule"]


def test_context_resolves_manifest_only_generator_parameters_without_metadata_dump():
    campaign, hypothesis, dataset, qualification, draft = proposal()
    hypothesis = hypothesis.model_copy(update={"proposed_dsl": {"evaluator": "controlled"}})
    draft = draft.model_copy(update={"dsl": hypothesis.proposed_dsl})
    dataset["metadata"].update(effect=-0.2, noise=0.3, n_sessions=48)
    context = build_critic_context(campaign, hypothesis, dataset, qualification, draft)
    assert context.controlled_generator.effect == -0.2
    assert context.controlled_generator.noise_standard_deviation == 0.3
    assert context.controlled_generator.n_sessions == 48
    assert "raw_private_account_data" not in context.model_dump_json()


def test_critic_cannot_be_called_with_hypothesis_only():
    _, hypothesis, _, _, _ = proposal()
    with pytest.raises(TypeError, match="CriticContext"):
        AgentService(FixtureProvider({})).critique(hypothesis)


def test_unicode_artifact_provenance_and_scientific_identity_use_their_own_canonical_hashes(
    tmp_path,
):
    campaign, hypothesis, dataset, qualification, draft = proposal()
    campaign["source_records"][0]["summary"] = "Évaluation synthétique — paired control"
    dataset["metadata"]["description"] = "Données synthétiques"
    qualification["limitations"] = ["Synthétique seulement"]
    context = build_critic_context(campaign, hypothesis, dataset, qualification, draft)
    artifacts = ArtifactStore(tmp_path)
    assert context.data_context.qualification_hash == artifacts.put_json(qualification).sha256
    assert context.data_context.manifest_hash == artifacts.put_json(dataset).sha256
    assert context.sources[0].provenance_hash == artifact_digest(campaign["source_records"][0])
    assert context.specification_hash == draft.digest()
    assert context.hypothesis_hash == hypothesis.digest()


def test_revision_provider_receives_prior_spec_and_bounded_concerns_not_results():
    campaign, hypothesis, dataset, qualification, draft = proposal()
    previous = SpecificationOutput(dsl={**draft.dsl, "unsupported_field": True}, notes=["Draft"])
    report = {"recommendation": "REVISE", "concerns": ["Remove unsupported DSL field"]}
    context = build_critic_context(
        campaign, hypothesis, dataset, qualification, draft, revision=1, prior_reviews=[report]
    )
    seen = []

    def specify(request):
        seen.append(request)
        return {"dsl": hypothesis.proposed_dsl, "notes": ["Removed unsupported field"]}

    result = AgentService(FixtureProvider({"specification": specify})).specify(
        hypothesis, review_context=context, previous=previous, concerns=report["concerns"]
    )
    assert result.dsl == hypothesis.proposed_dsl
    assert seen[0]["previous_specification"]["dsl"]["unsupported_field"] is True
    assert seen[0]["revision_concerns"] == report["concerns"]
    assert seen[0]["review_context"]["prior_reviews"][0]["recommendation"] == "REVISE"
    assert seen[0]["hypothesis"]["id"] == hypothesis.id
    assert "numerical_results" not in seen[0]


def test_context_rejects_protected_partition_oversized_scope_and_unsafe_source_text():
    campaign, hypothesis, dataset, qualification, draft = proposal()
    with pytest.raises(PermissionError, match="Protected"):
        build_critic_context(
            campaign, hypothesis, {**dataset, "partition": "confirmation"}, qualification, draft
        )
    with pytest.raises(ValidationError):
        build_critic_context(
            {**campaign, "objective": "x" * 8001}, hypothesis, dataset, qualification, draft
        )
    for text in ("Load /Users/private/.env", "Bearer private-token", "file:///private/auth.json"):
        bad = {**campaign, "source_records": [{"id": "bad", "summary": text}]}
        with pytest.raises(PermissionError):
            build_critic_context(bad, hypothesis, dataset, qualification, draft)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.model_copy(update={"evaluator": "exp001"}),
        lambda d: d.model_copy(update={"dsl": {**d.dsl, "effect": 0.9}}),
        lambda d: d.model_copy(update={"dsl": {**d.dsl, "shell": "unsafe"}}),
        lambda d: d.model_copy(update={"seed": 123}),
        lambda d: d.model_copy(update={"inference": d.inference.model_copy(update={"alpha": 0.5})}),
        lambda d: d.model_copy(
            update={"inference": d.inference.model_copy(update={"practical_effect": 0})}
        ),
        lambda d: d.model_copy(
            update={"split": d.split.model_copy(update={"train_end": "2027-01-01"})}
        ),
    ],
)
def test_deterministic_methodology_blocks_scope_and_scoring_changes(mutate):
    _, hypothesis, dataset, qualification, draft = proposal()
    assert methodological_admission(hypothesis, dataset, qualification, draft, original=draft)[
        "admitted"
    ]
    report = methodological_admission(
        hypothesis, dataset, qualification, mutate(draft), original=draft
    )
    assert not report["admitted"] and report["outcome"] == "UNSUPPORTED_HYPOTHESIS"


def test_capability_and_qualification_failure_cannot_be_overridden_by_critic():
    _, hypothesis, dataset, qualification, draft = proposal()
    for failed in (
        {**qualification, "status": "DATA_LIMITED", "errors": ["unverified chronology"]},
        {**qualification, "capabilities": []},
    ):
        report = methodological_admission(hypothesis, dataset, failed, draft)
        assert not report["admitted"] and report["outcome"] == "DATA_LIMITED"


def test_hypothesis_cannot_omit_evaluator_required_capabilities():
    _, hypothesis, dataset, qualification, _ = proposal()
    qualification = {**qualification, "capabilities": ["optimistic_capability"]}
    for evaluator in ("controlled", "exp001", "iron_butterfly"):
        weak = hypothesis.model_copy(
            update={"evaluator": evaluator, "minimum_data": ["optimistic_capability"]}
        )
        report = admission(weak, dataset, qualification)
        assert report["outcome"] == "DATA_LIMITED" and not report["admitted"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("slippage_points", -10000),
        ("latency_seconds", -1),
        ("capital_inr", float("inf")),
        ("assumed_spread_points", -1),
        ("hold_minutes", 0),
    ],
)
def test_execution_assumptions_cannot_create_favorable_negative_costs(field, value):
    with pytest.raises(ValueError, match="execution assumption"):
        validate_dsl({"evaluator": "iron_butterfly", "dsl": {field: value}})


def test_robustness_budget_is_bounded_and_cannot_repeat_blocks():
    _, hypothesis, dataset, qualification, draft = proposal()
    for lengths in ([1] * 9, [1, 1], [0, 5]):
        with pytest.raises(ValidationError):
            InferencePlan(robustness_block_lengths=lengths)
    expensive = draft.model_copy(
        update={
            "inference": InferencePlan(
                bootstrap_samples=10000, robustness_block_lengths=[1, 2, 3, 4, 5]
            )
        }
    )
    assert not methodological_admission(hypothesis, dataset, qualification, expensive)["admitted"]


def test_ironfly_omitted_hold_uses_real_default_and_new_parameters_are_blocked():
    _, hypothesis, dataset, _, draft = proposal()
    dsl = {
        "evaluator": "iron_butterfly",
        "management": "close",
        "capital_inr": 100000,
        "margin_per_cycle_inr": 10000,
        "margin_basis": "synthetic proxy",
    }
    hypothesis = hypothesis.model_copy(
        update={
            "evaluator": "iron_butterfly",
            "baseline_id": "B0-simple",
            "horizon_minutes": 60,
            "minimum_data": ["identified_contracts"],
            "proposed_dsl": dsl,
        }
    )
    dataset = {
        **dataset,
        "kind": "option_quotes",
        "metadata": {
            "fee_schedule": ["bound fee record"],
            "contract_specs": ["bound contract record"],
        },
    }
    qualification = {
        "status": "PASS",
        "capabilities": [
            "identified_contracts",
            "dated_lot_units",
            "two_sided_quotes",
            "displayed_size",
        ],
    }
    draft = draft.model_copy(
        update={"evaluator": "iron_butterfly", "baseline_id": "B0-simple", "dsl": dsl}
    )
    report = methodological_admission(hypothesis, dataset, qualification, draft)
    assert "holding horizon differs from original hypothesis" in report["reasons"]
    hypothesis = hypothesis.model_copy(update={"horizon_minutes": 30})
    altered = draft.model_copy(update={"dsl": {**dsl, "slippage_points": 50}})
    report = methodological_admission(hypothesis, dataset, qualification, altered, original=draft)
    assert any("no original search-scope" in reason for reason in report["reasons"])


def test_nonadmission_critic_must_explain_the_actual_defect():
    campaign, hypothesis, dataset, qualification, draft = proposal()
    context = build_critic_context(campaign, hypothesis, dataset, qualification, draft)
    service = AgentService(
        FixtureProvider({"critic": {"notes": ["Opaque veto"], "recommendation": "UNSUPPORTED"}})
    )
    with pytest.raises(ValidationError, match="concrete methodological concern"):
        service.critique(context)
    assert service.calls == 2


def test_accepted_call_survives_new_agent_service_and_is_bound_to_exact_context(tmp_path):
    campaign, hypothesis, dataset, qualification, draft = proposal()
    registry = Registry(tmp_path)
    registry.put("campaign", campaign["id"], campaign)
    seen = []

    def critic(request):
        seen.append(request)
        return {"notes": ["Complete experiment received"], "recommendation": "ADMIT"}

    context = build_critic_context(campaign, hypothesis, dataset, qualification, draft)
    service = AgentService(FixtureProvider({"critic": critic}), registry)
    assert service.critique(context, call_id="critic-v0").recommendation == "ADMIT"
    restarted = AgentService(FixtureProvider({}), registry)
    assert restarted.critique(context, call_id="critic-v0").recommendation == "ADMIT"
    assert len(seen) == 1 and restarted.calls == 0
    different = build_critic_context(
        campaign, hypothesis, dataset, qualification, draft, revision=1
    )
    with pytest.raises(ProviderError, match="different request"):
        restarted.critique(different, call_id="critic-v0")


def test_ambiguous_dispatch_is_never_automatically_repeated(tmp_path):
    campaign, hypothesis, dataset, qualification, draft = proposal()
    registry = Registry(tmp_path)
    registry.put("campaign", campaign["id"], campaign)
    context = build_critic_context(campaign, hypothesis, dataset, qualification, draft)
    seen = []

    def fail(request):
        seen.append(request)
        raise ProviderError("Ambiguous dispatched turn")

    with pytest.raises(ProviderError, match="Ambiguous"):
        AgentService(FixtureProvider({"critic": fail}), registry).critique(
            context, call_id="ambiguous"
        )
    with pytest.raises(ProviderError, match="unresolved"):
        AgentService(FixtureProvider({"critic": fail}), registry).critique(
            context, call_id="ambiguous"
        )
    assert len(seen) == 1


@pytest.mark.parametrize(
    "text",
    [
        "/home/person/token.json",
        "file:///private/secrets",
        "Read .env now",
        "Bearer opaque-secret",
        r"C:\private\auth.json",
    ],
)
def test_free_text_private_locators_are_not_safe_context(text):
    with pytest.raises(PermissionError):
        _safe_context({"source_summary": text})
