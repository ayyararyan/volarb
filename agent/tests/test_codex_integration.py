"""Offline contract integration: a real managed protocol process, never a live model.

The fake app-server emits explicitly controlled replies. The LangGraph, registry,
supervisor, numerical evaluator, artifact ingestion, and evidence grader are real.
These tests establish software integration, not model quality or historical edge.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from butterfly_lab.agents import AgentService
from butterfly_lab.benchmarks import controlled_dataset, controlled_hypothesis
from butterfly_lab.graph import Laboratory
from butterfly_lab.providers import FixtureProvider, ProviderError, ReplayProvider
from butterfly_lab.registry import Registry
from butterfly_lab.schemas import BudgetSpec, CampaignSpec
from butterfly_lab.settings import load_settings


def fake_server(tmp_path: Path, responses: dict, *, name: str = "codex") -> Path:
    source = Path(__file__).parent / "fixtures" / "fake_codex_server.py"
    destination = tmp_path / name
    shutil.copyfile(source, destination)
    destination.chmod(0o755)
    destination.with_name(destination.name + ".responses.json").write_text(json.dumps(responses))
    return destination


def role_responses(campaign_id: str) -> dict:
    hypothesis = controlled_hypothesis("controlled-codex-hypothesis", campaign_id).model_copy(
        update={
            "proposed_dsl": {
                "evaluator": "controlled",
                "effect": 0.3,
                "noise": 0.1,
                "n_sessions": 64,
            }
        }
    )
    narrative = {"notes": ["Controlled protocol fixture, not a real model observation."]}
    return {
        "designer": {"hypotheses": [hypothesis.model_dump(mode="json")]},
        "critic": {**narrative, "recommendation": "ADMIT"},
        "specification": {**narrative, "dsl": hypothesis.proposed_dsl},
        "replication": narrative,
        "synthesis": narrative,
        "steward": narrative,
    }


def env_file(tmp_path: Path, command: Path, *, provider: str = "codex") -> Path:
    path = tmp_path / ".env"
    path.write_text(
        f"BUTTERFLY_LLM_PROVIDER={provider}\n"
        f"BUTTERFLY_CODEX_COMMAND='{command}'\n"
        "BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN=20\n"
        "BUTTERFLY_CODEX_STARTUP_TIMEOUT_SECONDS=5\n"
        "BUTTERFLY_CODEX_REQUEST_TIMEOUT_SECONDS=5\n"
        "BUTTERFLY_LLM_MAX_OUTPUT_TOKENS=4096\n"
    )
    path.chmod(0o600)
    return path


def campaign(id: str = "codex-integration", **updates) -> CampaignSpec:
    return CampaignSpec(
        id=id,
        objective="Controlled Codex protocol lifecycle; no historical or live-model claims",
        provider="codex",
        approved=True,
        max_hypotheses=1,
        budget=BudgetSpec(llm_calls=20, llm_tokens=262144),
        **updates,
    )


def service(root: Path, configuration: Path) -> AgentService:
    from butterfly_lab.provider_factory import make_provider

    return AgentService(
        make_provider(root, settings=load_settings(configuration, environ={})),
        Registry(root),
        max_calls=20,
    )


def cli(root: Path, configuration: Path, *arguments: str, timeout: int = 60):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("BUTTERFLY_") and key != "OPENAI_API_KEY"
    }
    environment["BUTTERFLY_ENV_FILE"] = str(configuration)
    result = subprocess.run(
        [sys.executable, "-m", "butterfly_lab.cli", "--root", str(root), *arguments],
        capture_output=True,
        text=True,
        env=environment,
        timeout=timeout,
    )
    return result, json.loads(result.stdout)


def test_codex_roles_real_langgraph_external_worker_restart_and_provenance(tmp_path):
    contract = campaign()
    command = fake_server(tmp_path, role_responses(contract.id))
    configuration = env_file(tmp_path, command)
    root = tmp_path / "runtime"
    lab = Laboratory(root, service(root, configuration))
    dataset = controlled_dataset("codex-controlled-dataset")
    lab.registry.put("campaign", contract.id, contract)
    lab.registry.put("dataset", dataset.id, dataset)
    prepared = lab.run_campaign(contract.id, dataset.id)
    assert prepared["report_ref"]
    experiments = lab.registry.list("experiments", contract.id)
    assert len(experiments) == 1
    experiment_id = experiments[0]["id"]
    assert lab.registry.runs()[0]["state"] == "QUEUED"
    # The Codex process and graph can stop; durable numerical work is independent.
    lab.close()
    worker = subprocess.run(
        [
            sys.executable,
            "-m",
            "butterfly_lab.workers",
            "--root",
            str(root),
            "--max-jobs",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert worker.returncode == 0, worker.stderr
    assert json.loads(worker.stdout)["attempts_processed"] == 1
    lab = Laboratory(root, service(root, configuration))
    try:
        result = lab.resume(experiment_id)
        assert result["finding_id"]
        report = lab.campaign_report(contract.id)
        assert not report["pending_experiments"]
        assert len(report["findings"]) == len(lab.registry.runs()) == 1
        finding = report["findings"][0]
        assert finding["outcome"] == "EXPLORATORY_SUPPORTED"
        assert finding["evidence_grade"]["fidelity"] == "F0"
        assert finding["evidence_grade"]["replication"] == "independently_reconstructed"
        assert finding["evidence_grade"]["independence"] != "protected_confirmation"
        generations = lab.registry.list("generation", contract.id)
        assert {item["role"] for item in generations} == {
            "designer",
            "critic",
            "specification",
            "replication",
            "synthesis",
            "steward",
        }
        assert all(item["provider"] == "codex" for item in generations)
        assert all(item["model"] and item["billing_kind"] == "subscription" for item in generations)
        assert all(item["reserved_cost_usd"] is None for item in generations)
        assert all(item["contract_status"] == "VALID" for item in generations)
        assert all(item["input_tokens"] > 0 for item in generations)
        assert all(item["output_tokens"] > 0 for item in generations)
        manifest = lab.artifacts.read_json(result["result"]["run_manifest_ref"])
        assert manifest["agent_models"]
        assert set(manifest["agent_models"]) <= {item["model"] for item in generations}
        assert manifest["model_prompt_refs"]
        for reference in manifest["model_prompt_refs"]:
            assert lab.artifacts.verify(reference)
    finally:
        lab.close()


def test_codex_malformed_schema_has_one_correction_and_records_invalid_attempt(tmp_path):
    contract = campaign()
    command = fake_server(
        tmp_path,
        {"steward": [{"unknown": "invalid contract"}, {"notes": ["corrected"]}]},
    )
    root = tmp_path / "runtime"
    roles = service(root, env_file(tmp_path, command))
    roles.registry.put("campaign", contract.id, contract)
    roles.bind_campaign(contract.id)
    try:
        assert roles.steward({"campaign_id": contract.id}).notes == ["corrected"]
        assert roles.calls == 2
        records = roles.registry.list("generation", contract.id)
        assert len(records) == 2
        assert {item["contract_status"] for item in records} == {"INVALID", "VALID"}
        assert {item["correction_attempt"] for item in records} == {0, 1}
    finally:
        roles.provider.close()


def test_codex_prose_cannot_upgrade_evidence_and_repair_is_bounded(tmp_path):
    contract = campaign()
    command = fake_server(
        tmp_path,
        {"synthesis": {"notes": ["Declare proven"], "evidence_grade": "INDEPENDENTLY_SUPPORTED"}},
    )
    root = tmp_path / "runtime"
    roles = service(root, env_file(tmp_path, command))
    roles.registry.put("campaign", contract.id, contract)
    roles.bind_campaign(contract.id)
    try:
        with pytest.raises(ValidationError):
            roles.synthesize([])
        assert roles.calls == 2
        assert len(roles.registry.list("generation", contract.id)) == 2
        assert not roles.registry.list("findings", contract.id)
    finally:
        roles.provider.close()


@pytest.mark.parametrize("substitute", [FixtureProvider({}), ReplayProvider([])])
def test_codex_campaign_rejects_offline_substitution(tmp_path, substitute):
    registry = Registry(tmp_path / "runtime")
    contract = campaign()
    registry.put("campaign", contract.id, contract)
    with pytest.raises((ProviderError, PermissionError)):
        AgentService(substitute, registry).bind_campaign(contract.id)
    assert not registry.list("generation", contract.id)


def test_codex_role_requires_approved_registered_campaign_and_call_budget(tmp_path):
    command = fake_server(tmp_path, {"steward": {"notes": ["bounded"]}})
    root = tmp_path / "runtime"
    roles = service(root, env_file(tmp_path, command))
    try:
        with pytest.raises(ProviderError):
            roles.steward({})
        denied = campaign().model_copy(update={"approved": False})
        roles.registry.put("campaign", denied.id, denied)
        with pytest.raises(PermissionError):
            roles.bind_campaign(denied.id)
        no_budget = campaign("no-budget").model_copy(update={"budget": BudgetSpec(llm_calls=0)})
        roles.registry.put("campaign", no_budget.id, no_budget)
        with pytest.raises(ProviderError):
            roles.bind_campaign(no_budget.id)
        assert roles.calls == 0
    finally:
        roles.provider.close()


def test_codex_agent_context_rejects_protected_inputs_before_provider_call(tmp_path):
    contract = campaign()
    command = fake_server(tmp_path, {"steward": {"notes": ["not invoked"]}})
    root = tmp_path / "runtime"
    roles = service(root, env_file(tmp_path, command))
    roles.registry.put("campaign", contract.id, contract)
    roles.bind_campaign(contract.id)
    try:
        for protected in (
            {"source_path": "/controlled/private/confirmation.json"},
            {"partition": "confirmation"},
            {"raw_data": [1, 2, 3]},
            {"access_token": "synthetic-prohibited-context"},
        ):
            with pytest.raises(PermissionError):
                roles.steward(protected)
        assert roles.calls == 0
        assert not roles.registry.list("generation", contract.id)
    finally:
        roles.provider.close()


def test_cli_config_diagnostics_are_redacted_and_do_not_make_model_calls(tmp_path):
    command = fake_server(tmp_path, {"steward": {"notes": ["only on explicit test"]}})
    configuration = env_file(tmp_path, command)
    synthetic_secret = "configuration-redaction-test-value"
    configuration.write_text(configuration.read_text() + f"OPENAI_API_KEY={synthetic_secret}\n")
    root = tmp_path / "runtime"
    for arguments in (
        ("config", "check"),
        ("config", "show"),
        ("doctor",),
        ("auth", "status"),
        ("provider", "status"),
    ):
        result, output = cli(root, configuration, *arguments)
        assert result.returncode == 0, result.stderr + result.stdout
        assert synthetic_secret not in result.stdout + result.stderr
        assert isinstance(output, dict)
        if arguments in (("auth", "status"), ("provider", "status")):
            assert output["provider"] == "codex"
            assert output["installed"] and output["authenticated"] and output["reachable"]
            assert output["model_available"] and output["usable"]
            assert output["model_request_performed"] is False
    # Status must never consume the model-call budget, even when authenticated.
    trace = command.with_name(command.name + ".requests.jsonl")
    assert all(
        json.loads(line)["method"] != "turn/start" for line in trace.read_text().splitlines()
    )
    result, output = cli(root, configuration, "auth", "test")
    assert result.returncode == 0, result.stderr + result.stdout
    assert synthetic_secret not in result.stdout + result.stderr
    assert output["typed_response_validated"] and output["model_request_performed"]
    assert output["provider"] == "codex"
    assert output["billing_kind"] == "subscription"
    assert output["reserved_cost_usd"] is None
    assert (
        sum(json.loads(line)["method"] == "turn/start" for line in trace.read_text().splitlines())
        == 1
    )
    for path in root.rglob("*"):
        if path.is_file():
            assert synthetic_secret.encode() not in path.read_bytes()


def test_cli_campaign_uses_dotenv_codex_without_provider_config(tmp_path):
    contract = campaign("cli-codex-campaign")
    command = fake_server(tmp_path, role_responses(contract.id))
    configuration = env_file(tmp_path, command)
    contract_path = tmp_path / "campaign.json"
    # Missing optional identifier binds the configured provider into the immutable
    # registered contract. Connection details never enter that scientific artifact.
    serialized = contract.model_dump(mode="json")
    serialized.pop("provider")
    contract_path.write_text(json.dumps(serialized))
    dataset = controlled_dataset("cli-controlled-dataset")
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(dataset.model_dump_json())
    root = tmp_path / "runtime"
    result, output = cli(
        root,
        configuration,
        "campaign",
        "run",
        str(contract_path),
        "--dataset",
        str(dataset_path),
        "--wait",
        timeout=120,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    registry = Registry(root)
    assert registry.get("campaign", contract.id)["provider"] == "codex"
    findings = registry.list("findings", contract.id)
    assert len(findings) == 1
    assert findings[0]["outcome"] == "EXPLORATORY_SUPPORTED"
    assert isinstance(output, dict)
    assert {record["role"] for record in registry.list("generation", contract.id)} == {
        "designer",
        "critic",
        "specification",
        "replication",
        "steward",
        "synthesis",
    }
    assert "codex_command" not in json.dumps(registry.get("campaign", contract.id))


def test_fixture_campaign_remains_explicitly_offline_with_codex_machine_default(tmp_path):
    # An unavailable binary is never consulted for an explicitly fixture campaign.
    configuration = env_file(tmp_path, tmp_path / "not-installed-codex")
    root = tmp_path / "runtime"
    contract = campaign("explicit-offline").model_copy(update={"provider": "fixture"})
    from butterfly_lab.provider_factory import service_for

    Registry(root).put("campaign", contract.id, contract)
    roles = service_for(
        root,
        campaign=contract.model_dump(mode="json"),
        settings=load_settings(configuration, environ={}),
    )
    assert isinstance(roles.provider, FixtureProvider)
    roles.bind_campaign(contract.id)
    assert roles.steward({"remaining_runs": 1}).notes


@pytest.mark.parametrize("tighter_limit", ["campaign", "machine"])
def test_persistent_codex_call_ceiling_survives_service_restart_and_backup_restore(
    tmp_path, tighter_limit
):
    from butterfly_lab.backup import backup, restore

    contract = campaign().model_copy(
        update={"budget": BudgetSpec(llm_calls=1 if tighter_limit == "campaign" else 5)}
    )
    command = fake_server(tmp_path, {"steward": {"notes": ["one authorized call"]}})
    configuration = env_file(tmp_path, command)
    if tighter_limit == "machine":
        configuration.write_text(
            configuration.read_text().replace(
                "BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN=20",
                "BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN=1",
            )
        )
    root = tmp_path / "runtime"
    roles = service(root, configuration)
    roles.registry.put("campaign", contract.id, contract)
    roles.bind_campaign(contract.id)
    try:
        assert roles.steward({"remaining_runs": 1}).notes == ["one authorized call"]
    finally:
        roles.provider.close()
    roles = service(root, configuration)
    roles.bind_campaign(contract.id)
    try:
        with pytest.raises(ProviderError, match="budget"):
            roles.steward({"remaining_runs": 1})
    finally:
        roles.provider.close()
    # Generated reservations are restoreable state. User configuration and
    # secrets remain excluded even if accidentally placed inside the runtime.
    (root / ".env").write_text("OPENAI_API_KEY=synthetic-not-for-backup\n")
    receipt = backup(root, tmp_path / "snapshot")
    restored = tmp_path / "restored"
    restore(tmp_path / "snapshot", restored, manifest_sha256=receipt["manifest_sha256"])
    assert not (tmp_path / "snapshot" / ".env").exists()
    assert not (restored / ".env").exists()
    assert (restored / "codex-usage.json").read_bytes() == (root / "codex-usage.json").read_bytes()
    roles = service(restored, configuration)
    roles.bind_campaign(contract.id)
    try:
        with pytest.raises(ProviderError, match="budget"):
            roles.steward({"remaining_runs": 1})
        assert len(roles.registry.list("generation", contract.id)) == 1
    finally:
        roles.provider.close()
    trace = command.with_name(command.name + ".requests.jsonl")
    assert (
        sum(json.loads(line)["method"] == "turn/start" for line in trace.read_text().splitlines())
        == 1
    )


def test_machine_queue_ceiling_spans_campaigns_and_resumes_without_rewriting(tmp_path, monkeypatch):
    from argparse import Namespace

    from butterfly_lab.cli import lab_for
    from butterfly_lab.config import environment_hash, evaluator_hash
    from butterfly_lab.schemas import ExperimentSpec
    from butterfly_lab.settings import clear_settings_cache

    configuration = env_file(tmp_path, tmp_path / "not-installed-codex")
    configuration.write_text(
        configuration.read_text()
        + "BUTTERFLY_NUMERICAL_WORKERS=1\nBUTTERFLY_PENDING_JOB_LIMIT=1\n"
        + "BUTTERFLY_LLM_MAX_CONCURRENT_CALLS=1\n"
    )
    for key in list(os.environ):
        if key.startswith("BUTTERFLY_") or key == "OPENAI_API_KEY":
            monkeypatch.delenv(key)
    monkeypatch.setenv("BUTTERFLY_ENV_FILE", str(configuration))
    clear_settings_cache()
    root = tmp_path / "runtime"
    contract = campaign("machine-queue").model_copy(update={"provider": "fixture"})
    other_contract = contract.model_copy(update={"id": "machine-queue-other-campaign"})
    lab = lab_for(Namespace(), root, contract.model_dump(mode="json"))
    try:
        assert lab._config("review-runtime-ceiling")["max_concurrency"] == 1
        dataset = controlled_dataset()
        lab.registry.put("campaign", contract.id, contract)
        lab.registry.put("campaign", other_contract.id, other_contract)
        lab.registry.put("dataset", dataset.id, dataset)
        for ordinal in range(2):
            selected_contract = contract if ordinal == 0 else other_contract
            hypothesis = controlled_hypothesis(f"queue-h{ordinal}", selected_contract.id)
            lab.registry.put("hypothesis", hypothesis.id, hypothesis)
            experiment = ExperimentSpec(
                id=f"queue-e{ordinal}",
                campaign_id=selected_contract.id,
                hypothesis_id=hypothesis.id,
                trial_id=f"queue-t{ordinal}",
                dataset_id=dataset.id,
                evaluator="controlled",
                environment_hash=environment_hash(),
                implementation_hash=evaluator_hash(),
            )
            lab.registry.put("experiment", experiment.id, experiment)
            lab.registry.put(
                "trial",
                experiment.trial_id,
                {"campaign_id": selected_contract.id, "hypothesis_id": hypothesis.id},
            )
        assert lab.run_experiment("queue-e0")["run_id"]
        parked = lab.run_experiment("queue-e1")
        assert parked["__interrupt__"][0].value["kind"] == "queue_capacity"
        assert len(lab.registry.runs()) == 1
        assert lab.registry.get("campaign", contract.id)["budget"]["max_pending"] == 20
    finally:
        lab.close()
        clear_settings_cache()
    # A new CLI process must retain the tighter machine ceiling during resume.
    resumed, _ = cli(root, configuration, "resume", "queue-e1")
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    registry = Registry(root)
    assert len(registry.runs()) == 1
    assert not registry.get("finding", "finding-queue-e1")
    for ordinal in range(2):
        executed, worker = cli(
            root, configuration, "worker", "start", "--concurrency", "1", "--max-jobs", "1"
        )
        assert executed.returncode == 0, executed.stdout + executed.stderr
        assert worker["attempts_processed"] == 1
        finished, _ = cli(root, configuration, "resume", f"queue-e{ordinal}")
        assert finished.returncode == 0, finished.stdout + finished.stderr
        if ordinal == 0:
            admitted, _ = cli(root, configuration, "resume", "queue-e1")
            assert admitted.returncode == 0, admitted.stdout + admitted.stderr
    assert len(registry.runs()) == len(registry.list("findings")) == 2
    assert all(row["outcome"] != "BUDGET_EXHAUSTED" for row in registry.list("findings"))


def test_cli_refuses_numerical_workers_above_machine_ceiling(tmp_path):
    configuration = env_file(tmp_path, tmp_path / "not-installed-codex")
    configuration.write_text(configuration.read_text() + "BUTTERFLY_NUMERICAL_WORKERS=1\n")
    result, output = cli(
        tmp_path / "runtime",
        configuration,
        "worker",
        "start",
        "--concurrency",
        "2",
        "--max-jobs",
        "1",
    )
    assert result.returncode == 2
    assert output["error"] == "ValueError"
    assert "ceiling" in output["detail"]
