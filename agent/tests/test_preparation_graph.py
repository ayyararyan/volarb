"""Actual provider handoffs and durable pre-result research lifecycle acceptance."""

from __future__ import annotations

import copy

import pytest

from butterfly_lab.agents import AgentService
from butterfly_lab.benchmarks import controlled_dataset, controlled_hypothesis
from butterfly_lab.graph import Laboratory
from butterfly_lab.providers import FixtureProvider
from butterfly_lab.registry import Registry
from butterfly_lab.schemas import BudgetSpec, CampaignSpec, digest
from butterfly_lab.settings import Settings
from butterfly_lab.workers import start_worker


def controlled_campaign(tmp_path, *, outcome="ADMIT", first_incomplete=False, effect=0.2):
    root = tmp_path / "runtime"
    c = CampaignSpec(
        id="lifecycle",
        approved=True,
        objective="Verify a fixed paired synthetic experiment through complete research lifecycle",
        max_hypotheses=1,
        preparation_batch=1,
        budget=BudgetSpec(max_runs=1, llm_calls=10, llm_tokens=100000),
        source_records=[
            {
                "id": "approved-generator-v1",
                "title": "Controlled generator protocol",
                "summary": "Paired unit-loss comparison; planted effect is engineering evidence only.",
                "limitations": ["No market or profitability claims"],
            }
        ],
    )
    h = controlled_hypothesis("hypothesis", c.id).model_copy(
        update={
            "proposed_dsl": {"effect": effect, "noise": 0.1, "n_sessions": 48},
        }
    )
    d = controlled_dataset("development-fixture")
    captured = []

    def designer(context):
        captured.append(("designer", copy.deepcopy(context)))
        return {"hypotheses": [h.model_dump(mode="json")]}

    def specification(context):
        captured.append(("specification", copy.deepcopy(context)))
        dsl = dict(context["hypothesis"]["proposed_dsl"])
        if first_incomplete and sum(role == "specification" for role, _ in captured) == 1:
            dsl.pop("effect")
        return {"dsl": dsl, "notes": ["Preserved hypothesis and preregistered generator scope."]}

    def critic(context):
        captured.append(("critic", copy.deepcopy(context)))
        # This test observes actual provider input and registry, not only schemas.
        assert not Registry(root).runs(), "No numerical result may precede critic admission"
        draft = context["review_context"]["proposed_experiment"]
        recommendation = outcome
        if first_incomplete:
            recommendation = "ADMIT" if "effect" in draft["dsl"] else "REVISE"
        return {
            "notes": ["Review the actual registered comparison, not an inferred experiment."],
            "concerns": ["Specify the original registered effect explicitly in the draft DSL."]
            if recommendation == "REVISE"
            else ["Causal interpretation is irreparable within this observational research scope."]
            if recommendation == "UNSUPPORTED"
            else [],
            "recommendation": recommendation,
        }

    def narrative(role):
        def response(context):
            captured.append((role, copy.deepcopy(context)))
            if role in ("synthesis", "steward"):
                assert Registry(root).list("findings", c.id)
                assert all(r["state"] == "INGESTED" for r in Registry(root).runs())
            return {"notes": ["Interpret authoritative frozen evidence without modifying it."]}

        return response

    def make_lab():
        provider = FixtureProvider(
            {
                "designer": designer,
                "specification": specification,
                "critic": critic,
                "replication": narrative("replication"),
                "synthesis": narrative("synthesis"),
                "steward": narrative("steward"),
            }
        )
        lab = Laboratory(root, AgentService(provider, Registry(root), max_calls=12))
        lab.registry.put("campaign", c.id, c)
        lab.registry.put("dataset", d.id, d)
        return lab

    return make_lab, c, h, d, captured


def complete(lab, campaign):
    assert start_worker(lab.root, max_jobs=1)["attempts_processed"] == 1
    exp = lab.registry.list("experiments", campaign.id)[0]
    assert lab.resume(exp["id"])["finding_id"]
    assert lab.advance_campaign(campaign.id)["report_ref"]
    report = lab.campaign_report(campaign.id)
    assert report["lifecycle_status"] == "COMPLETED"
    assert report["synthesis_complete"] and report["steward_complete"]
    assert not report["pending_experiments"]
    return report


