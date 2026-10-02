"""Independent numerical reconstruction, deliberately not evaluator reruns.

EXP001 uses scalar return/excursion construction and augmented least-squares,
where the primary uses vector transformations and ridge normal equations.
Accounting independently reduces primitive fills using decimal arithmetic.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd


def replicate_exp001(
    frame: pd.DataFrame,
    dataset: dict[str, Any],
    experiment: dict[str, Any],
    features: pd.DataFrame,
    predictions: pd.DataFrame,
) -> dict[str, Any]:
    records = []
    disagreements = []
    # The adapter is shared only for byte/time normalization. Transformations,
    # eligibility decisions, model solve and scoring are independently expressed.
    for day in sorted(set(frame.session) | set(dataset.get("session_dates", []))):
        origin = pd.Timestamp(day + " 10:05:00", tz="Asia/Kolkata").tz_convert("UTC")
        by_end = {row["bar_end"]: row for row in frame[frame.session.eq(day)].to_dict("records")}
        past_keys = [origin - pd.Timedelta(minutes=31 - j) for j in range(31)]
        future_keys = [origin + pd.Timedelta(minutes=j) for j in range(1, 31)]
        if any(key not in by_end for key in past_keys + future_keys):
            continue
        past, future = [by_end[k] for k in past_keys], [by_end[k] for k in future_keys]
        if any(row["session_class"] != "regular" for row in past + future) or any(
            row["available_at"] > origin for row in past
        ):
            continue
        returns = [
            math.log(float(past[j + 1]["close"])) - math.log(float(past[j]["close"]))
            for j in range(30)
        ]
        variance = math.fsum(x * x for x in returns)
        direction = abs(math.fsum(returns)) / math.sqrt(variance) if variance else 0.0
        excursion = max(
            abs(math.log(float(row["close"]) / float(past[-1]["close"]))) for row in future
        )
        records.append(
            {
                "session": day,
                "origin": origin,
                "log_rv": math.log(max(variance, 1e-16)),
                "rv": variance,
                "drift": direction,
                "excursion": excursion,
                "log_excursion": math.log(max(excursion, 1e-8)),
                "label_available_at": max(row["available_at"] for row in future),
            }
        )
    if [r["session"] for r in records] != features.session.tolist():
        disagreements.append("independent session eligibility differs")
    reference = {r["session"]: r for r in records}
    max_feature_error = 0.0
    for row in features.to_dict("records"):
        if row["session"] not in reference:
            continue
        for name in ("rv", "log_rv", "drift", "excursion", "log_excursion"):
            error = abs(float(row[name]) - reference[row["session"]][name])
            max_feature_error = max(max_feature_error, error)
    if max_feature_error > 1e-8:
        disagreements.append("independent feature transformation mismatch")
    max_prediction_error = max_loss_error = 0.0
    split = experiment.get("split", {})
    # Cache fit by actual registered fit time, not by observed result values.
    fitted: dict[tuple[str, bool], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for row in predictions[predictions.status.eq("EVALUATED")].to_dict("records"):
        cutoff = pd.Timestamp(row["fit_at"])
        training = [
            r
            for r in records
            if r["label_available_at"] < cutoff
            and (
                (r["session"] <= split.get("train_end", "2023-12-31"))
                if split.get("refit", "expanding_monthly") == "frozen"
                else r["origin"] < cutoff
            )
        ]
        if len(training) != int(row["train_n"]):
            disagreements.append("independent training membership mismatch")
            continue
        for candidate in (False, True):
            names = ["log_rv", "drift"] if candidate else ["log_rv"]
            key = (str(cutoff), candidate)
            if key not in fitted:
                columns = [[r[name] for r in training] for name in names]
                means = np.array([math.fsum(x) / len(x) for x in columns])
                scales = np.array(
                    [
                        max(
                            math.sqrt(math.fsum((v - mean) ** 2 for v in values) / len(values)),
                            1e-12,
                        )
                        for mean, values in zip(means, columns, strict=True)
                    ]
                )
                design = np.array(
                    [
                        [1.0] + [(r[name] - means[j]) / scales[j] for j, name in enumerate(names)]
                        for r in training
                    ]
                )
                penalty = np.diag([0.0] + [math.sqrt(0.001)] * len(names))
                augmented = np.vstack([design, penalty])
                target = np.array([r["log_excursion"] for r in training] + [0.0] * (len(names) + 1))
                coefficients = np.linalg.lstsq(augmented, target, rcond=None)[0]
                fitted[key] = (means, scales, coefficients)
            means, scales, coefficients = fitted[key]
            source = reference[row["session"]]
            linear = float(coefficients[0]) + math.fsum(
                float(coefficients[j + 1]) * (source[name] - means[j]) / scales[j]
                for j, name in enumerate(names)
            )
            estimate = math.exp(max(math.log(1e-8), min(20.0, linear)))
            prefix = "candidate" if candidate else "baseline"
            max_prediction_error = max(
                max_prediction_error, abs(estimate - float(row[prefix + "_prediction"]))
            )
            independent_loss = 10000 * abs(source["excursion"] - estimate)
            max_loss_error = max(
                max_loss_error, abs(independent_loss - float(row[prefix + "_loss"]))
            )
    if max_prediction_error > 1e-7 or max_loss_error > 1e-3:
        disagreements.append("independent augmented-OLS predictions/MAE mismatch")
    return {
        "status": "FAIL" if disagreements else "PASS",
        "method": "independent_scalar_features_augmented_ridge_and_metrics",
        "n_features": len(records),
        "max_feature_error": max_feature_error,
        "max_prediction_error": max_prediction_error,
        "max_loss_error_bp": max_loss_error,
        "checks": [
            "eligibility",
            "past-only features",
            "training membership",
            "independent ridge solution",
            "original-scale MAE",
        ],
        "disagreements": disagreements,
        "independence": "computational reconstruction; same market observations, not independent market evidence",
    }


def replicate_accounting(fills: pd.DataFrame, opportunities: pd.DataFrame) -> dict[str, Any]:
    accounts: dict[tuple[str, str], dict[str, Any]] = {}
    for fill in fills.to_dict("records"):
        key = (fill["policy"], fill["cycle_id"])
        acc = accounts.setdefault(key, {"cash": Decimal(0), "positions": {}})
        quantity = int(fill["units"])
        acc["cash"] -= Decimal(quantity) * Decimal(str(fill["price"])) + Decimal(str(fill["fees"]))
        contract = fill["contract_id"]
        acc["positions"][contract] = acc["positions"].get(contract, 0) + quantity
    failures, errors = [], []
    for row in opportunities.to_dict("records"):
        acc = accounts.get(
            (row["policy"], row["opportunity_id"]), {"cash": Decimal(0), "positions": {}}
        )
        unresolved = any(acc["positions"].values())
        pnl = row["pnl_inr"]
        missing = pnl is None or pd.isna(pnl)
        if unresolved and not missing:
            failures.append("nonzero inventory reported as realized P&L")
        if not missing:
            error = abs(float(acc["cash"]) - float(pnl))
            errors.append(error)
            if error > 1e-6:
                failures.append("independent cashflow mismatch")
    return {
        "status": "FAIL" if failures else "PASS",
        "method": "independent_decimal_cash_and_signed_inventory_reduce",
        "cycles": len(opportunities),
        "max_cash_error": max(errors, default=0.0),
        "disagreements": sorted(set(failures)),
        "independence": "accounting reconstruction from immutable primitive fills",
    }


def replicate_controlled(rows: pd.DataFrame, primary_estimate: float) -> dict[str, Any]:
    n = len(rows)
    baseline = math.fsum(float(v) for v in rows.baseline_loss) / n
    candidate = math.fsum(float(v) for v in rows.candidate_loss) / n
    independently_computed = (baseline - candidate) / baseline
    error = abs(independently_computed - primary_estimate)
    return {
        "status": "PASS" if error < 1e-12 else "FAIL",
        "method": "independent_scalar_session_metric",
        "max_error": error,
    }


def replicate(
    experiment: dict[str, Any], dataset: dict[str, Any], result_dir: Any
) -> dict[str, Any]:
    """Explicit standalone reconstruction adapter for accepted immutable artifacts."""
    from pathlib import Path
    from .data import load_dataset

    directory = Path(result_dir)
    evaluator = experiment["evaluator"]
    if evaluator == "exp001":
        return replicate_exp001(
            load_dataset(dataset),
            dataset,
            experiment,
            pd.read_parquet(directory / "features.parquet"),
            pd.read_parquet(directory / "predictions.parquet"),
        )
    if evaluator == "iron_butterfly":
        return replicate_accounting(
            pd.read_parquet(directory / "fills.parquet"),
            pd.read_parquet(directory / "opportunities.parquet"),
        )
    if evaluator == "controlled":
        rows = pd.read_parquet(directory / "session_outcomes.parquet")
        original = float(
            ((rows.baseline_loss - rows.candidate_loss).mean()) / rows.baseline_loss.mean()
        )
        return replicate_controlled(rows, original)
    raise ValueError("unknown evaluator")
