import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from butterfly_lab.agents import load_seeds
from butterfly_lab.confirmation import ConfirmationError, ConfirmationService
from butterfly_lab.registry import Registry
from butterfly_lab.schemas import (
    CampaignSpec,
    DatasetManifest,
    ExperimentSpec,
    ValidationReport,
    digest,
)
from butterfly_lab.security import BoundaryUnavailable, verify_boundary


def require_boundary():
    try:
        verify_boundary()
    except BoundaryUnavailable as exc:
        pytest.skip("Protected operation correctly unavailable on this host: " + str(exc))


def setup_service(tmp_path, *, exposed=False, panel=None, claims_count=1, alpha=0.05):
    registry = Registry(tmp_path / "runtime")
    store = registry.artifacts
    registry.put(
        "campaign",
        "C",
        CampaignSpec(
            id="C",
            objective="Frozen fixture confirmation",
            approved=True,
            budget={"max_runs": 10, "cpu_seconds": 600, "storage_bytes": 200_000_000},
        ),
    )
    claim_specs = []
    dataset_id = "D-final"
    seeds = load_seeds(Path(__file__).parents[1] / "configs" / "seeds.json", "C")
    for i in range(claims_count):
        hyp = seeds[i]
        registry.put("hypothesis", hyp.id, hyp)
        exp = ExperimentSpec(
            id=f"E{i}",
            campaign_id="C",
            hypothesis_id=hyp.id,
            trial_id=f"T{i}",
            dataset_id="D-dev",
            evaluator="controlled",
            fidelity="F0",
        )
        registry.put("experiment", exp.id, exp)
        evidence = store.put_json(
            {"experiment_id": exp.id, "independent_fixture_reconstruction": True}
        )
        validation = ValidationReport(
            id="replication-" + exp.id,
            subject_ref=evidence,
            checks=[
                {
                    "name": "independent_reconstruction",
                    "passed": True,
                    "detail": "Controlled fixture independently constructed",
                }
            ],
            evaluator_version="1",
            reviewer_identity="independent-fixture",
            status="PASS",
            permitted_evidence_ceiling={
                "implementation": "verified",
                "fidelity": "F0",
                "independence": "development",
                "precision": "informative",
                "replication": "independently_reconstructed",
            },
        )
        registry.put("validation", validation.id, validation)
        claim_specs.append(
            {
                "hypothesis_id": hyp.id,
                "experiment_hash": digest(exp.model_dump(mode="json")),
                "implementation_hash": exp.implementation_hash,
                "replication_report_id": validation.id,
                "replication_passed": True,
                "practical_effect": 0.05,
                "higher_is_better": False,
            }
        )
    if panel is None:
        sessions = [(date(2027, 1, 1) + timedelta(days=i)).isoformat() for i in range(40)]
        panel = {
            "claims": {
                row["hypothesis_id"]: {
                    "session_ids": sessions,
                    "baseline": [1.0] * 40,
                    "candidate": [0.5 + (i % 4) * 0.01 for i in range(40)],
                }
                for row in claim_specs
            }
        }
    source = tmp_path / "segregated-final.json"
    source.write_text(json.dumps(panel))
    manifest = DatasetManifest(
        id=dataset_id,
        kind="session_panel",
        source_path=str(source),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        fidelity="F0",
        provenance="SYNTHETIC",
        partition="confirmation",
        prior_exposed=exposed,
        metadata={"unexamined_attestation": True},
    )
    registry.put("dataset", dataset_id, manifest)
    service = ConfirmationService(registry, store, b"s" * 32, "authorization-fixture-secret")
    return service, claim_specs, source, {"alpha": alpha, "bootstrap_samples": 999}