@pytest.mark.parametrize("configured", [False, True])
def test_run_resources_are_reviewed_frozen_and_preserved_on_revision_and_resume(
    tmp_path, monkeypatch, configured
):
    settings = Settings(
        **(
            {
                "run_cpu_seconds": 120,
                "run_wall_seconds": 240,
                "run_memory_mb": 2048,
                "run_storage_bytes": 50_000_000,
            }
            if configured
            else {}
        )
    )
    monkeypatch.setattr("butterfly_lab.graph.get_settings", lambda: settings)
    expected = {
        "schema_version": "1",
        "cpu_seconds": settings.run_cpu_seconds,
        "wall_seconds": settings.run_wall_seconds,
        "memory_mb": settings.run_memory_mb,
        "storage_bytes": settings.run_storage_bytes,
    }
    factory, campaign, hypothesis, dataset, captured = controlled_campaign(
        tmp_path, first_incomplete=True
    )
    lab = factory()
    original_critic = lab.agent_service.provider.responses["critic"]

    def critic(context):
        assert context["review_context"]["proposed_experiment"]["resources"] == expected
        # A later runtime setting must not alter this draft during revision.
        monkeypatch.setattr("butterfly_lab.graph.get_settings", lambda: Settings(run_cpu_seconds=1))
        return original_critic(context)

    lab.agent_service.provider.responses["critic"] = critic
    try:
        state = lab.prepare_hypothesis(campaign.id, dataset.id, hypothesis.model_dump(mode="json"))
        versions = lab.registry.list("preparation", campaign.id)
        assert len(versions) == 2
        assert all(row["experiment"]["resources"] == expected for row in versions)
        assert all(
            context["review_context"]["proposed_experiment"]["resources"] == expected
            for role, context in captured
            if role in {"specification", "critic"}
        )
        experiment = lab.registry.get("experiments", state["experiment_id"])
        assert experiment["resources"] == expected
        assert not lab.registry.runs()
        calls = len(captured)
    finally:
        lab.close()

    restarted = factory()
    try:
        resumed = restarted.prepare_hypothesis(
            campaign.id, dataset.id, hypothesis.model_dump(mode="json")
        )
        assert resumed["draft"]["resources"] == expected
        assert len(captured) == calls
        assert not restarted.registry.runs()
    finally:
        restarted.close()


def test_admit_complete_provider_handoff_and_finalization(tmp_path):
    factory, campaign, hypothesis, dataset, captured = controlled_campaign(tmp_path)
    lab = factory()
    first = lab.run_campaign(campaign.id, dataset.id)
    assert first["__interrupt__"][0].value["kind"] == "campaign_findings"
    assert [role for role, _ in captured] == ["designer", "specification", "critic"]
    critic = next(value["review_context"] for role, value in captured if role == "critic")
    assert critic["campaign"]["objective"] == campaign.objective
    assert critic["hypothesis"] == hypothesis.model_dump(mode="json")
    assert critic["data_context"]["fidelity"] == "F0"
    assert critic["data_context"]["qualification_status"] == "PASS"
    assert critic["data_context"]["limitations"]
    assert critic["proposed_experiment"]["dsl"] == hypothesis.proposed_dsl
    assert critic["proposed_experiment"]["evaluator"] == "controlled"
    assert critic["proposed_experiment"]["baseline_id"] == "unit-loss"
    assert critic["inference"]["primary_metric"] == hypothesis.primary_metric
    assert critic["inference"]["practical_threshold"] == hypothesis.practical_effect
    assert critic["inference"]["unit_of_inference"] == "session"
    assert critic["inference"]["training_evaluation_chronology"]
    assert critic["inference"]["dependence_resampling"]
    assert any(source["id"] == "approved-generator-v1" for source in critic["sources"])
    assert critic["proposed_experiment"]["split"]
    assert critic["baseline"] and critic["candidate"]
    report = complete(lab, campaign)
    finding = report["findings"][0]
    assert finding["outcome"] == "EXPLORATORY_SUPPORTED"
    assert finding["evidence_grade"]["replication"] == "independently_reconstructed"
    assert finding["evidence_grade"]["fidelity"] == "F0"
    assert [role for role, _ in captured] == [
        "designer",
        "specification",
        "critic",
        "replication",
        "synthesis",
        "steward",
    ]
    # Finished campaign resume has neither repeated role calls nor new worker jobs.
    lab.run_campaign(campaign.id, dataset.id)
    lab.advance_campaign(campaign.id)
    assert len(captured) == 6
    assert len(lab.registry.runs()) == 1
    lab.close()


