from pathlib import Path

import pytest
from pydantic import ValidationError

from butterfly_lab.agents import AgentService, fixture_provider, load_seeds
from butterfly_lab.providers import FixtureProvider, ProviderError
from butterfly_lab.review_context import build_critic_context
from butterfly_lab.schemas import ExperimentSpec, InferencePlan


SEEDS = Path(__file__).parents[1] / "configs" / "seeds.json"


def review_context(hypothesis, capabilities):
    draft = ExperimentSpec(
        id="exp-" + hypothesis.id,
        campaign_id=hypothesis.campaign_id,
        hypothesis_id=hypothesis.id,
        trial_id="trial-" + hypothesis.id,
        dataset_id="fixture-data",
        evaluator=hypothesis.evaluator,
        baseline_id=hypothesis.baseline_id,
        dsl=hypothesis.proposed_dsl,
        inference=InferencePlan(practical_effect=hypothesis.practical_effect),
    )
    return build_critic_context(
        {"id": hypothesis.campaign_id, "objective": "Review the registered experiment"},
        hypothesis,
        {
            "id": "fixture-data",
            "fidelity": "F0",
            "provenance": "SYNTHETIC",
            "partition": "development",
        },
        {"status": "PASS", "capabilities": capabilities},
        draft,
    )


def test_twelve_seed_specs_and_roles_are_operational():
    seeds = load_seeds(SEEDS, "campaign")
    assert len(seeds) == len({spec.id for spec in seeds}) == 12
    assert len({spec.family_id for spec in seeds}) == 12
    service = AgentService(fixture_provider(seeds))
    generated = service.design(
        {"id": "campaign", "objective": "Challenge the butterfly edge", "max_hypotheses": 12},
        ["spot_bars", "spot_excursion", "past_only_rv", "past_only_drift"],
    )
    assert len(generated) == 12
    assert (
        service.critique(review_context(generated[0], generated[0].minimum_data)).recommendation
        == "ADMIT"
    )
    assert service.critique(review_context(generated[1], [])).recommendation == "REVISE"
    assert service.specify(generated[0]).dsl["evaluator"] == "exp001"
    assert service.replicate({"id": "frozen"}).notes
    assert service.synthesize([{"evidence_grade": "F0", "limitations": ["fixture"]}]).notes
    assert service.steward({"remaining_runs": 1}).notes


def test_generator_budget_and_development_only_context():
    seeds = load_seeds(SEEDS, "campaign")
    service = AgentService(fixture_provider(seeds), max_calls=1)
    assert (
        len(service.design({"id": "campaign", "objective": "finite", "max_hypotheses": 2}, [])) == 2
    )
    with pytest.raises(ProviderError, match="budget"):
        service.steward({})
    for diagnostics in ([{"partition": "confirmation"}], [{"partition": "validation"}]):
        with pytest.raises(PermissionError):
            AgentService(fixture_provider(seeds)).design(
                {"id": "campaign", "objective": "finite", "development_diagnostics": diagnostics},
                [],
            )


def test_agent_cannot_receive_confirmation_paths_or_credentials():
    service = AgentService(fixture_provider(load_seeds(SEEDS)))
    for payload in (
        {"source_path": "/private/data"},
        {"access_token": "fixture"},
        {"partition": "confirmation"},
    ):
        with pytest.raises(PermissionError):
            service.steward(payload)


def test_model_prose_cannot_upgrade_authoritative_grade():
    malicious = FixtureProvider(
        {"synthesis": {"notes": ["all passed"], "evidence_grade": "INDEPENDENTLY_SUPPORTED"}}
    )
    with pytest.raises(ValidationError):
        AgentService(malicious).synthesize([])


def test_model_critic_cannot_override_missing_deterministic_capabilities():
    seeds = load_seeds(SEEDS)
    # Agent's ADMIT is advisory; full missing requirements remain in the spec.
    service = AgentService(
        FixtureProvider({"critic": {"notes": ["optimistic model"], "recommendation": "ADMIT"}})
    )
    assert service.critique(review_context(seeds[1], [])).recommendation == "ADMIT"
    assert set(seeds[1].minimum_data) - set([])


def test_one_bounded_malformed_output_correction():
    seen = []

    def response(context):
        seen.append(context)
        return {"bad_field": "malformed"} if len(seen) == 1 else {"notes": ["corrected schema"]}

    service = AgentService(FixtureProvider({"steward": response}))
    assert service.steward({}).notes == ["corrected schema"]
    assert len(seen) == 2 and "correction" in seen[1]
    wrong = AgentService(FixtureProvider({"steward": {"bad": "still malformed"}}))
    with pytest.raises(ValidationError):
        wrong.steward({})
    assert wrong.calls == 2


def test_designer_capability_prose_receives_bounded_contract_correction():
    from butterfly_lab.benchmarks import controlled_hypothesis

    valid = controlled_hypothesis("h", "c").model_dump(mode="json")
    invalid = {**valid, "minimum_data": ["controlled_sessions", "64 paired synthetic sessions"]}
    seen = []

    def response(context):
        seen.append(context)
        return {"hypotheses": [invalid if len(seen) == 1 else valid]}

    service = AgentService(FixtureProvider({"designer": response}))
    hypotheses = service.design(
        {"id": "c", "objective": "Controlled method test", "max_hypotheses": 1},
        ["controlled_sessions"],
    )
    assert hypotheses[0].minimum_data == ["controlled_sessions"]
    assert len(seen) == service.calls == 2
    assert seen[1]["correction"]["errors"][0]["loc"] == ("hypotheses", 0, "minimum_data", 1)
    # A syntactically valid but unavailable capability remains a genuine data gate,
    # not something the model contract silently removes or admits.
    assert type(hypotheses[0]).model_validate(
        {**valid, "minimum_data": ["missing_quotes"]}
    ).minimum_data == ["missing_quotes"]


def test_live_agent_requires_registered_approved_usd_and_token_budget(tmp_path, monkeypatch):
    from butterfly_lab.providers import OpenAIConfig, OpenAIProvider
    from butterfly_lab.registry import Registry
    from butterfly_lab.schemas import CampaignSpec

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []

    def transport(*args):
        calls.append(args)
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"notes":["bounded"]}'}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8},
        }

    config = OpenAIConfig(
        model="test",
        ledger_path=tmp_path / "budget.json",
        approved=True,
        max_calls=10,
        max_cost_usd=1,
        input_usd_per_million=1,
        output_usd_per_million=1,
    )
    registry = Registry(tmp_path / "runtime")
    registry.put(
        "campaign",
        "zero",
        CampaignSpec(
            id="zero", objective="No model spend authorized", approved=True, provider="openai"
        ),
    )
    service = AgentService(OpenAIProvider(config, transport=transport), registry)
    with pytest.raises(ProviderError, match="USD"):
        service.bind_campaign("zero")
    assert not calls
    registry.put(
        "campaign",
        "live",
        CampaignSpec(
            id="live",
            objective="Contract tested bounded model call",
            approved=True,
            provider="openai",
            budget={"currency": "USD", "llm_currency": 0.1, "llm_tokens": 5000},
        ),
    )
    service.bind_campaign("live")
    assert service.steward({"campaign_id": "live"}).notes
    # Identical accepted calls are now replayed durably without duplicate spend.
    assert service.steward({"campaign_id": "live"}).notes
    with pytest.raises(ProviderError, match="budget"):
        service.steward({"campaign_id": "live"}, call_id="another-distinct-steward-call")
    assert len(calls) == 1
