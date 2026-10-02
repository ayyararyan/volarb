"""Closed, path-free summaries for pre-result experiment review.

All source hashes refer to original registry/artifact records, not to the display
summary. Dataset metadata, source paths and protected observations are never copied.
"""

from __future__ import annotations

from typing import Any

from .artifacts import digest as artifact_digest
from .schemas import (
    ArtifactRef,
    CriticContext,
    ControlledGeneratorReview,
    ExperimentSpec,
    HypothesisSpec,
    ReviewAdmission,
    ReviewCampaign,
    ReviewCoverage,
    ReviewCritique,
    ReviewData,
    ReviewGovernance,
    ReviewInference,
    ReviewSource,
    digest,
)


def _content_ref(ref: ArtifactRef | None) -> ArtifactRef | None:
    return ref.model_copy(update={"uri": "sha256:" + ref.sha256}) if ref else None


def review_hypothesis(hypothesis: HypothesisSpec) -> HypothesisSpec:
    """Retain the full scientific hypothesis but replace filesystem locators."""
    return hypothesis.model_copy(
        update={
            "source_refs": [
                ref.model_copy(update={"uri": "sha256:" + ref.sha256})
                for ref in hypothesis.source_refs
            ]
        }
    )


def review_experiment(draft: ExperimentSpec) -> ExperimentSpec:
    return draft.model_copy(
        update={
            field: _content_ref(getattr(draft, field))
            for field in ("hypothesis_ref", "dataset_ref", "baseline_ref")
        }
    )


def source_summaries(records: list[dict[str, Any]]) -> list[ReviewSource]:
    """Approved campaign records only; no fetching or following source instructions."""
    summaries = []
    for record in records[:12]:
        if (
            record.get("partition") == "confirmation"
            or record.get("access_class") == "confirmation"
        ):
            raise PermissionError("Protected source evidence cannot enter preparation")
        source_hash = artifact_digest(record)
        summaries.append(
            ReviewSource(
                id=str(record.get("id", "source-" + source_hash[:20]))[:256],
                title=str(record.get("title", record.get("name", "Approved campaign source")))[
                    :300
                ],
                summary=str(
                    record.get(
                        "summary",
                        record.get(
                            "description", record.get("citation", "No source summary registered.")
                        ),
                    )
                )[:1800],
                provenance_hash=source_hash,
                limitations=[str(item)[:400] for item in record.get("limitations", [])[:8]],
            )
        )
    return summaries


def _semantics(draft: ExperimentSpec, hypothesis: HypothesisSpec) -> dict[str, Any]:
    if draft.evaluator == "controlled":
        return {
            "baseline": "Registered unit-loss control: baseline loss equals 1 in every synthetic session.",
            "candidate": "Candidate loss = 1 - registered effect + IID zero-mean Gaussian noise. The registered noise parameter is the standard deviation, not variance. NumPy default_rng(experiment.seed) generates the frozen normal sample; effect/noise/n_sessions are frozen DSL/manifest parameters.",
            "estimand": "Relative paired mean loss reduction (mean baseline loss minus mean candidate loss) / mean baseline loss.",
            "timing": "No market decision or model fitting: controlled paired session generator with preregistered seed and parameters.",
            "chronology": "No training or refitting applies to the controlled generator. Synthetic business-day session labels begin 2020-01-01; they are identifiers, not historical observations. All generated sessions enter the paired test; stored calendar split fields do not filter this evaluator.",
            "missing": "Generator constructs complete paired sessions; no imputation. Numerical nonfinite/missing output fails validation.",
            "execution": [
                "Synthetic loss-scale engineering fixture only; no orders, fills, fees, market returns or trading interpretation.",
                "A planted effect is a generator input, never evidence of profitability.",
            ],
        }
    if draft.evaluator == "exp001":
        return {
            "baseline": "EXP001 frozen ridge regression of log excursion on past log realized variance.",
            "candidate": "EXP001 same ridge regression plus past-only normalized directional displacement, evaluated on identical eligible sessions.",
            "estimand": "Relative paired reduction of MAE in excursion basis points versus the RV-only baseline.",
            "timing": "10:05 IST origin, thirty complete past returns, 60-second feature availability lag, thirty-minute future excursion target.",
            "chronology": "Generate predictions for sessions after train_end through evaluation_end. Frozen fit uses training-end data; expanding_monthly uses labels available strictly before first monthly prediction. Primary scored inference uses only sessions strictly after validation_end; earlier validation predictions are retained separately. No numerical evidence is visible during preparation.",
            "missing": "Require every registered feature/target close and eligible timestamps; no forward filling. Missing opportunities remain in exclusion/session ledgers and can force inconclusive evidence.",
            "execution": [
                "Predictive spot-excursion comparison, not option execution or P&L.",
                "Fixed ridge coefficient and transformations belong to protected evaluator, not to agent-generated code.",
            ],
        }
    management = {**draft.parameters, **draft.dsl}.get("management", "hold")
    return {
        "baseline": "Frozen " + draft.baseline_id + " entry structures with hold policy.",
        "candidate": "Same registered opportunities and entry structures with "
        + str(management)
        + " management policy.",
        "estimand": "Mean paired candidate-minus-baseline net INR P&L per registered session, aggregating all eligible opportunities.",
        "timing": "Registered entry_time, hold_minutes, management_after_minutes, latency, quote age and sequential dependent-leg execution in the frozen DSL.",
        "chronology": "No learned fit: the frozen policy evaluates all registered opportunities; calendar split fields do not select or optimize policy parameters.",
        "missing": "Unavailable contract identities/quotes/exit valuations remain ledgered exclusions or invalid/missing outcomes; rejected opportunities are not silently discarded.",
        "execution": [
            "Identified contracts, dated lots/fees, quote availability and registered fill/capital assumptions are deterministic.",
            "Intraday only, one lot; no live broker access or accounting-ledger writes.",
        ],
    }