def test_revise_then_admit_retains_versions_and_lineage(tmp_path):
    factory, campaign, hypothesis, dataset, captured = controlled_campaign(
        tmp_path,
        first_incomplete=True,
    )
    lab = factory()
    lab.run_campaign(campaign.id, dataset.id)
    versions = lab.registry.list("preparation", campaign.id)
    reviews = lab.registry.list("critic_review", campaign.id)
    assert len(versions) == len(reviews) == 2
    assert [row["revision"] for row in versions] == [0, 1]
    assert versions[0]["specification_hash"] != versions[1]["specification_hash"]
    assert versions[1]["previous_specification_hash"] == versions[0]["specification_hash"]
    assert versions[1]["changed_fields"] == ["dsl"]
    assert {row["hypothesis_hash"] for row in versions} == {digest(hypothesis)}
    assert lab.registry.get("hypothesis", hypothesis.id) == hypothesis.model_dump(mode="json")
    assert [row["report"]["recommendation"] for row in reviews] == ["REVISE", "ADMIT"]
    provider_critics = [value["review_context"] for role, value in captured if role == "critic"]
    assert provider_critics[1]["prior_reviews"][0]["recommendation"] == "REVISE"
    assert provider_critics[1]["proposed_experiment"]["dsl"] == hypothesis.proposed_dsl
    assert provider_critics[1]["research_governance"]["revision"] == 1
    complete(lab, campaign)
    assert len(lab.registry.list("preparation", campaign.id)) == 2
    assert len(lab.registry.runs()) == 1
    lab.close()


def test_live_discovered_inapplicable_robustness_is_revisable_before_numerics(tmp_path):
    factory, campaign, _, dataset, captured = controlled_campaign(tmp_path)
    lab = factory()

    def specify(context):
        captured.append(("specification", copy.deepcopy(context)))
        revision = context["review_context"]["research_governance"]["revision"]
        # Initial human/model draft may still contain an inapplicable declaration.
        repairing = "previous_specification" in context
        assert revision <= 1
        return {
            "dsl": context["hypothesis"]["proposed_dsl"],
            "notes": ["Correct robustness applicability"],
            "robustness": ["block_length"] if repairing else ["block_length", "cost_stress"],
        }

    def critique(context):
        captured.append(("critic", copy.deepcopy(context)))
        assert not lab.registry.runs()
        bad = "cost_stress" in context["review_context"]["proposed_experiment"]["robustness"]
        return {
            "notes": ["Assess actual supported checks"],
            "recommendation": "REVISE" if bad else "ADMIT",
            "concerns": ["Remove undefined cost stress from controlled evaluator"] if bad else [],
        }

    lab.agent_service.provider.responses.update(specification=specify, critic=critique)
    lab.run_campaign(campaign.id, dataset.id)
    versions = lab.registry.list("preparation", campaign.id)
    assert len(versions) == 2
    assert versions[0]["specification_hash"] != versions[1]["specification_hash"]
    assert versions[1]["changed_fields"] == ["robustness"]
    assert versions[1]["experiment"]["robustness"] == ["block_length"]
    assert [
        row["report"]["recommendation"] for row in lab.registry.list("critic_review", campaign.id)
    ] == ["REVISE", "ADMIT"]
    complete(lab, campaign)
    lab.close()


@pytest.mark.parametrize(
    "robustness,admitted", [(["block_length"], True), (["block_length", "cost_stress"], False)]
)
def test_supplied_draft_is_labelled_and_cannot_bypass_deterministic_admission(
    tmp_path, robustness, admitted
):
    factory, campaign, hypothesis, dataset, captured = controlled_campaign(tmp_path)
    lab = factory()
    supplied = {
        "dsl": hypothesis.proposed_dsl,
        "notes": ["Explicit supplied engineering draft"],
        "robustness": robustness,
    }
    result = lab.prepare_hypothesis(
        campaign.id, dataset.id, hypothesis.model_dump(mode="json"), initial_specification=supplied
    )
    assert bool(result.get("experiment_id")) == admitted
    assert [role for role, _ in captured] == ["critic"]
    assert lab.registry.list("preparation", campaign.id)[0]["origin"] == "supplied_draft"
    assert not lab.registry.runs()
    with pytest.raises(ValueError, match="cannot change"):
        lab.prepare_hypothesis(
            campaign.id,
            dataset.id,
            hypothesis.model_dump(mode="json"),
            initial_specification={**supplied, "notes": ["changed"]},
        )
    lab.close()


