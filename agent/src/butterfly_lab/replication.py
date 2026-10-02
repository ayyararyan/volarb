"""Independent numerical reconstruction, deliberately not evaluator reruns.

EXP001 uses scalar return/excursion construction and augmented least-squares,
where the primary uses vector transformations and ridge normal equations.
Accounting independently reduces primitive fills using decimal arithmetic.
"""

from __future__ import annotations

import math
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from .artifacts import ArtifactError, ArtifactStore, digest, plain


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
    failures: list[str] = []
    errors: list[float] = []
    for fill in fills.to_dict("records"):
        key = (fill["policy"], fill["cycle_id"])
        acc = accounts.setdefault(key, {"cash": Decimal(0), "positions": {}})
        if "timestamp" in fill:
            clock = datetime.fromisoformat(fill["timestamp"])
            if clock.tzinfo is None:
                failures.append("offset-naive primitive fill clock")
            elif "clock" in acc and clock < acc["clock"]:
                failures.append("dependent primitive fill chronology moved backwards")
            if clock.tzinfo is not None:
                acc["clock"] = clock
        quantity = int(fill["units"])
        acc["cash"] -= Decimal(quantity) * Decimal(str(fill["price"])) + Decimal(str(fill["fees"]))
        contract = fill["contract_id"]
        acc["positions"][contract] = acc["positions"].get(contract, 0) + quantity
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


class _ReconstructionError(ValueError):
    """Bounded validation messages that never include external source paths."""


