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


def test_relative_bootstrap_resamples_denominator_not_fixed_original_mean():
    baseline = np.geomspace(0.01, 100, 80)
    candidate = 0.9 * baseline
    result = paired_inference(baseline, candidate, repetitions=199, block_length=4)
    # Every resampled ratio equals 10%; the level variation is irrelevant to
    # this statistic and must not manufacture a wide confidence interval.
    assert result["estimate"] == pytest.approx(0.1)
    assert result["ci_low"] == pytest.approx(0.1)
    assert result["ci_high"] == pytest.approx(0.1)


def test_relative_bootstrap_matches_independent_paired_ratio_reconstruction():
    baseline = np.array([1.0, 8.0, 0.5, 3.0, 0.3] * 12)
    candidate = np.array([0.6, 7.0, 0.7, 2.5, 0.2] * 12)
    seed, repetitions, length = 71, 199, 3
    result = paired_inference(
        baseline, candidate, seed=seed, repetitions=repetitions, block_length=length
    )
    starts = np.random.default_rng(seed).integers(
        0, len(baseline), size=(repetitions, len(baseline) // length)
    )
    reconstructed = []
    for draw in starts:
        indices = [
            (int(start) + offset) % len(baseline) for start in draw for offset in range(length)
        ]
        b = sum(float(baseline[i]) for i in indices)
        c = sum(float(candidate[i]) for i in indices)
        reconstructed.append((b - c) / b)
    lo, hi = np.quantile(reconstructed, [0.025, 0.975])
    assert (result["ci_low"], result["ci_high"]) == pytest.approx((lo, hi))


def test_undefined_relative_resamples_are_not_dropped_to_manufacture_precision():
    baseline = np.array([0.0] * 39 + [1.0])
    result = paired_inference(baseline, baseline * 0.8, repetitions=199, block_length=1)
    assert result["outcome"] == "INCONCLUSIVE"
    assert result["invalid_resamples"] > 0
    assert result["ci_low"] is result["ci_high"] is result["p_value"] is None