def release(service, claims, inference):
    service.freeze("B", "C", "D-final", claims, inference)
    return service.authorize(
        "B",
        "human-reviewer",
        (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        "authorization-fixture-secret",
    )["signature"]


def test_frozen_authorized_confirmation_computes_holm_and_single_bundle(tmp_path):
    require_boundary()
    service, claims, _, inference = setup_service(tmp_path, claims_count=2)
    token = release(service, claims, inference)
    result = service.evaluate("B", token)
    assert result["protected_confirmation"] and result["synthetic_demonstration"]
    assert len(result["claims"]) == 2
    assert all(row["holm_adjusted_p"] >= row["p_value"] for row in result["claims"])
    assert all(
        row["demonstration_outcome"] == "INDEPENDENTLY_SUPPORTED" for row in result["claims"]
    )
    assert all(row["outcome"] == "EXPLORATORY_SUPPORTED" for row in result["claims"])
    assert service.evaluate("B", token) == result  # idempotent read, no recomputation
    assert service.report("B") == result
    assert len([r for r in service.registry.list("confirmation") if r.get("kind") == "result"]) == 1
    findings = service.publish_findings("B")
    assert len(findings) == 2 and all(f["evidence_grade"]["fidelity"] == "F0" for f in findings)
    assert service.publish_findings("B") == findings


def test_unauthorized_or_changed_finalists_never_evaluate(tmp_path):
    service, claims, _, inference = setup_service(tmp_path)
    service.freeze("B", "C", "D-final", claims, inference)
    with pytest.raises(PermissionError):
        service.authorize(
            "B",
            "researcher",
            (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "wrong-secret",
        )
    with pytest.raises(PermissionError):
        service.evaluate("B", "invented-token")
    changed = [{**claims[0], "implementation_hash": "changed"}]
    with pytest.raises(ConfirmationError, match="registered implementation"):
        service.freeze("other", "C", "D-final", changed, inference)
    assert not service.registry.list("exposure")


def test_exposed_history_and_unreplicated_claims_blocked(tmp_path):
    service, claims, _, inference = setup_service(tmp_path, exposed=True)
    assert not service.eligibility("D-final")[0]
    with pytest.raises(ConfirmationError, match="unexamined"):
        service.freeze("B", "C", "D-final", claims, inference)
    claims[0]["replication_passed"] = False
    with pytest.raises(ConfirmationError, match="replication"):
        service.freeze("B", "C", "D-final", claims, inference)


def test_consumed_bytes_cannot_be_renamed_pristine_and_descendants_tracked(tmp_path):
    require_boundary()
    service, claims, _, inference = setup_service(tmp_path)
    service.evaluate("B", release(service, claims, inference))
    renamed = {**service.registry.get("dataset", "D-final"), "id": "renamed-partition"}
    service.registry.put("dataset", renamed["id"], renamed)
    assert not service.eligibility(renamed["id"])[0]
    with pytest.raises(ConfirmationError, match="consumed"):
        service.freeze("again", "C", renamed["id"], claims, inference)
    lineage_id = service.register_descendant("B", "H-descendant")
    assert service.registry.get("lineage", lineage_id)["requires_new_confirmation_data"]


def test_missing_targets_and_changed_bytes_remain_consumed(tmp_path):
    require_boundary()
    service, claims, source, inference = setup_service(tmp_path)
    token = release(service, claims, inference)
    source.write_text("modified after freeze")
    with pytest.raises(ConfirmationError, match="remains consumed"):
        service.evaluate("B", token)
    assert not service.eligibility("D-final")[0]
    with pytest.raises(ConfirmationError, match="consumed"):
        service.evaluate("B", token)


def test_null_missing_targets_not_dropped(tmp_path):
    require_boundary()
    sessions = [(date(2027, 1, 1) + timedelta(days=i)).isoformat() for i in range(40)]
    panel = {
        "claims": {
            "C-H001": {
                "session_ids": sessions,
                "baseline": [1.0] * 40,
                "candidate": [0.5] * 39 + [None],
            }
        }
    }
    service, claims, _, inference = setup_service(tmp_path, panel=panel)
    with pytest.raises(ConfirmationError, match="remains consumed"):
        service.evaluate("B", release(service, claims, inference))


def test_insufficient_precision_is_not_automatic_rejection(tmp_path):
    require_boundary()
    sessions = [(date(2027, 1, 1) + timedelta(days=i)).isoformat() for i in range(40)]
    # Alternating blocks give a wide paired uncertainty interval spanning the hurdle.
    candidate = [1 + (1 if (i // 5) % 2 else -1) for i in range(40)]
    panel = {
        "claims": {
            "C-H001": {"session_ids": sessions, "baseline": [1.0] * 40, "candidate": candidate}
        }
    }
    service, claims, _, inference = setup_service(tmp_path, panel=panel)
    result = service.evaluate("B", release(service, claims, inference))
    assert result["claims"][0]["outcome"] == "INCONCLUSIVE"


def test_confirmation_requires_enforceable_boundary(tmp_path, monkeypatch):
    service, claims, _, inference = setup_service(tmp_path)
    token = release(service, claims, inference)

    def unavailable():
        raise BoundaryUnavailable("test host has no sandbox")

    monkeypatch.setattr("butterfly_lab.confirmation.verify_boundary", unavailable)
    with pytest.raises(BoundaryUnavailable):
        service.evaluate("B", token)
    assert service.eligibility("D-final")[0]  # no sensitive access took place


def test_program_error_budget_cannot_be_repeated_until_success(tmp_path):
    service, claims, _, inference = setup_service(tmp_path)
    release(service, claims, inference)
    service.freeze("second", "C", "D-final", claims, inference)
    with pytest.raises(ConfirmationError, match="error budget"):
        service.authorize(
            "second",
            "reviewer",
            (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "authorization-fixture-secret",
        )


def test_raw_four_leg_confirmation_runs_protected_evaluator(tmp_path):
    require_boundary()
    from butterfly_lab.fixtures import default_ironfly_parameters, generate_option_fixture

    service, claims, _, inference = setup_service(tmp_path)
    manifest = generate_option_fixture(tmp_path / "protected-option-quotes.parquet", sessions=30)
    manifest.update(id="raw-final", partition="confirmation", prior_exposed=False)
    manifest["metadata"].update(
        unexamined_attestation=True, confirmation_session_dates=manifest["session_dates"]
    )
    service.registry.put("dataset", manifest["id"], manifest)
    experiment = ExperimentSpec(
        id="raw-exp",
        campaign_id="C",
        hypothesis_id=claims[0]["hypothesis_id"],
        trial_id="raw-trial",
        dataset_id="D-dev",
        evaluator="iron_butterfly",
        fidelity="F0",
        parameters=default_ironfly_parameters(),
        dsl=default_ironfly_parameters(),
    )
    service.registry.put("experiment", experiment.id, experiment)
    previous = service.registry.get("validation", claims[0]["replication_report_id"])
    validation = {**previous, "id": "replication-raw-exp"}
    service.registry.put("validation", validation["id"], validation)
    claim = {
        **claims[0],
        "experiment_hash": digest(experiment.model_dump(mode="json")),
        "replication_report_id": validation["id"],
        "higher_is_better": True,
    }
    service.freeze("raw", "C", "raw-final", [claim], inference)
    approval = service.authorize(
        "raw",
        "fixture-human",
        (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        "authorization-fixture-secret",
    )
    result = service.evaluate("raw", approval["signature"])
    assert result["claims"][0]["sessions"] == 30
    assert result["synthetic_demonstration"]
    assert result["protected_artifact_refs"]
    assert service.artifacts.verify_tree(result["protected_artifact_refs"]) >= 4


def test_frozen_confirmation_runtime_rejects_changed_scientific_code(tmp_path, monkeypatch):
    service, claims, _, inference = setup_service(tmp_path)
    token = release(service, claims, inference)
    monkeypatch.setattr("butterfly_lab.confirmation.evaluator_hash", lambda: "changed")
    with pytest.raises(ConfirmationError, match="frozen runtime"):
        service.evaluate("B", token)
    assert not service.registry.list("exposure")


def test_relative_effect_uses_baseline_scale_not_currency_units(tmp_path):
    require_boundary()
    sessions = [(date(2027, 1, 1) + timedelta(days=i)).isoformat() for i in range(40)]
    panel = {
        "claims": {
            "C-H001": {"session_ids": sessions, "baseline": [100.0] * 40, "candidate": [96.0] * 40}
        }
    }
    service, claims, _, inference = setup_service(tmp_path, panel=panel)
    claims[0].update(effect_scale="relative_baseline", practical_effect=0.05)
    result = service.evaluate("B", release(service, claims, inference))
    assert result["claims"][0]["estimate"] == pytest.approx(0.04)
    assert result["claims"][0]["outcome"] == "REJECTED_FINDING"