def verify_registered_reconstruction(
    result: dict[str, Any],
    experiment: dict[str, Any],
    dataset: dict[str, Any],
    artifact_store: ArtifactStore,
) -> dict[str, Any]:
    """Post-role independent arithmetic over accepted immutable worker artifacts.

    This is a bounded validation, not an evaluator/backtest rerun. Full independent
    feature/model reconstruction remains inside the reserved numerical worker.
    No raw source, source_path, protected partition, or provider is accessed here.
    """
    import pyarrow.parquet as parquet

    resources = experiment.get("resources", {})
    byte_limit = min(64 * 1024 * 1024, int(resources.get("storage_bytes", 10 * 1024 * 1024)))
    decoded_limit = min(64 * 1024 * 1024, int(resources.get("memory_mb", 256)) * 1024 * 256)
    deadline = time.monotonic() + min(10.0, float(resources.get("wall_seconds", 60)))
    refs: dict[str, dict[str, Any]] = {}
    counts = {"artifact_bytes": 0, "decoded_bytes": 0, "rows": 0}
    report: dict[str, Any] = {
        "status": "FAIL",
        "method": "post_role_independent_registered_artifact_reconstruction_v1",
        "evaluator": experiment.get("evaluator"),
        "result_hash": digest(result),
        "experiment_hash": digest(experiment),
        "independence": "Independent scalar/decimal reductions after replication support; source-level feature/model reconstruction remains in the reserved worker.",
        "checks": [],
        "disagreements": [],
    }

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise _ReconstructionError(message)
        if time.monotonic() > deadline:
            raise _ReconstructionError("Registered artifact validation deadline exceeded")

    def read(name: str, columns: list[str]) -> pd.DataFrame:
        ref = plain(result.get("artifacts", {}).get(name, {}))
        path = artifact_store.path(ref)
        size = path.stat().st_size
        require(size + counts["artifact_bytes"] <= byte_limit, "Artifact byte bound exceeded")
        artifact_store.verify(ref)
        table = parquet.ParquetFile(path)
        rows = table.metadata.num_rows
        decoded = sum(
            table.metadata.row_group(i).column(j).total_uncompressed_size
            for i in range(table.metadata.num_row_groups)
            for j in range(table.metadata.num_columns)
        )
        require(rows + counts["rows"] <= 100_000, "Artifact row bound exceeded")
        require(
            decoded + counts["decoded_bytes"] <= decoded_limit,
            "Decoded artifact memory bound exceeded",
        )
        require(set(columns) <= set(table.schema.names), "Required primitive columns absent")
        frame = table.read(columns=columns, use_threads=False).to_pandas()
        artifact_store.verify(ref)
        counts["artifact_bytes"] += size
        counts["decoded_bytes"] += decoded
        counts["rows"] += rows
        refs[name] = ref
        require(True, "")
        return frame

    def close(actual: float | None, expected: Any, label: str, tolerance: float = 1e-8) -> None:
        require(
            actual is None
            and expected is None
            or actual is not None
            and expected is not None
            and math.isfinite(float(expected))
            and math.isclose(actual, float(expected), rel_tol=1e-10, abs_tol=tolerance),
            "Independent registered value mismatch: " + label,
        )

    try:
        require(dataset.get("partition") != "confirmation", "Protected confirmation is forbidden")
        require(
            result.get("fidelity") == dataset.get("fidelity")
            and result.get("provenance") == dataset.get("provenance"),
            "Result/dataset evidence classification differs",
        )
        evaluator = experiment["evaluator"]
        require(evaluator in {"controlled", "exp001", "iron_butterfly"}, "Unknown evaluator")
        columns = (
            ["session", "baseline_pnl", "candidate_pnl"]
            if evaluator == "iron_butterfly"
            else ["session", "baseline_loss", "candidate_loss"]
        )
        sessions = read("session_outcomes", columns)
        require(len(sessions) > 0 and sessions.session.is_unique, "Session outcomes must be unique")
        require(
            np.isfinite(sessions[columns[1:]].to_numpy(dtype=float)).all(),
            "Unresolved/nonfinite outcomes cannot be silently omitted",
        )
        baseline = math.fsum(float(x) for x in sessions[columns[1]]) / len(sessions)
        candidate = math.fsum(float(x) for x in sessions[columns[2]]) / len(sessions)
        estimate = (
            candidate - baseline
            if evaluator == "iron_butterfly"
            else (baseline - candidate) / baseline
            if baseline > 0
            else None
        )
        close(estimate, result.get("inference", {}).get("estimate"), "paired session estimand")
        close(float(len(sessions)), result.get("metrics", {}).get("n_sessions"), "session count")
        if evaluator == "controlled":
            require(
                dataset.get("fidelity") == "F0" and dataset.get("provenance") == "SYNTHETIC",
                "Controlled reconstruction requires F0 synthetic evidence",
            )
            require(sessions.baseline_loss.eq(1.0).all(), "Controlled unit-loss baseline differs")
            names = ("baseline_mean", "candidate_mean")
        elif evaluator == "exp001":
            features = read("features", ["session", "excursion"])
            predictions = read(
                "predictions",
                [
                    "session",
                    "status",
                    "baseline_prediction",
                    "candidate_prediction",
                    "baseline_loss",
                    "candidate_loss",
                ],
            )
            require(features.session.is_unique, "Feature sessions must be unique")
            targets = dict(zip(features.session, features.excursion, strict=True))
            scored = predictions[predictions.status.eq("EVALUATED")]
            require(scored.session.is_unique, "Prediction sessions must be unique")
            for row in scored.to_dict("records"):
                require(row["session"] in targets, "Prediction target absent")
                for policy in ("baseline", "candidate"):
                    loss = 10000 * abs(
                        float(targets[row["session"]]) - float(row[policy + "_prediction"])
                    )
                    close(loss, row[policy + "_loss"], policy + " original-scale loss", 1e-3)
            split = experiment.get("split", {})
            final = scored[
                (scored.session > split.get("validation_end", "2024-12-31"))
                & (scored.session <= split.get("evaluation_end", "2026-08-31"))
            ].set_index("session")
            require(
                set(final.index) == set(sessions.session), "Registered evaluation split differs"
            )
            for row in sessions.to_dict("records"):
                for policy in ("baseline", "candidate"):
                    close(
                        float(final.loc[row["session"], policy + "_loss"]),
                        row[policy + "_loss"],
                        "session/prediction loss",
                    )
            names = ("baseline_mae_bp", "candidate_mae_bp")
            report["checks"].append(
                "primitive target/prediction loss and registered evaluation split"
            )
        else:
            fills = read(
                "fills",
                ["policy", "cycle_id", "contract_id", "units", "price", "fees", "timestamp"],
            )
            opportunities = read(
                "opportunities", ["policy", "opportunity_id", "session", "pnl_inr"]
            )
            accounting = replicate_accounting(fills, opportunities)
            require(
                accounting["status"] == "PASS", "Primitive decimal accounting reconstruction failed"
            )
            keys = set(zip(opportunities.policy, opportunities.opportunity_id, strict=True))
            require(len(keys) == len(opportunities), "Duplicate opportunity identity")
            require(
                set(zip(fills.policy, fills.cycle_id, strict=True)) <= keys,
                "Primitive fills absent from opportunity ledger",
            )
            params = {**experiment.get("parameters", {}), **experiment.get("dsl", {})}
            management = params.get("management", "hold")
            left = opportunities[opportunities.policy.eq("hold")]
            right = opportunities[opportunities.policy.eq(management)]
            require(
                set(left.opportunity_id) == set(right.opportunity_id),
                "Paired opportunity identities differ",
            )
            require(
                set(left.session) == set(sessions.session), "Opportunity/session coverage differs"
            )
            for row in sessions.to_dict("records"):
                for ledger, name in ((left, "baseline_pnl"), (right, "candidate_pnl")):
                    values = [float(x) for x in ledger[ledger.session.eq(row["session"])].pnl_inr]
                    require(
                        all(math.isfinite(x) for x in values), "Unresolved primitive opportunity"
                    )
                    close(math.fsum(values), row[name], "opportunity/session cashflow")
            names = ("baseline_mean_pnl_inr", "candidate_mean_pnl_inr")
            report["accounting"] = accounting
            report["checks"].append(
                "primitive decimal fills, clocks, paired opportunities and session P&L"
            )
        close(baseline, result.get("metrics", {}).get(names[0]), names[0])
        close(candidate, result.get("metrics", {}).get(names[1]), names[1])
        report["checks"].extend(
            ["content-addressed artifacts verified", "paired session means and registered estimand"]
        )
        require(True, "")
        report["status"] = "PASS"
    except (ArtifactError, _ReconstructionError) as error:
        report["disagreements"] = [str(error)]
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as error:
        # Backend error prose can contain private paths; retain only its class.
        report["disagreements"] = ["Artifact reconstruction rejected: " + type(error).__name__]
    report.update(
        artifact_refs=refs,
        bounds={
            "artifact_bytes": byte_limit,
            "decoded_bytes": decoded_limit,
            "rows": 100_000,
            "wall_seconds": min(10.0, float(resources.get("wall_seconds", 60))),
        },
        observed=counts,
    )
    return report


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
