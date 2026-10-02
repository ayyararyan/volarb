from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from langgraph.types import Command

from butterfly_lab.benchmarks import controlled_dataset, controlled_hypothesis
from butterfly_lab.cli import confirmation_service
from butterfly_lab.config import environment_hash, evaluator_hash
from butterfly_lab.graph import Laboratory, merge_refs
from butterfly_lab.registry import RegistryError
from butterfly_lab.schemas import CampaignSpec, DatasetManifest, ExperimentSpec
from butterfly_lab.workers import start_worker


def setup_lab(tmp_path, effect=0, confirmation=False):
    root = tmp_path / "runtime"
    lab = Laboratory(root)
    c = CampaignSpec(
        id="graph-test",
        objective="Controlled lifecycle with frozen scientific claim",
        approved=True,
        max_hypotheses=3,
        confirmation_dataset_id="protected" if confirmation else None,
    )
    h = controlled_hypothesis("h1", c.id)
    d = controlled_dataset()
    e = ExperimentSpec(
        id="e1",
        campaign_id=c.id,
        hypothesis_id=h.id,
        trial_id="t1",
        dataset_id=d.id,
        evaluator="controlled",
        baseline_id="unit-loss",
        parameters={"effect": effect, "n_sessions": 64},
        environment_hash=environment_hash(),
        implementation_hash=evaluator_hash(),
    )
    for kind, obj in [("campaigns", c), ("hypotheses", h), ("datasets", d), ("experiments", e)]:
        lab.registry.put(kind, obj.id, obj)
    lab.registry.put(
        "trials", "t1", {"id": "t1", "campaign_id": c.id, "hypothesis_id": h.id, "relation": "NEW"}
    )
    return lab, c, h, d, e


def test_real_graph_restart_outbox_and_negative_economics(tmp_path):
    lab, c, h, d, e = setup_lab(tmp_path, effect=-0.2)
    first = lab.run_experiment(e.id)
    assert first["__interrupt__"]
    run = first["run_id"]
    assert lab.registry.get_run(run)["state"] == "QUEUED"
    lab.close()
    worker = start_worker(tmp_path / "runtime", max_jobs=1)
    assert worker["attempts_processed"] == 1
    lab = Laboratory(tmp_path / "runtime")
    final = lab.resume(e.id)
    assert final["outcome"] == "REJECTED_FINDING"
    assert len(lab.registry.runs()) == 1
    assert final["repair_count"] == 0
    assert "session_estimates" not in final["result"]
    assert lab.run_experiment(e.id) == final
    lab.close()


def test_completion_before_graph_wait(tmp_path):
    lab, _, _, d, e = setup_lab(tmp_path)
    run = lab.registry.register_run(e, d, environment_hash(), evaluator_hash())
    start_worker(lab.root, max_jobs=1)
    result = lab.run_experiment(e.id)
    assert "__interrupt__" not in result
    assert result["run_id"] == run
    assert result["finding_id"]
    lab.close()


def test_forged_resume_rejected(tmp_path):
    lab, _, _, _, e = setup_lab(tmp_path)
    lab.run_experiment(e.id)
    with pytest.raises(RegistryError):
        lab.experiment_graph.invoke(
            Command(resume={"event_id": "forged"}), lab._config("experiment-" + e.id)
        )
    lab.close()


def test_versions_and_parallel_conflicts(tmp_path):
    lab, _, _, _, e = setup_lab(tmp_path)
    wrong = e.model_copy(update={"id": "wrong", "environment_hash": "not-installed"})
    lab.registry.put("experiments", wrong.id, wrong)
    with pytest.raises(ValueError, match="incompatible"):
        lab.run_experiment(wrong.id)
    assert merge_refs({"x": "a"}, {"x": "a", "b": "c"}) == {"b": "c", "x": "a"}
    with pytest.raises(ValueError, match="conflicting"):
        merge_refs({"x": "a"}, {"x": "b"})
    lab.close()


def test_campaign_duplicate_and_blocked_preserve_lineage(tmp_path):
    lab, c, h, d, _ = setup_lab(tmp_path)
    alias = h.model_copy(update={"id": "alias"})
    blocked = h.model_copy(update={"id": "blocked", "minimum_data": ["missing_historical_quotes"]})
    lab.run_campaign(
        c.id,
        d.id,
        [h.model_dump(mode="json"), alias.model_dump(mode="json"), blocked.model_dump(mode="json")],
    )
    assert len(lab.registry.runs()) == 1
    assert lab.registry.get("findings", "finding-exp-alias")["outcome"] == "UNSUPPORTED_HYPOTHESIS"
    assert lab.registry.get("findings", "finding-exp-blocked")["outcome"] == "DATA_LIMITED"
    assert lab.registry.get("lineage", "alias-alias")["relation"] == "DUPLICATE"
    lab.close()


