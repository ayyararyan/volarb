"""Evidence grades are computed, never assigned by narrative providers."""

from __future__ import annotations

from .schemas import EvidenceGrade, FindingOutcome, ResearchFinding


def classify(result: dict, independent: bool, confirmation: dict | None = None) -> FindingOutcome:
    if result.get("outcome") in {
        "DATA_LIMITED",
        "INVALID_RESULT",
        "IMPLEMENTATION_FAILED",
        "CANCELLED",
        "BUDGET_EXHAUSTED",
    }:
        return FindingOutcome(result["outcome"])
    if result.get("validation", {}).get("status") == "FAIL":
        return FindingOutcome.INVALID_RESULT
    if result.get("metrics", {}).get("missing_sessions", 0) > 0:
        return FindingOutcome.INCONCLUSIVE
    if not independent:
        return FindingOutcome.INVALID_RESULT
    inference = result.get("inference", result.get("session_estimates", {}))
    if not isinstance(inference, dict):
        inference = {}
    low = inference.get("ci_low", inference.get("ci_lower", inference.get("lower")))
    high = inference.get("ci_high", inference.get("ci_upper", inference.get("upper")))
    hurdle = inference.get("practical_effect", 0)
    enough = inference.get("n_sessions", inference.get("n", 0)) >= inference.get(
        "minimum_sessions", 30
    )
    if low is None or high is None or not enough:
        return FindingOutcome.INCONCLUSIVE
    if high < hurdle:
        return FindingOutcome.REJECTED_FINDING
    if low > hurdle:
        if (
            confirmation
            and confirmation.get("supported")
            and result.get("provenance") != "SYNTHETIC"
        ):
            return FindingOutcome.INDEPENDENTLY_SUPPORTED
        return FindingOutcome.EXPLORATORY_SUPPORTED
    return FindingOutcome.INCONCLUSIVE


def make_finding(
    experiment: dict,
    hypothesis: dict,
    dataset: dict,
    result: dict,
    result_ref=None,
    validation_refs=None,
    independent=False,
    confirmation=None,
    forced_outcome=None,
    reasons=None,
) -> ResearchFinding:
    outcome = (
        FindingOutcome(forced_outcome)
        if forced_outcome
        else classify(result, independent, confirmation)
    )
    precise = outcome in (
        FindingOutcome.REJECTED_FINDING,
        FindingOutcome.EXPLORATORY_SUPPORTED,
        FindingOutcome.INDEPENDENTLY_SUPPORTED,
    )
    invalid = outcome in (FindingOutcome.INVALID_RESULT, FindingOutcome.IMPLEMENTATION_FAILED)
    limitations = list(result.get("limitations", [])) + list(reasons or [])
    if dataset["provenance"] == "SYNTHETIC":
        limitations.append("Controlled fixture; no historical or economic evidence.")
    if not confirmation:
        limitations.append(
            "No eligible protected confirmation evaluated; historical findings remain exploratory."
        )
    grade = EvidenceGrade(
        implementation="invalid" if invalid else ("verified" if independent else "qualified"),
        fidelity=dataset["fidelity"],
        independence="protected_confirmation"
        if confirmation
        else ("exposed_temporal" if dataset.get("prior_exposed") else "development"),
        precision="informative" if precise else "insufficient",
        replication="independently_reconstructed" if independent else "absent",
    )
    claim = f"{outcome.value}: {hypothesis['decision_change']}"
    return ResearchFinding(
        id=f"finding-{experiment['id']}",
        campaign_id=experiment["campaign_id"],
        hypothesis_id=hypothesis["id"],
        experiment_id=experiment["id"],
        outcome=outcome,
        claim=claim,
        evidence_grade=grade,
        dataset_id=dataset["id"],
        search_family_id=hypothesis["family_id"],
        estimate_refs=[result_ref] if result_ref else [],
        validation_refs=validation_refs or [],
        assumptions=[
            "Predictive association, not causal identification.",
            "Registered execution/availability assumptions apply.",
        ],
        limitations=limitations,
    )


class ResearchMemory:
    def __init__(self, registry):
        self.registry = registry

    def ingest(self, finding: ResearchFinding):
        self.registry.put("findings", finding.id, finding.model_dump(mode="json"))
        self.registry.put(
            "memory",
            finding.id,
            {
                "finding_id": finding.id,
                "campaign_id": finding.campaign_id,
                "terms": (finding.claim + " " + " ".join(finding.limitations)).lower(),
            },
        )

    def retrieve(self, query: str, limit: int = 10) -> list[dict]:
        terms = set(query.lower().split())
        findings = self.registry.list("findings")
        superseded = {id for f in findings for id in f.get("supersedes", [])}
        matches = sorted(
            findings,
            key=lambda f: (
                -len(
                    terms.intersection(
                        (f["claim"] + " " + " ".join(f.get("limitations", []))).lower().split()
                    )
                ),
                f["id"],
            ),
        )
        return [{**f, "superseded": f["id"] in superseded} for f in matches[:limit]]


def result_contract(result: dict, run_id: str):
    """Validate complete numerical evidence against the public typed result contract."""
    from .schemas import BacktestResult, MetricEstimate, Quantity

    refs = result.get("artifacts", {})
    required = {"opportunities", "session_outcomes", "exclusions"}
    if not required.issubset(refs):
        raise ValueError(
            "accepted numerical result lacks complete opportunity/outcome/exclusion artifacts"
        )
    n = int(result.get("metrics", {}).get("n_sessions", 0))
    metrics = []
    for name, value in result.get("metrics", {}).items():
        if not isinstance(value, (int, float)) and value is not None:
            continue
        unit = (
            "INR"
            if "inr" in name
            else "basis_points"
            if name.endswith("_bp")
            else "count"
            if any(s in name for s in ("sessions", "opportunities", "validation_n"))
            else "dimensionless"
        )
        quantity = Quantity(
            value=value,
            unit=unit,
            unknown_reason="Not estimable from admitted observations" if value is None else None,
        )
        metrics.append(MetricEstimate(name=name, value=quantity, n_sessions=n))
    return BacktestResult(
        run_id=run_id,
        fidelity=result["fidelity"],
        provenance=result["provenance"],
        opportunity_ledger_ref=refs["opportunities"],
        session_outcomes_ref=refs["session_outcomes"],
        exclusions_and_missingness_ref=refs["exclusions"],
        order_fill_ledger_ref=refs.get("fills"),
        inventory_cash_paths_ref=refs.get("paths"),
        predictions_ref=refs.get("predictions"),
        metrics=metrics,
        limitations=result.get("limitations", []),
    )
