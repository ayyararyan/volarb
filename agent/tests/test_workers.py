from __future__ import annotations

import os

import pytest

from butterfly_lab.artifacts import plain
from butterfly_lab.config import environment_hash, evaluator_hash
from butterfly_lab.registry import SourceBindingError
from butterfly_lab.workers import WorkerSupervisor, _atomic_json
from test_registry import setup_registry, register


def test_real_sandboxed_external_worker_and_duplicate_safe_ingestion(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    exp = exp.model_copy(
        update={
            "parameters": {"n_sessions": 12, "effect": 0.0},
            "inference": exp.inference.model_copy(
                update={"bootstrap_samples": 99, "minimum_sessions": 5}
            ),
        }
    )
    run = reg.register_run(exp, data, environment_hash(), evaluator_hash())
    os.environ["DHAN_ACCESS_TOKEN"] = "deliberate-fixture-secret-not-real"
    try:
        assert WorkerSupervisor(reg.root).run_once()
    finally:
        os.environ.pop("DHAN_ACCESS_TOKEN")
    row = reg.get_run(run)
    if row["state"] != "COMPLETED":
        failure = row["failure"]
        if failure and "stderr_ref" in failure:
            pytest.fail(reg.artifacts.path(failure["stderr_ref"]).read_text())
        pytest.fail(str(failure))
    result = reg.ingest(run)
    assert result["provenance"] == "SYNTHETIC"
    assert result["metrics"]["n_sessions"] == 12
    assert result["artifacts"]["opportunities"] == result["artifacts"]["session_outcomes"]
    assert reg.artifacts.verify_tree(result) >= 3
    assert result["execution"]["cpu_seconds"] > 0
    assert not WorkerSupervisor(reg.root).run_once()


def test_incompatible_science_hash_cannot_execute(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    run = register(reg, exp, data)
    assert WorkerSupervisor(reg.root).run_once()
    row = reg.get_run(run)
    assert row["state"] == "FAILED"
    assert "Incompatible" in row["failure"]["message"]
    assert not (reg.root / "jobs" / run / row["attempt_id"] / "published.json").exists()


def test_confirmation_cannot_be_sent_to_general_worker(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    data = data.model_copy(update={"partition": "confirmation", "prior_exposed": False})
    with pytest.raises(SourceBindingError, match="confirmation"):
        reg.register_run(exp, data, environment_hash(), evaluator_hash())
    assert reg.runs() == []
    assert not WorkerSupervisor(reg.root).run_once()


def test_publication_before_completion_crash_is_recovered(tmp_path, monkeypatch):
    reg, exp, data = setup_registry(tmp_path)
    run = register(reg, exp, data)
    job = reg.claim("owner", os.getpid())
    scratch = reg.root / "jobs" / run / job["attempt_id"]
    scratch.mkdir(parents=True)
    reg.start_job(run, job["attempt_id"], job["fence"], os.getpid(), scratch)
    result = reg.artifacts.put_json({"outcome": "INCONCLUSIVE"})
    _atomic_json(
        scratch / "published.json",
        {
            "run_id": run,
            "attempt_id": job["attempt_id"],
            "fence": job["fence"],
            "result_ref": plain(result),
        },
    )
    monkeypatch.setattr("butterfly_lab.registry.process_alive", lambda *_: False)
    assert reg.reconcile()[0]["state"] == "COMPLETED"
    assert reg.ingest(run)["outcome"] == "INCONCLUSIVE"


def test_running_child_without_supervisor_stays_unresolved(tmp_path, monkeypatch):
    reg, exp, data = setup_registry(tmp_path)
    run = register(reg, exp, data)
    job = reg.claim("owner", os.getpid())
    reg.start_job(run, job["attempt_id"], job["fence"], os.getpid(), reg.root / "scratch")
    values = iter([False, True])
    monkeypatch.setattr("butterfly_lab.registry.process_alive", lambda *_: next(values))
    assert reg.reconcile()[0]["state"] == "LOST_UNRESOLVED"
    assert reg.claim("replacement", os.getpid()) is None
