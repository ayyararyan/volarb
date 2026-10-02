"""Controlled benchmarks. Timing results apply only to the declared toy workload."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from .config import environment_hash, evaluator_hash
from .registry import Registry
from .schemas import (
    BudgetSpec,
    CampaignSpec,
    DatasetManifest,
    ExperimentSpec,
    HypothesisSpec,
    InferencePlan,
    RunResources,
)


def benchmark_config():
    path = Path(__file__).parent / "resources" / "benchmarks.json"
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "configs" / "benchmarks.json"
    return json.loads(path.read_text())


def controlled_dataset(id="controlled"):
    return DatasetManifest(
        id=id,
        kind="synthetic",
        fidelity="F0",
        provenance="SYNTHETIC",
        capabilities=["controlled_sessions", "synthetic_session_outcomes"],
        metadata={"generator": "controlled_session_panel_v1"},
    )


def controlled_hypothesis(id, campaign_id):
    return HypothesisSpec(
        id=id,
        campaign_id=campaign_id,
        family_id="known-effect-control",
        mechanism="A planted reduction in paired synthetic loss should be reconstructed without future inputs.",
        expected_direction="lower loss",
        decision_change="Compare fixed synthetic candidate against unit-loss baseline",
        observable_inputs=["known fixture generator"],
        horizon_minutes=30,
        outcome="session loss",
        baseline_id="unit-loss",
        primary_comparison="Candidate minus baseline on identical session IDs",
        primary_metric="paired_loss_improvement",
        practical_effect=0.01,
        risk_constraints=["F0 only; no historical inference"],
        search_budget=1,
        minimum_data=["controlled_sessions"],
        falsification_rule="Registered uncertainty excludes the planted practical effect or reconstruction disagrees.",
        alternative_explanations=["sampling error", "implementation defect"],
        evaluator="controlled",
    )


def _register(root, id, jobs, hypotheses, parameters, inference_repetitions=99):
    reg = Registry(root)
    campaign = CampaignSpec(
        id=id,
        objective="Controlled numerical reliability and scientific benchmark, no historical claims",
        approved=True,
        max_hypotheses=min(500, hypotheses),
        numerical_concurrency=2,
        budget=BudgetSpec(
            max_runs=jobs,
            cpu_seconds=jobs * 30,
            storage_bytes=jobs * 2_000_000,
            max_pending=max(20, jobs),
            memory_mb=2048,
        ),
    )
    reg.put("campaigns", id, campaign)
    data = controlled_dataset(id + "-data")
    reg.put("datasets", data.id, data)
    for i in range(hypotheses):
        hyp = controlled_hypothesis(f"{id}-h{i:03}", id)
        reg.put("hypotheses", hyp.id, hyp)
    engine, env = evaluator_hash(), environment_hash()
    runs = []
    for i in range(jobs):
        params = parameters(i)
        exp = ExperimentSpec(
            id=f"{id}-e{i:05}",
            campaign_id=id,
            hypothesis_id=f"{id}-h{i % hypotheses:03}",
            trial_id=f"{id}-t{i:05}",
            dataset_id=data.id,
            evaluator="controlled",
            relation="MONTE_CARLO" if i >= hypotheses else "NEW",
            baseline_id="unit-loss",
            seed=int(params.pop("_seed", i)),
            parameters=params,
            implementation_hash=engine,
            environment_hash=env,
            inference=InferencePlan(bootstrap_samples=inference_repetitions),
            resources=RunResources(
                cpu_seconds=30, wall_seconds=60, memory_mb=1024, storage_bytes=2_000_000
            ),
        )
        reg.put("experiments", exp.id, exp)
        reg.put(
            "trials",
            exp.trial_id,
            {
                "id": exp.trial_id,
                "campaign_id": id,
                "hypothesis_id": exp.hypothesis_id,
                "relation": "MONTE_CARLO" if i >= hypotheses else "NEW",
                "selection_alternative": i % hypotheses,
            },
        )
        runs.append(reg.register_run(exp, data, env, engine))
    return reg, runs


def _execute(root):
    started = time.monotonic()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "butterfly_lab.workers",
            "--root",
            str(root),
            "--concurrency",
            "2",
            "--idle-timeout",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=7200,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr[-4000:])
    return json.loads(proc.stdout), time.monotonic() - started


def load_benchmark(root: Path, jobs=2000, hypotheses=250):
    if not 1 <= hypotheses <= 500 or not hypotheses <= jobs <= 5000:
        raise ValueError("bounded jobs/hypotheses required")
    started = time.monotonic()
    reg, runs = _register(
        root, "load-v1", jobs, hypotheses, lambda i: {"n_sessions": 8, "effect": 0, "noise": 0.1}
    )
    registration = time.monotonic() - started
    # Simulate graph/controller restart after durable outbox commit, before execution.
    del reg
    reg = Registry(root)
    recovery_before = reg.reconcile()
    worker, elapsed = _execute(root)
    counts = {}
    checksums = []
    peak_child_rss_mib = 0.0
    for run in runs:
        row = reg.get_run(run)
        counts[row["state"]] = counts.get(row["state"], 0) + 1
        if row["state"] in ("COMPLETED", "INGESTED"):
            result = reg.ingest(run)
            checksums.append(row["result_ref"]["sha256"])
            peak_child_rss_mib = max(
                peak_child_rss_mib, result.get("execution", {}).get("peak_rss_mb", 0.0)
            )
            if result["replication"]["status"] != "PASS":
                raise AssertionError("load reconstruction failed")
            # Duplicate ingestion is exercised against every accepted result.
            if reg.ingest(run) != result:
                raise AssertionError("non-idempotent ingestion")
    receipt = {
        "label": "CONTROLLED SYNTHETIC lightweight numerical jobs; not real backtest throughput",
        "hypotheses": hypotheses,
        "registered_jobs": jobs,
        "accepted_results": len(checksums),
        "states_before_ingestion": counts,
        "registration_seconds": registration,
        "execution_seconds": elapsed,
        "jobs_per_second": jobs / elapsed,
        "numerical_concurrency": 2,
        "max_observed_child_rss_mib": peak_child_rss_mib,
        "artifact_bytes": sum(
            p.stat().st_size for p in (root / "artifacts").glob("*/*") if p.is_file()
        ),
        "worker_receipt": worker,
        "recovery_before": recovery_before,
        "recovery_after": reg.reconcile(),
        "schema_version": "1",
        "benchmark_config": benchmark_config()["load"],
        "passed": len(checksums) == jobs,
    }
    reg.put("benchmarks", "load-v1", receipt)
    (root / "load-report.json").write_text(json.dumps(receipt, indent=2))
    if not receipt["passed"]:
        raise AssertionError(f"load completion {len(checksums)}/{jobs}")
    return receipt


def scientific_benchmark(root: Path):
    cfg = benchmark_config()["scientific"]
    count = len(cfg["seeds"])
    reg, runs = _register(
        root,
        "scientific-v1",
        2 * count,
        2,
        lambda i: {
            "_seed": cfg["seeds"][i % count],
            "n_sessions": cfg["n_sessions"],
            "effect": cfg["null_effect"] if i < count else cfg["planted_effect"],
            "noise": cfg["noise"],
        },
        cfg["bootstrap_samples"],
    )
    worker, elapsed = _execute(root)
    groups = [[], []]
    for i, run in enumerate(runs):
        result = reg.ingest(run)
        groups[i // count].append(result["inference"]["outcome"] == "EXPLORATORY_SUPPORTED")
    null_rate = sum(groups[0]) / count
    power = sum(groups[1]) / count
    passed = null_rate <= cfg["max_null_support_rate"] and power >= cfg["min_planted_support_rate"]
    report = {
        "label": "SYNTHETIC preregistered known-null/planted-effect benchmark",
        "config": cfg,
        "null_support_rate": null_rate,
        "planted_support_rate": power,
        "trials_per_family": count,
        "monte_carlo_standard_error_null": (null_rate * (1 - null_rate) / count) ** 0.5,
        "monte_carlo_standard_error_power": (power * (1 - power) / count) ** 0.5,
        "null_rate_wilson_95": _wilson(null_rate, count),
        "power_wilson_95": _wilson(power, count),
        "uncertainty_note": "Plug-in standard errors vanish at 0/1; Wilson bounds express finite Monte Carlo uncertainty. Acceptance thresholds were fixed before these draws.",
        "passed": passed,
        "elapsed_seconds": elapsed,
        "worker": worker,
    }
    reg.put("benchmarks", "scientific-v1", report)
    (root / "scientific-report.json").write_text(json.dumps(report, indent=2))
    if not passed:
        raise AssertionError("predefined scientific acceptance failed")
    return report


def _wilson(proportion, count):
    z = 1.959963984540054
    denominator = 1 + z * z / count
    center = (proportion + z * z / (2 * count)) / denominator
    radius = (
        z
        * ((proportion * (1 - proportion) / count + z * z / (4 * count * count)) ** 0.5)
        / denominator
    )
    return [max(0.0, center - radius), min(1.0, center + radius)]


def comparison_benchmark(root: Path):
    from .agents import AgentService, fixture_provider
    from .data import qualify_dataset
    from .review_context import build_critic_context

    reports = []
    for mode in ("multi_role", "single_agent", "deterministic"):
        id = "compare-" + mode
        seeds = [controlled_hypothesis(f"{id}-h{i:03}", id) for i in range(3)]
        role = AgentService(fixture_provider(seeds), max_calls=12)
        campaign = {
            "id": id,
            "objective": "Matched controlled workflow comparison",
            "max_hypotheses": 3,
        }
        if mode != "deterministic":
            proposals = role.design(campaign, ["controlled_sessions"])
            if mode == "multi_role":
                dataset = controlled_dataset(id + "-review-data").model_dump(mode="json")
                qualification = qualify_dataset(dataset)
                for h in proposals:
                    draft = ExperimentSpec(
                        id="review-" + h.id,
                        campaign_id=id,
                        hypothesis_id=h.id,
                        trial_id="review-trial-" + h.id,
                        dataset_id=dataset["id"],
                        evaluator=h.evaluator,
                        baseline_id=h.baseline_id,
                        dsl=h.proposed_dsl,
                        inference=InferencePlan(practical_effect=h.practical_effect),
                    )
                    context = build_critic_context(campaign, h, dataset, qualification, draft)
                    output = role.specify(h, review_context=context)
                    draft = draft.model_copy(update={"dsl": output.dsl})
                    role.critique(build_critic_context(campaign, h, dataset, qualification, draft))
        reg, runs = _register(
            root,
            id,
            3,
            3,
            lambda i: {"n_sessions": 64, "effect": [0, 0.1, -0.1][i], "noise": 0.1},
            199,
        )
        worker, elapsed = _execute(root)
        results = [reg.ingest(run) for run in runs]
        reports.append(
            {
                "mode": mode,
                "provider": "SYNTHETIC_FIXTURE",
                "provider_calls": role.calls,
                "llm_tokens": 0,
                "llm_currency": 0,
                "numeric_budget_seconds": 90,
                "registered": 3,
                "valid_reproducible": sum(r["replication"]["status"] == "PASS" for r in results),
                "informative_negative": sum(r["outcome"] == "REJECTED_FINDING" for r in results),
                "outcomes": [r["outcome"] for r in results],
                "elapsed_seconds": elapsed,
                "worker": worker,
                "human_review_minutes": {
                    "value": None,
                    "reason": "No human comparison trial conducted",
                },
            }
        )
    report = {
        "modes": reports,
        "claim": "Infrastructure comparison on matched synthetic evidence. This does not establish LLM or multi-agent research superiority; a live-provider comparison needs explicit budget and credentials.",
    }
    (root / "comparison-report.json").write_text(json.dumps(report, indent=2))
    return report
