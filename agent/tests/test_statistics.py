import numpy as np
import pytest

from butterfly_lab.statistics import holm, negative_replication_sample, paired_inference


def test_null_negative_and_planted_effects():
    baseline = np.ones(100)
    null = paired_inference(baseline, baseline, repetitions=199)
    assert null["outcome"] == "REJECTED_FINDING"  # exact null excludes 1% hurdle
    positive = paired_inference(baseline, baseline - 0.1, repetitions=199)
    assert positive["outcome"] == "EXPLORATORY_SUPPORTED"
    assert positive["ci_low"] == pytest.approx(0.1)
    small = paired_inference(baseline[:5], baseline[:5] - 0.1, repetitions=199)
    assert small["outcome"] == "INCONCLUSIVE"


def test_opportunity_mismatch_missing_and_seed_determinism():
    with pytest.raises(ValueError, match="paired"):
        paired_inference([1, 2], [1])
    with pytest.raises(ValueError, match="missing"):
        paired_inference([1, np.nan], [1, 2])
    b = np.linspace(0, 1, 100)
    assert paired_inference(b, b[::-1], seed=3) == paired_inference(b, b[::-1], seed=3)


def test_holm_and_negative_audit_sample():
    result = holm([0.001, 0.03, 0.2])
    assert result["adjusted_p_values"] == pytest.approx([0.003, 0.06, 0.2])
    assert result["rejected"] == [True, False, False]
    ids = [f"negative-{x}" for x in range(20)]
    assert len(negative_replication_sample(ids, 0.2, 3)) == 4
    assert negative_replication_sample(ids, 0.2, 3) == negative_replication_sample(
        ids[::-1], 0.2, 3
    )
