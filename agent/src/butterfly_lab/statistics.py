"""Session-paired estimands with fixed circular moving-block inference."""

from __future__ import annotations

from typing import Any

import numpy as np


def paired_inference(
    baseline: list[float] | np.ndarray,
    candidate: list[float] | np.ndarray,
    *,
    metric: str = "loss",
    block_length: int = 5,
    repetitions: int = 999,
    seed: int = 1729,
    practical_effect: float = 0.01,
    relative: bool = True,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Positive change means improvement; no dropping unmatched/nonfinite sessions.

    For loss, change = baseline-candidate. For P&L, candidate-baseline.
    Relative loss improvement divides by mean baseline loss, not each observation.
    Null-centered one-sided bootstrap tests the registered practical hurdle.
    """
    b, c = np.asarray(baseline, dtype=float), np.asarray(candidate, dtype=float)
    if b.ndim != 1 or b.shape != c.shape or not len(b):
        raise ValueError("paired nonempty vectors with identical opportunity sets required")
    if not np.isfinite(b).all() or not np.isfinite(c).all():
        raise ValueError("missing/unresolved outcomes cannot be dropped from inference")
    if block_length < 1 or repetitions < 99 or not 0 < alpha < 1:
        raise ValueError("invalid registered inference parameters")
    if metric not in {"loss", "pnl"}:
        raise ValueError("metric must be loss or pnl")
    denominator = float(b.mean()) if relative else 1.0
    if denominator <= 0 and relative:
        return {
            "n_sessions": len(b),
            "estimate": None,
            "ci_low": None,
            "ci_high": None,
            "p_value": None,
            "outcome": "INCONCLUSIVE",
            "reason": "relative baseline denominator nonpositive",
            "practical_effect": practical_effect,
        }
    delta = b - c if metric == "loss" else c - b
    n, length = len(delta), min(block_length, len(delta))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(repetitions, int(np.ceil(n / length))))
    indices = ((starts[:, :, None] + np.arange(length)) % n).reshape(repetitions, -1)[:, :n]
    estimate = float(delta.mean() / denominator)
    # Resample paired observations and recompute the *registered statistic*.
    # Fixing the denominator at its full-sample value is not a bootstrap of
    # relative improvement and gives spurious uncertainty for c = constant * b.
    draw_denominators = b[indices].mean(axis=1) if relative else np.ones(repetitions)
    if (draw_denominators <= 0).any():
        return {
            "n_sessions": n,
            "estimate": estimate,
            "ci_low": None,
            "ci_high": None,
            "p_value": None,
            "outcome": "INCONCLUSIVE",
            "precision": "insufficient",
            "reason": "relative baseline denominator nonpositive in registered resamples",
            "invalid_resamples": int(np.count_nonzero(draw_denominators <= 0)),
            "practical_effect": practical_effect,
            "relative": relative,
            "unit": "session",
            "block_length": length,
            "repetitions": repetitions,
            "seed": seed,
        }
    draws = delta[indices].mean(axis=1) / draw_denominators
    low, high = np.quantile(draws, [alpha / 2, 1 - alpha / 2])
    centered = draws - estimate
    p = float((1 + np.count_nonzero(centered >= estimate - practical_effect)) / (repetitions + 1))
    adequate = n >= max(20, 4 * length)
    outcome = "INCONCLUSIVE"
    if adequate and high < practical_effect:
        outcome = "REJECTED_FINDING"
    elif adequate and low > practical_effect:
        outcome = "EXPLORATORY_SUPPORTED"
    return {
        "n_sessions": n,
        "estimate": estimate,
        "ci_low": float(low),
        "ci_high": float(high),
        "p_value": p,
        "outcome": outcome,
        "practical_effect": practical_effect,
        "relative": relative,
        "unit": "session",
        "block_length": length,
        "repetitions": repetitions,
        "seed": seed,
        "method": "circular_moving_block_percentile",
        "precision": "informative" if adequate else "insufficient",
        "limitations": [
            "Exploratory/post-selection intervals are descriptive",
            "Blocks assume local dependence regularity; absent crises are not synthesized",
        ],
    }


def holm(p_values: list[float], alpha: float = 0.05) -> dict[str, Any]:
    p = np.asarray(p_values, dtype=float)
    if p.ndim != 1 or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("valid finite p-values required")
    order = np.argsort(p, kind="stable")
    adjusted = np.empty(len(p))
    maximum = 0.0
    for rank, idx in enumerate(order):
        maximum = max(maximum, min(1.0, (len(p) - rank) * p[idx]))
        adjusted[idx] = maximum
    return {
        "adjusted_p_values": adjusted.tolist(),
        "rejected": (adjusted <= alpha).tolist(),
        "alpha": alpha,
        "method": "Holm",
    }


def robustness(
    baseline: list[float], candidate: list[float], plan: dict[str, Any], *, metric: str = "loss"
) -> dict[str, Any]:
    lengths = plan.get("block_lengths", [3, 5, 10])
    reports = {
        str(n): paired_inference(
            baseline,
            candidate,
            metric=metric,
            block_length=int(n),
            repetitions=int(plan.get("repetitions", 999)),
            seed=int(plan.get("seed", 1729)),
            practical_effect=float(plan.get("practical_effect", 0.01)),
            relative=bool(plan.get("relative", metric == "loss")),
            alpha=float(plan.get("alpha", 0.05)),
        )
        for n in lengths
    }
    for report in reports.values():
        report["minimum_sessions"] = int(plan.get("minimum_sessions", 30))
        if report["n_sessions"] < report["minimum_sessions"]:
            report.update(outcome="INCONCLUSIVE", precision="insufficient")
    return {
        "registered_checks": reports,
        "sign_stable": len(
            {np.sign(v["estimate"]) for v in reports.values() if v["estimate"] is not None}
        )
        <= 1,
    }


def negative_replication_sample(
    ids: list[str], fraction: float = 0.1, seed: int = 1729
) -> list[str]:
    """Preregistered seed selects negatives without reference to their magnitudes."""
    if not 0 <= fraction <= 1:
        raise ValueError("fraction out of range")
    ordered = sorted(set(ids))
    if not ordered or fraction == 0:
        return []
    rng = np.random.default_rng(seed)
    chosen = rng.choice(
        len(ordered), size=max(1, int(np.ceil(len(ordered) * fraction))), replace=False
    )
    return [ordered[int(i)] for i in sorted(chosen)]
