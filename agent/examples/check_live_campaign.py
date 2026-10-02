"""Audit a completed live synthetic campaign using local authoritative receipts.

Reads no provider configuration, credentials or account identifiers. This does
not initiate model, worker or broker activity, and rejects offline substitution.
"""

import argparse
import json

from butterfly_lab.registry import Registry


def audit(root: str, campaign_id: str) -> dict:
    registry = Registry(root)
    campaign = registry.get("campaign", campaign_id)
    assert campaign is not None
    generations = registry.list("generation", campaign_id)
    accepted = [g for g in generations if g["contract_status"] == "VALID"]
    experiments = registry.list("experiment", campaign_id)
    findings = registry.list("finding", campaign_id)
    runs = registry.runs(campaign_id)
    final = registry.get("source", "campaign-report-" + campaign_id)
    assert final is not None, "No terminal campaign report"
    report = registry.artifacts.read_json(final["report_ref"])
    results = [registry.artifacts.read_json(run["result_ref"]) for run in runs]
    reconstruction = [registry.get("source", "reconstruction-" + exp["id"]) for exp in experiments]
    checks = {
        "one_hypothesis_experiment_finding": len(registry.list("hypothesis", campaign_id))
        == len(experiments)
        == len(findings)
        == 1,
        "one_ingested_numerical_run": len(runs) == 1 and runs[0]["state"] == "INGESTED",
        "all_six_live_roles": {g["role"] for g in accepted}
        == {"designer", "specification", "critic", "replication", "synthesis", "steward"},
        "subscription_codex_no_fallback": bool(generations)
        and all(
            g["provider"] == "codex"
            and g["source"] == "real_model"
            and g["billing_kind"] == "subscription"
            and g["reserved_cost_usd"] is None
            for g in generations
        ),
        "finite_call_budget": len(generations) <= campaign["budget"]["llm_calls"],
        "actual_numerical_robustness": bool(results)
        and all(result.get("robustness", {}).get("registered_checks") for result in results),
        "worker_independent_reconstruction": bool(results)
        and all(result.get("replication", {}).get("status") == "PASS" for result in results),
        "post_role_independent_reconstruction": bool(reconstruction)
        and all(item and item["report"]["status"] == "PASS" for item in reconstruction),
        "f0_independent_exploratory_evidence": bool(findings)
        and all(
            f["evidence_grade"]["fidelity"] == "F0"
            and f["evidence_grade"]["replication"] == "independently_reconstructed"
            and f["evidence_grade"]["independence"] != "protected_confirmation"
            for f in findings
        ),
        "terminal_report_after_findings": report.get("lifecycle_status") == "COMPLETED"
        and not report["pending_experiments"]
        and bool(report.get("synthesis_ref"))
        and bool(report.get("steward_ref")),
        "no_confirmation": campaign["confirmation_dataset_id"] is None,
    }
    events = registry.events()
    positions = {row["event_id"]: i for i, row in enumerate(events)}
    if len(experiments) == 1:
        eid = experiments[0]["id"]
        ordered = [
            "frozen-" + eid,
            "replication-support-" + eid,
            "reconstruction-" + eid,
            "synthesized-" + campaign_id,
            "stewarded-" + campaign_id,
            "completed-" + campaign_id,
        ]
        checks["registered_event_order"] = all(k in positions for k in ordered) and [
            positions[k] for k in ordered if k in positions
        ] == sorted(positions[k] for k in ordered if k in positions)
    references = [final["report_ref"], report.get("synthesis_ref"), report.get("steward_ref")]
    for result in results:
        references += [result["run_manifest_ref"], *result.get("artifacts", {}).values()]
    for ref in references:
        if ref:
            registry.artifacts.verify(ref)
    campaign_events = [row for row in events if row["subject"] == campaign_id]
    return {
        "campaign_id": campaign_id,
        "checks": checks,
        "passed": all(checks.values()),
        "experiment_ids": [exp["id"] for exp in experiments],
        "numerical_runs": [{"run_id": run["run_id"], "state": run["state"]} for run in runs],
        "models": sorted({g["model"] for g in generations}),
        "role_order": [g["role"] for g in generations],
        "calls": len(generations),
        "input_tokens": sum(g.get("input_tokens") or 0 for g in generations),
        "output_tokens": sum(g.get("output_tokens") or 0 for g in generations),
        "usage_incomplete": any(
            g.get("input_tokens") is None or g.get("output_tokens") is None for g in generations
        ),
        "elapsed_registry_seconds": round(
            campaign_events[-1]["created_at"] - campaign_events[0]["created_at"], 3
        ),
        "outcomes": [f["outcome"] for f in findings],
        "evidence_grades": [f["evidence_grade"] for f in findings],
        "robustness": [r["robustness"] for r in results],
        "worker_replication": [r["replication"] for r in results],
        "post_role_replication": [r["report"] for r in reconstruction if r],
        "scope": "Synthetic F0 workflow acceptance only; no profitability or historical strategy validation.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    result = audit(args.root, args.campaign_id)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