def test_protected_dataset_never_reaches_ordinary_loader(tmp_path, monkeypatch):
    lab, c, h, d, e = setup_lab(tmp_path)
    protected = d.model_copy(
        update={"id": "not-ordinary", "partition": "confirmation", "prior_exposed": False}
    )
    exp = e.model_copy(update={"id": "forbidden", "dataset_id": protected.id})
    lab.registry.put("datasets", protected.id, protected)
    lab.registry.put("experiments", exp.id, exp)

    def fail(_):
        raise AssertionError("protected bytes read by ordinary graph")

    monkeypatch.setattr("butterfly_lab.data.qualify_dataset", fail)
    assert lab.run_experiment(exp.id)["outcome"] == "UNSUPPORTED_HYPOTHESIS"
    lab.close()


def test_restart_while_external_worker_runs(tmp_path):
    lab, c, h, d, e = setup_lab(tmp_path)
    lab.run_experiment(e.id)
    root = lab.root
    process = subprocess.Popen(
        [sys.executable, "-m", "butterfly_lab.workers", "--root", str(root), "--max-jobs", "1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lab.close()
    # A new graph process instance opens the persistent checkpoint while the
    # independent supervisor owns computation; no duplicate run is submitted.
    lab = Laboratory(root)
    lab.run_experiment(e.id)
    output, error = process.communicate(timeout=30)
    assert process.returncode == 0, error
    assert json.loads(output)["attempts_processed"] == 1
    assert len(lab.registry.runs()) == 1
    assert lab.resume(e.id)["finding_id"]
    lab.close()


def test_confirmation_graph_authorization_and_consumption(tmp_path):
    lab, c, h, d, e = setup_lab(tmp_path, effect=0.3, confirmation=True)
    panel = tmp_path / "sealed.json"
    panel.write_text(
        json.dumps(
            {
                "claims": {
                    h.id: {
                        "session_ids": [f"2027-01-{i:02}" for i in range(1, 29)]
                        + ["2027-02-01", "2027-02-02", "2027-02-03", "2027-02-04"],
                        "baseline": [1.0] * 32,
                        "candidate": [0.5] * 32,
                    }
                }
            }
        )
    )
    import hashlib

    protected = DatasetManifest(
        id="protected",
        kind="session_panel",
        source_path=str(panel),
        source_sha256=hashlib.sha256(panel.read_bytes()).hexdigest(),
        fidelity="F0",
        provenance="SYNTHETIC",
        partition="confirmation",
        prior_exposed=False,
        metadata={"unexamined_attestation": True},
    )
    lab.registry.put("datasets", protected.id, protected)
    lab.run_experiment(e.id)
    start_worker(lab.root, max_jobs=1)
    assert lab.resume(e.id)["outcome"] == "EXPLORATORY_SUPPORTED"
    parked = lab.advance_confirmation(c.id)
    assert parked["__interrupt__"]
    service, secret = confirmation_service(lab.root)
    batch = parked["batch_id"]
    with pytest.raises(PermissionError):
        service.authorize(
            batch,
            "researcher",
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "wrong",
        )
    service.authorize(
        batch, "operator", (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), secret
    )
    completed = lab.advance_confirmation(c.id)
    assert completed["finding_ids"]
    assert service.report(batch)["synthetic_demonstration"]
    assert not service.eligibility(protected.id)[0]
    assert lab.advance_confirmation(c.id) == completed
    lab.close()


def test_queue_backpressure_parks_and_recovers_without_false_budget_failure(tmp_path):
    from butterfly_lab.schemas import BudgetSpec

    root = tmp_path / "bounded"
    lab = Laboratory(root)
    c = CampaignSpec(
        id="bounded",
        objective="Backpressure retains eligible registered research",
        approved=True,
        budget=BudgetSpec(max_pending=1),
    )
    d = controlled_dataset("d")
    lab.registry.put("campaign", c.id, c)
    lab.registry.put("dataset", d.id, d)
    for i in range(2):
        h = controlled_hypothesis(f"h{i}", c.id)
        lab.registry.put("hypothesis", h.id, h)
        lab.registry.put(
            "trial", f"t{i}", {"id": f"t{i}", "campaign_id": c.id, "hypothesis_id": h.id}
        )
        exp = ExperimentSpec(
            id=f"e{i}",
            campaign_id=c.id,
            hypothesis_id=h.id,
            trial_id=f"t{i}",
            dataset_id=d.id,
            evaluator="controlled",
            environment_hash=environment_hash(),
            implementation_hash=evaluator_hash(),
        )
        lab.registry.put("experiment", exp.id, exp)
    lab.run_experiment("e0")
    parked = lab.run_experiment("e1")
    assert parked["__interrupt__"][0].value["kind"] == "queue_capacity"
    assert not lab.registry.get("finding", "finding-e1")
    start_worker(root, max_jobs=1)
    lab.resume("e0")
    assert lab.resume("e1")["run_id"]
    start_worker(root, max_jobs=1)
    assert lab.resume("e1")["outcome"] != "BUDGET_EXHAUSTED"
    assert len(lab.registry.runs()) == 2
    lab.close()
