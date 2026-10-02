import copy

import pandas as pd
import pytest

from butterfly_lab.replication import replicate_accounting, replicate_controlled


def test_replication_detects_double_lot_and_missing_cash():
    fills = pd.DataFrame(
        [
            {
                "policy": "hold",
                "cycle_id": "c",
                "contract_id": "x",
                "units": 10,
                "price": 10,
                "fees": 1,
            },
            {
                "policy": "hold",
                "cycle_id": "c",
                "contract_id": "x",
                "units": -10,
                "price": 11,
                "fees": 1,
            },
        ]
    )
    ledger = pd.DataFrame([{"policy": "hold", "opportunity_id": "c", "pnl_inr": 8}])
    assert replicate_accounting(fills, ledger)["status"] == "PASS"
    ledger["pnl_inr"] = 80
    assert replicate_accounting(fills, ledger)["status"] == "FAIL"
    assert replicate_accounting(fills.iloc[:1], ledger)["status"] == "FAIL"


def test_replication_detects_changed_reported_metric():
    rows = pd.DataFrame({"baseline_loss": [1, 2, 3], "candidate_loss": [1, 2, 3]})
    assert replicate_controlled(rows, 0)["status"] == "PASS"
    assert replicate_controlled(rows, 0.1)["status"] == "FAIL"


def test_independent_accounting_rejects_balanced_but_backdated_fill_path():
    fills = pd.DataFrame(
        [
            {
                "policy": "hold",
                "cycle_id": "c",
                "contract_id": "x",
                "units": 10,
                "price": 10,
                "fees": 1,
                "timestamp": "2025-01-02T10:01:00+05:30",
            },
            {
                "policy": "hold",
                "cycle_id": "c",
                "contract_id": "x",
                "units": -10,
                "price": 11,
                "fees": 1,
                "timestamp": "2025-01-02T10:00:00+05:30",
            },
        ]
    )
    ledger = pd.DataFrame([{"policy": "hold", "opportunity_id": "c", "pnl_inr": 8}])
    report = replicate_accounting(fills, ledger)
    assert report["status"] == "FAIL"
    assert "chronology" in report["disagreements"][0]


def registered_fixture(tmp_path, evaluator="controlled"):
    from butterfly_lab.artifacts import ArtifactStore, plain
    from butterfly_lab.evaluators import evaluate
    from butterfly_lab.fixtures import (
        default_ironfly_parameters,
        generate_option_fixture,
        generate_spot_fixture,
    )

    if evaluator == "exp001":
        dataset = generate_spot_fixture(tmp_path / "spot.csv")
        params = {}
    elif evaluator == "iron_butterfly":
        dataset = generate_option_fixture(tmp_path / "option.parquet", 2)
        params = default_ironfly_parameters()
    else:
        dataset = {
            "kind": "synthetic",
            "fidelity": "F0",
            "provenance": "SYNTHETIC",
            "metadata": {"generator": "controlled_session_panel_v1"},
        }
        params = {"n_sessions": 48, "effect": -0.1, "noise": 0.01}
    experiment = {
        "evaluator": evaluator,
        "parameters": params,
        "baseline_id": "B0-simple",
        "seed": 17,
        "inference": {"bootstrap_samples": 99},
    }
    output = tmp_path / "output"
    result = evaluate(experiment, dataset, output)
    store = ArtifactStore(tmp_path / "artifacts")
    result["artifacts"] = {
        name: plain(store.put_file(output / relative, "application/vnd.apache.parquet"))
        for name, relative in result["artifacts"].items()
    }
    return result, experiment, dataset, store