def test_revise_exhaustion_never_starts_numerics(tmp_path):
    factory, campaign, _, dataset, captured = controlled_campaign(tmp_path, outcome="REVISE")
    lab = factory()
    final = lab.run_campaign(campaign.id, dataset.id)
    assert final["report_ref"]
    assert len(lab.registry.list("preparation", campaign.id)) == 3
    assert len(lab.registry.list("critic_review", campaign.id)) == 3
    assert not lab.registry.list("experiments", campaign.id)
    assert not lab.registry.runs()
    finding = lab.registry.list("findings", campaign.id)[0]
    assert finding["outcome"] == "UNSUPPORTED_HYPOTHESIS"
    assert finding["experiment_id"] is None
    assert any("exhausted" in text for text in finding["limitations"])
    assert [role for role, _ in captured].count("specification") == 3
    lab.close()


def test_unsupported_is_nonexecuted_scoped_critic_veto(tmp_path):
    factory, campaign, hypothesis, dataset, _ = controlled_campaign(tmp_path, outcome="UNSUPPORTED")
    lab = factory()
    lab.run_campaign(campaign.id, dataset.id)
    report = lab.registry.get("methodological_admission", "admission-" + hypothesis.id)
    assert report["report"]["admitted"]  # Deterministic checks do not prove semantic criticism.
    assert report["authorized"] is False
    assert lab.registry.list("findings", campaign.id)[0]["outcome"] == "UNSUPPORTED_HYPOTHESIS"
    assert not lab.registry.runs()
    assert len(lab.registry.list("preparation", campaign.id)) == 1
    lab.close()


def test_capability_failure_before_critic_optimism(tmp_path):
    factory, campaign, hypothesis, dataset, captured = controlled_campaign(tmp_path)
    hypothesis = hypothesis.model_copy(update={"minimum_data": ["unavailable_depth_history"]})
    lab = factory()
    lab.run_campaign(campaign.id, dataset.id, [hypothesis.model_dump(mode="json")])
    assert not any(role in ("critic", "specification") for role, _ in captured)
    assert not lab.registry.runs()
    assert not lab.registry.list("experiments", campaign.id)
    assert lab.registry.list("findings", campaign.id)[0]["outcome"] == "DATA_LIMITED"
    lab.close()


def test_negative_result_is_finding_not_revision_signal(tmp_path):
    factory, campaign, _, dataset, captured = controlled_campaign(tmp_path, effect=-0.2)
    lab = factory()
    lab.run_campaign(campaign.id, dataset.id)
    finding = complete(lab, campaign)["findings"][0]
    assert finding["outcome"] == "REJECTED_FINDING"
    assert finding["evidence_grade"]["replication"] == "independently_reconstructed"
    assert [role for role, _ in captured].count("specification") == 1
    assert [role for role, _ in captured].count("critic") == 1
    assert len(lab.registry.list("preparation", campaign.id)) == 1
    lab.close()


@pytest.mark.parametrize(
    "kind,version",
    [
        ("preparation", 0),
        ("critic_review", 0),
        ("preparation", 1),
        ("critic_review", 1),
    ],
)
def test_restart_after_accepted_role_does_not_repeat_calls_or_versions(
    tmp_path, monkeypatch, kind, version
):
    factory, campaign, _, dataset, captured = controlled_campaign(tmp_path, first_incomplete=True)
    lab = factory()
    original_put = lab.registry.put
    crashed = False

    def crash_after_record(record_kind, identifier, payload):
        nonlocal crashed
        result = original_put(record_kind, identifier, payload)
        if not crashed and record_kind == kind and payload.get("revision") == version:
            crashed = True
            raise RuntimeError("simulated process loss after durable accepted response")
        return result

    monkeypatch.setattr(lab.registry, "put", crash_after_record)
    with pytest.raises(RuntimeError, match="simulated process loss"):
        lab.run_campaign(campaign.id, dataset.id)
    calls_at_crash = len(captured)
    lab.close()
    lab = factory()
    lab.run_campaign(campaign.id, dataset.id)
    assert calls_at_crash >= 2
    assert [role for role, _ in captured].count("designer") == 1
    assert [role for role, _ in captured].count("specification") == 2
    assert [role for role, _ in captured].count("critic") == 2
    assert len(lab.registry.list("preparation", campaign.id)) == 2
    assert len(lab.registry.list("critic_review", campaign.id)) == 2
    complete(lab, campaign)
    assert len(lab.registry.runs()) == 1
    lab.close()


