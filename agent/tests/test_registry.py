from __future__ import annotations

import concurrent.futures
import os
import time

import pytest

from butterfly_lab.artifacts import ArtifactError, ArtifactStore, plain
from butterfly_lab.registry import (
    BudgetExceeded,
    ConflictError,
    Registry,
    RegistryError,
    StaleFence,
)
from butterfly_lab.schemas import (
    CampaignSpec,
    DatasetManifest,
    ExperimentSpec,
    BudgetSpec,
    RunResources,
    HypothesisSpec,
    Relation,
)


def setup_registry(tmp_path, *, max_runs=10, cpu_seconds=300, pending=20):
    registry = Registry(tmp_path / "runtime")
    campaign = CampaignSpec(
        id="test",
        objective="Controlled worker and scientific invariant test",
        approved=True,
        numerical_concurrency=2,
        budget=BudgetSpec(
            max_runs=max_runs,
            cpu_seconds=cpu_seconds,
            storage_bytes=100_000_000,
            max_pending=pending,
        ),
    )
    registry.put("campaign", campaign.id, campaign)
    hypothesis = HypothesisSpec(
        id="hyp",
        campaign_id="test",
        family_id="controlled",
        mechanism="Known controlled effect provides a worker verification target",
        expected_direction="positive",
        decision_change="Compare registered controlled predictors",
        observable_inputs=["controlled_state"],
        horizon_minutes=30,
        outcome="paired_loss",
        baseline_id="constant",
        primary_comparison="candidate versus constant baseline",
        primary_metric="paired_loss",
        practical_effect=0.01,
        risk_constraints=["fixture only"],
        minimum_data=["synthetic"],
        falsification_rule="Candidate fails to improve registered loss",
        alternative_explanations=["Monte Carlo noise"],
        evaluator="controlled",
    )
    registry.put("hypothesis", hypothesis.id, hypothesis)
    registry.put(
        "trial",
        "trial",
        {"id": "trial", "campaign_id": "test", "hypothesis_id": "hyp", "relation": "NEW"},
    )
    dataset = DatasetManifest(
        id="synthetic", kind="synthetic", fidelity="F0", provenance="SYNTHETIC"
    )
    experiment = ExperimentSpec(
        id="exp",
        campaign_id="test",
        hypothesis_id="hyp",
        trial_id="trial",
        dataset_id=dataset.id,
        evaluator="controlled",
        resources=RunResources(cpu_seconds=10, storage_bytes=1_000_000),
    )
    return registry, experiment, dataset


def register(registry, exp, data):
    return registry.register_run(exp, data, "environment-v1", "evaluator-v1")


def test_atomic_idempotent_registration_and_full_input_identity(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(lambda _: register(reg, exp, data), range(12)))
    assert len(set(ids)) == 1
    assert reg.status()["budget_committed_upper_bounds"]["runs"] == 1
    changed_environment = reg.register_run(exp, data, "environment-v2", "evaluator-v1")
    assert changed_environment != ids[0]
    with pytest.raises(ConflictError):
        reg.register_run(
            exp.model_copy(update={"seed": 88}), data, "environment-v1", "evaluator-v1"
        )


def test_immutable_entities_and_strict_models(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    reg.put("dataset", data.id, data)
    reg.put("dataset", data.id, data)
    with pytest.raises(ConflictError):
        reg.put("dataset", data.id, data.model_copy(update={"prior_exposed": False}))
    with pytest.raises(ValueError):
        reg.put("dataset", "bad", {**data.model_dump(mode="json"), "id": "bad", "invented": True})


def test_budget_prevents_concurrent_overspend_and_no_orphan_outbox(tmp_path):
    reg, exp, data = setup_registry(tmp_path, max_runs=1)

    def attempt(i):
        try:
            return register(reg, exp.model_copy(update={"id": f"exp-{i}"}), data)
        except BudgetExceeded:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(attempt, range(8)))
    assert sum(x is not None for x in ids) == 1
    assert reg.status()["pending_outbox"] == 1
    assert len(reg.runs()) == 1