@pytest.mark.parametrize("evaluator", ["controlled", "exp001", "iron_butterfly"])
def test_post_role_reconstruction_uses_only_registered_artifacts(tmp_path, monkeypatch, evaluator):
    from butterfly_lab.replication import verify_registered_reconstruction

    result, experiment, dataset, store = registered_fixture(tmp_path, evaluator)

    def forbidden(*args, **kwargs):
        raise AssertionError("Reconstruction must not read raw data or rerun evaluator")

    monkeypatch.setattr("butterfly_lab.data.load_dataset", forbidden)
    monkeypatch.setattr("butterfly_lab.evaluators.evaluate", forbidden)
    dataset["source_path"] = "/forbidden/private/confirmation/.env"
    report = verify_registered_reconstruction(result, experiment, dataset, store)
    assert report["status"] == "PASS", report
    assert report["artifact_refs"]
    assert report["observed"]["rows"] <= report["bounds"]["rows"]
    assert "/forbidden" not in str(report)
    # A balanced result with a corrupted aggregate estimate must still fail.
    changed = copy.deepcopy(result)
    changed["inference"]["estimate"] += 0.2
    assert verify_registered_reconstruction(changed, experiment, dataset, store)["status"] == "FAIL"


def test_post_role_reconstruction_rejects_protected_data_before_artifact_read(
    tmp_path, monkeypatch
):
    from butterfly_lab.replication import verify_registered_reconstruction

    result, experiment, dataset, store = registered_fixture(tmp_path)
    dataset["partition"] = "confirmation"

    def forbidden(*args, **kwargs):
        raise AssertionError("Protected partition must be rejected before artifact reads")

    monkeypatch.setattr(store, "path", forbidden)
    report = verify_registered_reconstruction(result, experiment, dataset, store)
    assert report["status"] == "FAIL"
    assert "Protected confirmation" in report["disagreements"][0]


def test_post_role_reconstruction_checks_hash_and_resource_bounds(tmp_path):
    from butterfly_lab.replication import verify_registered_reconstruction

    result, experiment, dataset, store = registered_fixture(tmp_path)
    bounded = {**experiment, "resources": {"storage_bytes": 1}}
    report = verify_registered_reconstruction(result, bounded, dataset, store)
    assert report["status"] == "FAIL" and "byte bound" in report["disagreements"][0]
    path = store.path(result["artifacts"]["session_outcomes"])
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b"corrupt")
    report = verify_registered_reconstruction(result, experiment, dataset, store)
    assert report["status"] == "FAIL" and "hash verification" in report["disagreements"][0]


def test_post_role_exp001_reconstructs_loss_not_just_reported_mean(tmp_path):
    from butterfly_lab.artifacts import plain
    from butterfly_lab.replication import verify_registered_reconstruction

    result, experiment, dataset, store = registered_fixture(tmp_path, "exp001")
    predictions = pd.read_parquet(store.path(result["artifacts"]["predictions"]))
    predictions.loc[predictions.index[0], "baseline_prediction"] *= 2
    path = tmp_path / "changed.parquet"
    predictions.to_parquet(path, index=False)
    result["artifacts"]["predictions"] = plain(
        store.put_file(path, "application/vnd.apache.parquet")
    )
    report = verify_registered_reconstruction(result, experiment, dataset, store)
    assert report["status"] == "FAIL" and "original-scale loss" in report["disagreements"][0]


def test_post_role_ironfly_reconstructs_primitive_fills_not_cached_pass(tmp_path):
    from butterfly_lab.artifacts import plain
    from butterfly_lab.replication import verify_registered_reconstruction

    result, experiment, dataset, store = registered_fixture(tmp_path, "iron_butterfly")
    fills = pd.read_parquet(store.path(result["artifacts"]["fills"]))
    fills.loc[fills.index[0], "fees"] += 1
    path = tmp_path / "changed.parquet"
    fills.to_parquet(path, index=False)
    result["artifacts"]["fills"] = plain(store.put_file(path, "application/vnd.apache.parquet"))
    assert result["replication"]["status"] == "PASS"
    report = verify_registered_reconstruction(result, experiment, dataset, store)
    assert report["status"] == "FAIL" and "decimal accounting" in report["disagreements"][0]