def test_admit_cannot_override_deterministic_scope_failure(tmp_path):
    factory, campaign, _, dataset, captured = controlled_campaign(tmp_path)
    lab = factory()

    # A schema-valid role response attempts an unregistered outcome-changing parameter.
    def specification(context):
        captured.append(("specification", context))
        return {
            "dsl": {"effect": 0.99, "noise": 0.1, "n_sessions": 48},
            "notes": ["Outside the authorized effect domain."],
        }

    lab.agent_service.provider.responses["specification"] = specification
    lab.run_campaign(campaign.id, dataset.id)
    assert not lab.registry.runs()
    assert lab.registry.list("findings", campaign.id)[0]["outcome"] == "UNSUPPORTED_HYPOTHESIS"
    assert lab.registry.list("critic_review", campaign.id)[0]["report"]["recommendation"] == "ADMIT"
    lab.close()


def test_dsl_only_revision_preserves_prior_split_and_inference(tmp_path):
    factory, campaign, _, dataset, captured = controlled_campaign(tmp_path, first_incomplete=True)
    lab = factory()
    original = lab.agent_service.provider.responses["specification"]

    def specification(context):
        response = original(context)
        if sum(role == "specification" for role, _ in captured) == 1:
            response["inference"] = {"bootstrap_samples": 199, "practical_effect": 0.01}
            response["split"] = {"refit": "frozen"}
        return response

    lab.agent_service.provider.responses["specification"] = specification
    lab.run_campaign(campaign.id, dataset.id)
    versions = lab.registry.list("preparation", campaign.id)
    assert versions[0]["experiment"]["inference"]["bootstrap_samples"] == 199
    assert versions[1]["experiment"]["inference"] == versions[0]["experiment"]["inference"]
    assert versions[1]["experiment"]["split"] == versions[0]["experiment"]["split"]
    assert versions[1]["changed_fields"] == ["dsl"]
    lab.close()


def test_irreparable_role_contract_failure_is_implementation_failed(tmp_path):
    factory, campaign, _, dataset, captured = controlled_campaign(tmp_path)
    lab = factory()

    def malformed(context):
        captured.append(("specification", context))
        return {"not_a_specification": True}

    lab.agent_service.provider.responses["specification"] = malformed
    assert lab.run_campaign(campaign.id, dataset.id)["report_ref"]
    assert [role for role, _ in captured].count("specification") == 2
    assert lab.registry.list("findings", campaign.id)[0]["outcome"] == "IMPLEMENTATION_FAILED"
    assert not lab.registry.runs()
    lab.close()


@pytest.mark.parametrize("stage", ["synthesis", "steward", "campaign-report"])
def test_finalization_restart_preserves_accepted_calls_and_report(tmp_path, monkeypatch, stage):
    factory, campaign, _, dataset, captured = controlled_campaign(tmp_path)
    lab = factory()
    lab.run_campaign(campaign.id, dataset.id)
    start_worker(lab.root, max_jobs=1)
    exp = lab.registry.list("experiments", campaign.id)[0]
    lab.resume(exp["id"])
    original = lab.registry.put
    crashed = False

    def persist_then_crash(kind, identifier, payload):
        nonlocal crashed
        result = original(kind, identifier, payload)
        if not crashed and kind == "source" and identifier == stage + "-" + campaign.id:
            crashed = True
            raise RuntimeError("finalization checkpoint lost")
        return result

    monkeypatch.setattr(lab.registry, "put", persist_then_crash)
    with pytest.raises(RuntimeError, match="finalization checkpoint lost"):
        lab.advance_campaign(campaign.id)
    lab.close()
    lab = factory()
    assert lab.advance_campaign(campaign.id)["report_ref"]
    assert lab.campaign_report(campaign.id)["lifecycle_status"] == "COMPLETED"
    assert [role for role, _ in captured].count("synthesis") == 1
    assert [role for role, _ in captured].count("steward") == 1
    assert (
        len(
            [e for e in lab.registry.events(campaign.id) if e["event_type"] == "CAMPAIGN_COMPLETED"]
        )
        == 1
    )
    assert len(lab.registry.runs()) == 1
    lab.close()
