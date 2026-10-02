import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from butterfly_lab.compiler import validate_dsl
from butterfly_lab.config import runtime_root
from butterfly_lab.evidence import classify
from butterfly_lab.schemas import Quantity, Approval, EvidenceGrade, ResearchFinding


def test_unknown_units_extra_fields_and_aware_times():
    with pytest.raises(ValidationError):
        Quantity(value=None, unit="INR")
    with pytest.raises(ValidationError):
        Quantity(value=0, unit="INR", surprise=True)
    with pytest.raises(ValidationError):
        Quantity(value=float("nan"), unit="INR")
    assert Quantity(value=None, unit="INR", unknown_reason="historical fees absent").value is None
    with pytest.raises(ValidationError):
        Approval(
            id="a",
            scope="campaign",
            subject_hash="x",
            principal="user",
            approved_at="2026-01-01T00:00:00",
            expires_at="2026-01-02T00:00:00",
            signature="x",
        )


def test_prose_cannot_upgrade_evidence_or_insufficient_precision():
    grade = EvidenceGrade(
        implementation="verified",
        fidelity="F0",
        independence="development",
        precision="informative",
        replication="independently_reconstructed",
    )
    with pytest.raises(ValidationError):
        ResearchFinding(
            id="f",
            campaign_id="c",
            hypothesis_id="h",
            experiment_id="e",
            outcome="INDEPENDENTLY_SUPPORTED",
            claim="Model says proven!",
            evidence_grade=grade,
            dataset_id="d",
            search_family_id="s",
        )
    assert (
        classify(
            {
                "inference": {
                    "n_sessions": 100,
                    "ci_low": -0.1,
                    "ci_high": 0.2,
                    "practical_effect": 0.01,
                }
            },
            True,
        )
        == "INCONCLUSIVE"
    )
    assert (
        classify(
            {
                "inference": {
                    "n_sessions": 100,
                    "ci_low": -0.1,
                    "ci_high": 0,
                    "practical_effect": 0.01,
                }
            },
            True,
        )
        == "REJECTED_FINDING"
    )


def test_no_arbitrary_code_and_cloud_runtime(tmp_path):
    with pytest.raises(ValueError):
        validate_dsl({"evaluator": "controlled", "dsl": {"code": "print('bad')"}})
    with pytest.raises(ValueError):
        runtime_root(tmp_path / "CloudStorage" / "research")


def test_cli_help_schema_and_clean_error(tmp_path):
    root = tmp_path / "runtime"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "butterfly_lab.cli",
            "--root",
            str(root),
            "schemas",
            "--output",
            str(tmp_path / "schemas"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schemas"] >= 14
    assert (tmp_path / "schemas" / "ExperimentSpec.json").exists()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "butterfly_lab.cli",
            "--root",
            str(root),
            "data",
            "validate",
            str(tmp_path / "missing.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"] == "FileNotFoundError"


def test_environment_fingerprint_ignores_duplicate_import_paths(monkeypatch):
    import sys
    import butterfly_lab
    from pathlib import Path
    from butterfly_lab.config import environment_hash

    before = environment_hash()
    monkeypatch.setattr(sys, "path", [str(Path(butterfly_lab.__file__).parent.parent), *sys.path])
    assert environment_hash() == before