def build_critic_context(
    campaign: dict[str, Any],
    hypothesis: HypothesisSpec,
    dataset: dict[str, Any],
    qualification: dict[str, Any],
    draft: ExperimentSpec,
    *,
    revision: int = 0,
    prior_reviews: list[dict[str, Any]] | None = None,
    admission_report: dict[str, Any] | None = None,
) -> CriticContext:
    if dataset.get("partition") == "confirmation":
        raise PermissionError("Protected confirmation data cannot enter preparation")
    if (
        hypothesis.campaign_id != campaign["id"]
        or draft.campaign_id != campaign["id"]
        or draft.hypothesis_id != hypothesis.id
        or draft.dataset_id != dataset["id"]
    ):
        raise ValueError("Review context has inconsistent experiment lineage")
    sources = source_summaries(campaign.get("source_records", []))
    manifest_hash, qualification_hash = artifact_digest(dataset), artifact_digest(qualification)
    qualification_id = "qualification-exp-" + hypothesis.id
    sources.extend(
        [
            ReviewSource(
                id="manifest-" + dataset["id"],
                title="Registered dataset manifest",
                summary="Immutable registered dataset identity and semantics; raw observations and filesystem locators withheld.",
                provenance_hash=manifest_hash,
            ),
            ReviewSource(
                id=qualification_id,
                title="Deterministic capability qualification",
                summary="Qualification "
                + str(qualification.get("status", "UNKNOWN"))
                + "; capability and coverage summary appears in data_context.",
                provenance_hash=qualification_hash,
            ),
        ]
    )
    source_ids = [item.id for item in sources]
    source_ids.extend("sha256:" + ref["sha256"] for ref in dataset.get("source_refs", [])[:16])
    sem = _semantics(draft, hypothesis)
    limitations = [str(item)[:600] for item in qualification.get("limitations", [])[:10]]
    limitations += [str(item)[:600] for item in qualification.get("errors", [])[:5]]
    if dataset["fidelity"] == "F0":
        limitations.append(
            "F0 synthetic evidence tests implementation/orchestration only, not historical performance or profitability."
        )
    if dataset.get("prior_exposed", True):
        limitations.append(
            "Development observations have prior exposure; this is not an independent confirmation."
        )
    sessions = dataset.get("session_dates", [])
    plan, budget = draft.inference, campaign.get("budget", {})
    generator = None
    if draft.evaluator == "controlled":
        params = {
            key: value
            for key, value in dataset.get("metadata", {}).items()
            if key in ("effect", "noise", "n_sessions")
        }
        params.update({**draft.parameters, **draft.dsl})
        try:
            generator = ControlledGeneratorReview(
                n_sessions=params.get("n_sessions", 48),
                effect=params.get("effect", 0.0),
                noise_standard_deviation=params.get("noise", 0.1),
                seed=draft.seed,
            )
        except ValueError:
            # A malformed proposal remains reviewable, but cannot pass the
            # independent compiler. Never invent a replacement valid generator.
            limitations.append(
                "Controlled generator parameters are malformed; deterministic admission must fail until corrected."
            )
    context = CriticContext(
        campaign=ReviewCampaign(
            campaign_id=campaign["id"],
            objective=campaign["objective"],
            research_scope="Pre-result methodological review within the original hypothesis, registered evaluator primitives and original approved campaign objective/scope; no trading authority is implied.",
            constraints=hypothesis.risk_constraints,
        ),
        hypothesis=review_hypothesis(hypothesis),
        hypothesis_hash=hypothesis.digest(),
        data_context=ReviewData(
            dataset_id=dataset["id"],
            manifest_hash=manifest_hash,
            qualification_id=qualification_id,
            qualification_hash=qualification_hash,
            source_ids=source_ids[:32],
            fidelity=dataset["fidelity"],
            provenance=dataset["provenance"],
            verified_capabilities=qualification.get("capabilities", []),
            qualification_status=qualification.get("status", "UNKNOWN"),
            coverage=ReviewCoverage(
                rows=qualification.get("rows"),
                sessions=qualification.get(
                    "sessions",
                    qualification.get("rows") if draft.evaluator == "controlled" else None,
                ),
                start=qualification.get("start", min(sessions) if sessions else None),
                end=qualification.get("end", max(sessions) if sessions else None),
                registered_sessions=len(sessions),
            ),
            timing_semantics="timezone="
            + dataset.get("timezone", "Asia/Kolkata")
            + "; bar_label="
            + dataset.get("bar_label", "start")
            + "; timestamp_convention_verified="
            + str(dataset.get("timestamp_convention_verified", False))
            + ". "
            + sem["timing"],
            availability_semantics="Observations available no earlier than bar end/event plus registered lag ("
            + str(dataset.get("availability_lag_seconds", 60))
            + " seconds), and not before receipt when recorded. Controlled data has no market observation availability requirement.",
            missingness_summary=sem["missing"]
            + " Qualification does not certify that all future evaluator opportunities will be complete.",
            prior_exposed=dataset.get("prior_exposed", True),
            partition=dataset.get("partition", "development"),
            limitations=limitations,
        ),
        proposed_experiment=review_experiment(draft),
        specification_hash=draft.digest(),
        baseline=sem["baseline"],
        candidate=sem["candidate"],
        comparison_type="Paired comparison on identical session-level opportunity sets: "
        + hypothesis.primary_comparison,
        decision_timing=sem["timing"],
        holding_horizon_minutes=hypothesis.horizon_minutes,
        execution_assumptions=sem["execution"],
        controlled_generator=generator,
        inference=ReviewInference(
            estimand=sem["estimand"],
            primary_metric=hypothesis.primary_metric,
            practical_threshold=plan.practical_effect,
            unit_of_inference=plan.unit,
            split=draft.split,
            plan=plan,
            training_evaluation_chronology=sem["chronology"],
            dependence_resampling=f"Paired moving-block bootstrap; block length {plan.block_length}, repetitions {plan.bootstrap_samples}, alpha {plan.alpha}; registered robustness lengths {plan.robustness_block_lengths}. Resample paired sessions and recompute the relative ratio for loss comparisons.",
            missing_data_treatment=sem["missing"],
            multiple_testing_treatment="Exploratory per-comparison intervals, not familywise-confirmatory claims. Full family/search lineage retained; protected confirmation, if independently authorized later, uses the frozen family's deterministic multiplicity gate. No result-driven search or re-specification.",
            decision_rule=f"After valid independent reconstruction, informative precision requires n >= {plan.minimum_sessions} and n >= max(20, 4 * min(block_length, n)). Percentile CI uses alpha/2 and 1-alpha/2 quantiles. CI lower > practical threshold yields EXPLORATORY_SUPPORTED; CI upper < threshold yields REJECTED_FINDING; otherwise INCONCLUSIVE. Missing outcomes or insufficient precision remain inconclusive; invalid implementation/replication is not a negative economic finding. Synthetic F0 cannot receive protected-confirmation support.",
        ),
        research_governance=ReviewGovernance(
            search_family_id=hypothesis.family_id,
            search_budget=hypothesis.search_budget,
            parameter_domain=hypothesis.parameter_domain,
            max_hypotheses=campaign.get("max_hypotheses", 12),
            max_numerical_runs=budget.get("max_runs", 60),
            llm_call_budget=budget.get("llm_calls", 0),
            llm_token_budget=budget.get("llm_tokens", 0),
            revision=revision,
            fidelity_ceiling=dataset["fidelity"],
            confirmation_available=bool(campaign.get("confirmation_dataset_id")),
            protected_data_restrictions="No raw data, confirmation observations, provider/runtime configuration, credentials or account information. No numerical results exist in this revision lifecycle; accepted results cannot trigger scientific revision.",
        ),
        sources=sources,
        prior_reviews=[
            ReviewCritique(
                review_id=str(row.get("id", "review-" + digest(row)[:24])),
                recommendation=row.get("report", row)["recommendation"],
                concerns=row.get("report", row).get("concerns", [])[:20],
                report_hash=artifact_digest(row),
            )
            for row in (prior_reviews or [])[-2:]
        ],
        methodological_admission=ReviewAdmission(
            admitted=admission_report["admitted"],
            outcome=admission_report.get("outcome"),
            reasons=admission_report.get("reasons", []),
        )
        if admission_report
        else None,
    )
    # Late import keeps the contract module independent of provider implementations.
    from .agents import _safe_context

    _safe_context(context.model_dump(mode="json"))
    return context