def test_hypothesis_search_budget_separates_selection_and_monte_carlo(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    register(reg, exp, data)
    reg.put(
        "trial",
        "variant",
        {"id": "variant", "campaign_id": "test", "hypothesis_id": "hyp", "relation": "VARIANT"},
    )
    with pytest.raises(BudgetExceeded, match="hypothesis search"):
        register(
            reg,
            exp.model_copy(
                update={"id": "variant-exp", "trial_id": "variant", "relation": Relation.VARIANT}
            ),
            data,
        )
    reg.put(
        "trial",
        "mc",
        {"id": "mc", "campaign_id": "test", "hypothesis_id": "hyp", "relation": "MONTE_CARLO"},
    )
    register(
        reg,
        exp.model_copy(
            update={"id": "mc-exp", "trial_id": "mc", "relation": Relation.MONTE_CARLO, "seed": 91}
        ),
        data,
    )
    assert len(reg.runs()) == 2
    assert reg.status()["budget_committed_upper_bounds"]["runs"] == 2


def test_trial_and_experiment_cannot_disagree_about_selection_lineage(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    with pytest.raises(ConflictError, match="lineage relation"):
        register(reg, exp.model_copy(update={"relation": Relation.MONTE_CARLO}), data)
    assert not reg.runs()


def test_claim_fencing_duplicate_completion_and_ingestion(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    run = register(reg, exp, data)
    job = reg.claim("worker", os.getpid())
    assert job["run_id"] == run
    assert reg.claim("other", os.getpid()) is None
    ref = reg.artifacts.put_json({"outcome": "INCONCLUSIVE", "metrics": {"n": 5}})
    with pytest.raises(StaleFence):
        reg.complete(run, job["attempt_id"], job["fence"] + 1, ref)
    event = reg.complete(run, job["attempt_id"], job["fence"], ref)
    assert reg.complete(run, job["attempt_id"], job["fence"], ref) == event
    assert reg.get_run(run)["event_id"] == event
    assert reg.register_wait(run, "thread")["event_id"] == event
    assert reg.validate_terminal_event(run, event)["payload"]["result_ref"] == plain(ref)
    with pytest.raises(RegistryError):
        reg.validate_terminal_event(run, "forged")
    with pytest.raises(ConflictError):
        reg.complete(
            run, job["attempt_id"], job["fence"], reg.artifacts.put_json({"different": True})
        )
    assert reg.ingest(run) == reg.ingest(run)
    assert reg.get_run(run)["state"] == "INGESTED"


def test_expired_lease_does_not_duplicate_living_worker(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    run = register(reg, exp, data)
    job = reg.claim("worker", os.getpid(), lease_seconds=0.01)
    time.sleep(0.02)
    assert reg.reconcile()[0]["state"] == "LOST_UNRESOLVED"
    assert reg.claim("replacement", os.getpid()) is None
    assert reg.get_run(run)["fence"] == job["fence"]


def test_confirmed_dead_worker_retry_and_budget_fencing(tmp_path, monkeypatch):
    reg, exp, data = setup_registry(tmp_path)
    run = register(reg, exp, data)
    job = reg.claim("worker", os.getpid())
    monkeypatch.setattr("butterfly_lab.registry.process_alive", lambda *_: False)
    assert reg.reconcile()[0]["state"] == "QUEUED"
    new = reg.claim("replacement", os.getpid())
    assert new["fence"] == 2 and new["attempt_id"] != job["attempt_id"]
    with pytest.raises(StaleFence):
        reg.heartbeat(run, job["attempt_id"], job["fence"])
    assert reg.status()["budget_committed_upper_bounds"]["cpu_seconds"] == 20
    with pytest.raises(RegistryError):
        reg.fail(run, new["attempt_id"], new["fence"], {"kind": "POOR_PNL"}, retryable=True)


def test_cancellation_and_cannot_complete_after_cancel(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    run = register(reg, exp, data)
    job = reg.claim("worker", os.getpid())
    queued = register(reg, exp.model_copy(update={"id": "second"}), data)
    assert reg.cancel_campaign("test") == {"queued_cancelled": 1, "running_requested": 1}
    assert reg.get_run(queued)["state"] == "CANCELLED"
    assert not reg.heartbeat(run, job["attempt_id"], job["fence"])
    with pytest.raises(RegistryError):
        reg.complete(run, job["attempt_id"], job["fence"], reg.artifacts.put_json({"ok": True}))
    assert (
        reg.fail(run, job["attempt_id"], job["fence"], {"kind": "CANCELLED"}, cancelled=True)
        == "CANCELLED"
    )


def test_atomic_artifacts_reject_corruption_external_uri_and_nan(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_json({"meaning": "negative findings matter"})
    assert store.put_json({"meaning": "negative findings matter"}) == ref
    with pytest.raises(ValueError):
        store.put_json({"bad": float("nan")})
    with pytest.raises(ArtifactError):
        store.path({**plain(ref), "uri": "/etc/passwd"})
    path = store.path(ref)
    path.chmod(0o600)
    path.write_bytes(b"corrupted")
    with pytest.raises(ArtifactError):
        store.read_json(ref)


def test_migration_and_resume_versions_fail_closed(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    with reg.transaction() as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(RegistryError):
        Registry(reg.root)


def test_unapproved_campaign_has_no_numerical_execution(tmp_path):
    reg = Registry(tmp_path / "runtime")
    reg.put("campaign", "c", CampaignSpec(id="c", objective="Unapproved campaign contract"))
    dataset = DatasetManifest(id="d", kind="synthetic", fidelity="F0", provenance="SYNTHETIC")
    exp = ExperimentSpec(
        id="e",
        campaign_id="c",
        hypothesis_id="h",
        trial_id="t",
        dataset_id="d",
        evaluator="controlled",
    )
    with pytest.raises(RegistryError):
        register(reg, exp, dataset)


def test_protected_services_share_budget_and_are_not_claimable(tmp_path):
    reg, exp, data = setup_registry(tmp_path, cpu_seconds=15)
    service = reg.reserve_service_budget("test", "final-1", 10, 1000)
    assert service["state"] == "RESERVED"
    assert reg.reserve_service_budget("test", "final-1", 10, 1000) == service
    assert reg.claim("ordinary", os.getpid()) is None
    with pytest.raises(BudgetExceeded):
        register(reg, exp, data)
    with pytest.raises(ConflictError):
        reg.reserve_service_budget("test", "final-1", 11, 1000)
    ref = reg.artifacts.put_json({"protected_fixture": True})
    assert reg.finish_service("final-1", result_ref=ref)["state"] == "COMPLETED"
    assert reg.finish_service("final-1", result_ref=ref)["state"] == "COMPLETED"


def test_registered_hypothesis_and_trial_required(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    with pytest.raises(RegistryError, match="registered hypothesis"):
        register(reg, exp.model_copy(update={"hypothesis_id": "missing"}), data)
    with pytest.raises(RegistryError, match="registered trial"):
        register(reg, exp.model_copy(update={"trial_id": "missing"}), data)


def test_unknown_process_after_launch_intent_is_never_requeued(tmp_path, monkeypatch):
    reg, exp, data = setup_registry(tmp_path)
    run = register(reg, exp, data)
    job = reg.claim("owner", os.getpid())
    reg.prepare_job(run, job["attempt_id"], job["fence"], reg.root / "launching")
    monkeypatch.setattr("butterfly_lab.registry.process_alive", lambda *_: False)
    assert reg.reconcile()[0]["state"] == "LOST_UNRESOLVED"
    assert reg.claim("replacement", os.getpid()) is None
