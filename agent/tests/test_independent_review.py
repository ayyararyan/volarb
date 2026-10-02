"""Cross-boundary acceptance checks, independent of individual helper implementations."""

from __future__ import annotations

import hashlib
import os

import pytest

from butterfly_lab.artifacts import digest
from butterfly_lab.config import environment_hash, evaluator_hash
from butterfly_lab.graph import Laboratory
from butterfly_lab.registry import BudgetExceeded, SourceBindingError, verify_source_binding
from butterfly_lab.workers import WorkerSupervisor
from test_graph import setup_lab
from test_registry import register, setup_registry


def test_unbound_external_input_never_reserves_or_submits(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    source = tmp_path / "unbound.json"
    source.write_text("[]")
    data = data.model_copy(update={"source_path": str(source)})
    with pytest.raises(SourceBindingError, match="source_sha256"):
        register(reg, exp, data)
    assert reg.runs() == []
    assert reg.status()["pending_outbox"] == 0
    assert reg.status()["budget_committed_upper_bounds"]["runs"] == 0


def test_protected_bytes_cannot_be_relabeled_as_development(tmp_path, monkeypatch):
    reg, exp, data = setup_registry(tmp_path)
    source = tmp_path / "protected.json"
    source.write_text("[]")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    protected = data.model_copy(
        update={
            "id": "sealed",
            "partition": "confirmation",
            "prior_exposed": False,
            "source_path": str(source),
            "source_sha256": sha,
        }
    )
    reg.put("dataset", protected.id, protected)
    alias = protected.model_copy(update={"id": data.id, "partition": "development"})

    def forbidden_read(_):
        raise AssertionError("Protected source was inspected before role authorization")

    monkeypatch.setattr("butterfly_lab.registry.verify_source_binding", forbidden_read)
    with pytest.raises(SourceBindingError, match="aliases"):
        register(reg, exp, alias)
    # Identical bytes under a different path are still a protected-source alias.
    alias = alias.model_copy(update={"source_path": str(tmp_path / "copied.json")})
    with pytest.raises(SourceBindingError, match="aliases"):
        register(reg, exp, alias)
    assert reg.runs() == []


def test_changed_source_between_admission_and_execution_is_not_an_economic_result(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    source = tmp_path / "input.json"
    source.write_text("[]")
    data = data.model_copy(
        update={
            "source_path": str(source),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    )
    run = reg.register_run(exp, data, environment_hash(), evaluator_hash())
    source.write_text("[{}]")
    assert WorkerSupervisor(reg.root).run_once()
    failed = reg.get_run(run)
    assert failed["state"] == "FAILED"
    assert failed["failure"]["kind"] == "SourceBindingError"
    assert failed["result_ref"] is None
    assert not WorkerSupervisor(reg.root).run_once()


def test_directory_binding_is_exact_and_rejects_extra_or_changed_members(tmp_path):
    directory = tmp_path / "partitioned"
    directory.mkdir()
    (directory / "a.csv").write_text("x\n1\n")
    members = {"a.csv": hashlib.sha256((directory / "a.csv").read_bytes()).hexdigest()}
    data = {
        "source_path": str(directory),
        "source_sha256": digest(members),
        "metadata": {"glob": "*.csv", "file_sha256": members},
    }
    assert verify_source_binding(data) == ((directory / "a.csv").resolve(),)
    (directory / "b.csv").write_text("x\n2\n")
    with pytest.raises(SourceBindingError, match="selected directory members"):
        verify_source_binding(data)
    (directory / "b.csv").rename(directory / "b.not-selected")
    (directory / "a.csv").write_text("x\n3\n")
    with pytest.raises(SourceBindingError, match="differ from registered hash"):
        verify_source_binding(data)


def test_cpu_reservation_uses_os_enforceable_rounding(tmp_path):
    reg, exp, data = setup_registry(tmp_path, cpu_seconds=1)
    exp = exp.model_copy(
        update={"resources": exp.resources.model_copy(update={"cpu_seconds": 0.01})}
    )
    register(reg, exp, data)
    assert reg.status()["budget_committed_upper_bounds"]["cpu_seconds"] == 1
    with pytest.raises(BudgetExceeded, match="cpu_seconds"):
        register(reg, exp.model_copy(update={"id": "second"}), data)


def test_cancelled_graph_survives_restart_without_computing(tmp_path):
    lab, campaign, _, _, exp = setup_lab(tmp_path)
    waiting = lab.run_experiment(exp.id)
    lab.registry.cancel_campaign(campaign.id)
    root = lab.root
    lab.close()
    assert not WorkerSupervisor(root).run_once()
    lab = Laboratory(root)
    try:
        final = lab.resume(exp.id)
        assert final["outcome"] == "CANCELLED"
        assert lab.registry.get_run(waiting["run_id"])["state"] == "CANCELLED"
        assert len(lab.registry.runs()) == 1
    finally:
        lab.close()


def test_campaign_concurrency_ceiling_cannot_be_overridden_by_worker_pool(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    # The default helper campaign ceiling is two; a third claim cannot be
    # authorized merely by increasing the worker's requested pool size.
    for index in range(3):
        register(reg, exp.model_copy(update={"id": f"exp-{index}"}), data)
    assert reg.claim("first", os.getpid(), max_concurrency=8)
    assert reg.claim("second", os.getpid(), max_concurrency=8)
    assert reg.claim("third", os.getpid(), max_concurrency=8) is None


def test_live_unresolved_slot_is_not_reallocated_after_restart(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    first = register(reg, exp, data)
    register(reg, exp.model_copy(update={"id": "second"}), data)
    claimed = reg.claim("live", os.getpid(), lease_seconds=0.001, max_concurrency=1)
    import time

    time.sleep(0.01)
    assert reg.reconcile()[0]["state"] == "LOST_UNRESOLVED"
    from butterfly_lab.registry import Registry

    reopened = Registry(reg.root)
    assert reopened.claim("restart", os.getpid(), max_concurrency=1) is None
    assert reopened.get_run(first)["fence"] == claimed["fence"]
