from butterfly_lab.evidence import classify
from butterfly_lab.evaluators import evaluate


def test_registered_minimum_sample_size_survives_numerical_result_and_grading(tmp_path):
    dataset = {
        "kind": "synthetic",
        "fidelity": "F0",
        "provenance": "SYNTHETIC",
        "metadata": {"generator": "controlled_session_panel_v1"},
    }
    result = evaluate(
        {
            "evaluator": "controlled",
            "seed": 17,
            "parameters": {"n_sessions": 35, "effect": 0.1, "noise": 0},
            "inference": {"minimum_sessions": 100, "bootstrap_samples": 99},
        },
        dataset,
        tmp_path,
    )
    assert result["inference"]["minimum_sessions"] == 100
    assert result["inference"]["outcome"] == "INCONCLUSIVE"
    assert classify(result, independent=True).value == "INCONCLUSIVE"
    assert all(
        check["minimum_sessions"] == 100 and check["outcome"] == "INCONCLUSIVE"
        for check in result["robustness"]["registered_checks"].values()
    )


def test_insufficient_effective_blocks_cannot_be_upgraded_by_evidence_layer():
    result = {
        "inference": {
            "n_sessions": 35,
            "minimum_sessions": 30,
            "ci_low": 0.1,
            "ci_high": 0.2,
            "practical_effect": 0.01,
            "block_length": 10,
            "precision": "insufficient",
            "outcome": "INCONCLUSIVE",
        },
    }
    assert classify(result, independent=True).value == "INCONCLUSIVE"
