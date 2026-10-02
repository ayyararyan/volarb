"""Versioned immutable contracts. Runtime state belongs in the registry, not these models."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_default=True, allow_inf_nan=False
    )
    schema_version: Literal["1"] = "1"

    def digest(self) -> str:
        return digest(self.model_dump(mode="json"))


def canonical_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class Fidelity(StrEnum):
    F0 = "F0"
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"


class FindingOutcome(StrEnum):
    UNSUPPORTED_HYPOTHESIS = "UNSUPPORTED_HYPOTHESIS"
    DATA_LIMITED = "DATA_LIMITED"
    IMPLEMENTATION_FAILED = "IMPLEMENTATION_FAILED"
    INVALID_RESULT = "INVALID_RESULT"
    REJECTED_FINDING = "REJECTED_FINDING"
    INCONCLUSIVE = "INCONCLUSIVE"
    EXPLORATORY_SUPPORTED = "EXPLORATORY_SUPPORTED"
    INDEPENDENTLY_SUPPORTED = "INDEPENDENTLY_SUPPORTED"
    CANCELLED = "CANCELLED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class JobState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    INGESTED = "INGESTED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    LOST_UNRESOLVED = "LOST_UNRESOLVED"


class Relation(StrEnum):
    NEW = "NEW"
    VARIANT = "VARIANT"
    REPAIR = "REPAIR"
    RERUN = "RERUN"
    MONTE_CARLO = "MONTE_CARLO"
    REPLICATION = "REPLICATION"
    RESULT_INFORMED = "RESULT_INFORMED"
    DUPLICATE = "DUPLICATE"


class ArtifactRef(Contract):
    uri: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = "application/json"
    size_bytes: int | None = Field(default=None, ge=0)


class Quantity(Contract):
    value: float | None
    unit: str
    unknown_reason: str | None = None

    @model_validator(mode="after")
    def unknown(self):
        if self.value is None and not self.unknown_reason:
            raise ValueError("null quantity requires unknown_reason")
        if self.value is not None and self.unknown_reason is not None:
            raise ValueError("known quantity cannot have unknown_reason")
        return self


class BudgetSpec(Contract):
    max_runs: int = Field(default=60, ge=0)
    cpu_seconds: float = Field(default=3600, ge=0)
    storage_bytes: int = Field(default=1_000_000_000, ge=0)
    memory_mb: int = Field(default=2048, gt=0)
    max_pending: int = Field(default=20, ge=1, le=5000)
    llm_tokens: int = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    llm_currency: float = Field(default=0, ge=0)
    currency: Literal["INR", "USD"] = "INR"
    data_currency: float = Field(default=0, ge=0)
    human_review_minutes: int = Field(default=60, ge=0)


class RunResources(Contract):
    cpu_seconds: float = Field(default=30, gt=0)
    wall_seconds: float = Field(default=60, gt=0)
    memory_mb: int = Field(default=1024, ge=128)
    storage_bytes: int = Field(default=10_000_000, ge=1)


class CampaignSpec(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    objective: str = Field(min_length=8)
    approved: bool = Field(default=False, strict=True)
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    seed: int = 17
    max_hypotheses: int = Field(default=12, ge=1, le=500)
    preparation_batch: int = Field(default=4, ge=1, le=8)
    llm_concurrency: int = Field(default=2, ge=1, le=2)
    numerical_concurrency: int = Field(default=1, ge=1, le=2)
    provider: Literal["fixture", "replay", "codex", "openai", "deterministic"] = "fixture"
    source_records: list[dict[str, Any]] = Field(default_factory=list)
    development_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    prior_finding_ids: list[str] = Field(default_factory=list)
    dataset_ids: list[str] = Field(default_factory=list)
    negative_replication_fraction: float = Field(default=0.2, ge=0, le=1)
    confirmation_dataset_id: str | None = None
    graph_version: Literal["1"] = "1"


class HypothesisSpec(Contract):
    id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    campaign_id: str
    parent_ids: list[str] = Field(default_factory=list)
    family_id: str
    mechanism: str = Field(min_length=12)
    expected_direction: str = Field(min_length=1)
    decision_change: str = Field(min_length=8)
    observable_inputs: list[str] = Field(min_length=1)
    horizon_minutes: int = Field(gt=0, le=375)
    outcome: str
    baseline_id: str
    primary_comparison: str = Field(min_length=8)
    primary_metric: str
    practical_effect: float = Field(ge=0)
    risk_constraints: list[str] = Field(min_length=1)
    parameter_domain: dict[str, list[Any]] = Field(default_factory=dict)
    search_budget: int = Field(default=1, ge=1, le=60)
    minimum_data: list[str] = Field(min_length=1)
    falsification_rule: str = Field(min_length=12)
    alternative_explanations: list[str] = Field(min_length=1)
    source_refs: list[ArtifactRef] = Field(default_factory=list)
    informed_by_result_ids: list[str] = Field(default_factory=list)
    evaluator: Literal["exp001", "iron_butterfly", "controlled"] = "iron_butterfly"
    proposed_dsl: dict[str, Any] = Field(default_factory=dict)

    def canonical_digest(self) -> str:
        excluded = {
            "id",
            "campaign_id",
            "version",
            "parent_ids",
            "source_refs",
            "informed_by_result_ids",
        }
        return digest(self.model_dump(mode="json", exclude=excluded))


class DatasetManifest(Contract):
    id: str
    kind: Literal[
        "spot_bars", "option_quotes", "option_bars", "model", "synthetic", "session_panel"
    ]
    source_path: str | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_refs: list[ArtifactRef] = Field(default_factory=list)
    fidelity: Fidelity
    capabilities: list[str] = Field(default_factory=list)
    provenance: Literal["SYNTHETIC", "HISTORICAL", "MODEL", "REPLAY"]
    timezone: str = "Asia/Kolkata"
    bar_label: Literal["start", "end", "event"] = "start"
    availability_lag_seconds: int = Field(default=60, ge=0)
    partition: Literal["development", "validation", "confirmation"] = "development"
    prior_exposed: bool = Field(default=True, strict=True)
    calendar_policy: str = "explicit_sessions"
    timestamp_convention_verified: bool = Field(default=False, strict=True)
    session_dates: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    qualification_ref: ArtifactRef | None = None
    transformations: list[dict[str, Any]] = Field(default_factory=list)
    exposure_history: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def fidelity_contract(self):
        if self.provenance == "SYNTHETIC" and self.fidelity != Fidelity.F0:
            raise ValueError("synthetic observations must remain F0")
        if self.kind == "model" and self.fidelity not in (Fidelity.F0, Fidelity.F1):
            raise ValueError("model marks cannot be execution-quality")
        return self


class SplitPlan(Contract):
    train_end: str = "2023-12-31"
    validation_end: str = "2024-12-31"
    evaluation_end: str = "2026-08-31"
    refit: Literal["frozen", "expanding_monthly"] = "expanding_monthly"
    minimum_training_sessions: int = Field(default=30, ge=5)
    purge_overlapping_labels: bool = True
    availability_lag_seconds: int = Field(default=60, ge=0)


class InferencePlan(Contract):
    unit: Literal["session"] = "session"
    block_length: int = Field(default=5, ge=1)
    bootstrap_samples: int = Field(default=999, ge=99)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    practical_effect: float = Field(default=0.01, ge=0)
    minimum_sessions: int = Field(default=30, ge=5)
    confirmation_family: str | None = None
    robustness_block_lengths: list[int] = Field(default_factory=lambda: [1, 5, 10])


class ExperimentSpec(Contract):
    id: str
    campaign_id: str
    hypothesis_id: str
    trial_id: str
    dataset_id: str
    evaluator: Literal["exp001", "iron_butterfly", "controlled"]
    baseline_id: str = "B0-simple"
    relation: Relation = Relation.NEW
    parent_experiment_id: str | None = None
    informed_by_result_ids: list[str] = Field(default_factory=list)
    dsl: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    split: SplitPlan = Field(default_factory=SplitPlan)
    inference: InferencePlan = Field(default_factory=InferencePlan)
    robustness: list[str] = Field(default_factory=lambda: ["block_length", "cost_stress"])
    fidelity: Fidelity = Fidelity.F0
    seed: int = 17
    rerun_ordinal: int = Field(default=0, ge=0)
    implementation_hash: str = "builtin-v1"
    evaluator_version: Literal["1"] = "1"
    graph_version: Literal["1"] = "1"
    environment_hash: str = "unbound"
    resources: RunResources = Field(default_factory=RunResources)
    max_repairs: int = Field(default=2, ge=0, le=2)
    approval_scope_id: str = "campaign"
    hypothesis_ref: ArtifactRef | None = None
    dataset_ref: ArtifactRef | None = None
    baseline_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def lineage_required(self):
        if self.relation == Relation.RESULT_INFORMED and not self.informed_by_result_ids:
            raise ValueError("result-informed descendants require feedback lineage")
        if (
            self.relation in (Relation.REPAIR, Relation.RERUN, Relation.REPLICATION)
            and not self.parent_experiment_id
        ):
            raise ValueError("repair/rerun/replication requires parent experiment")
        return self


class RunManifest(Contract):
    run_id: str
    experiment_id: str
    attempt_id: str
    code_commit: str | None
    code_commit_unknown_reason: str | None = None
    source_tree_hash: str
    environment_hash: str
    config_ref: ArtifactRef
    model_prompt_refs: list[ArtifactRef] = Field(default_factory=list)
    agent_models: list[str] = Field(default_factory=list)
    seed: int
    worker_identity: str
    fencing_token: int = Field(ge=0)
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    status: JobState
    resource_usage: dict[str, Quantity] = Field(default_factory=dict)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    failure_ref: ArtifactRef | None = None
    graph_version: str = "1"
    evaluator_version: str = "1"

    @model_validator(mode="after")
    def commit_reason(self):
        if self.code_commit is None and not self.code_commit_unknown_reason:
            raise ValueError("unknown commit needs a reason")
        return self


class MetricEstimate(Contract):
    name: str
    value: Quantity
    lower: float | None = None
    upper: float | None = None
    n_sessions: int = Field(ge=0)


class BacktestResult(Contract):
    run_id: str
    fidelity: Fidelity
    provenance: Literal["SYNTHETIC", "HISTORICAL", "MODEL", "REPLAY"]
    opportunity_ledger_ref: ArtifactRef
    session_outcomes_ref: ArtifactRef
    exclusions_and_missingness_ref: ArtifactRef
    order_fill_ledger_ref: ArtifactRef | None = None
    inventory_cash_paths_ref: ArtifactRef | None = None
    predictions_ref: ArtifactRef | None = None
    metrics: list[MetricEstimate]
    accounting_residuals: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class EvidenceGrade(Contract):
    implementation: Literal["invalid", "qualified", "verified"]
    fidelity: Fidelity
    independence: Literal["development", "exposed_temporal", "protected_confirmation"]
    precision: Literal["insufficient", "informative"]
    replication: Literal["absent", "reproduced", "independently_reconstructed"]


class CheckResult(Contract):
    name: str
    passed: bool
    detail: str
    evidence_ref: ArtifactRef | None = None


class ValidationReport(Contract):
    id: str
    subject_ref: ArtifactRef
    checks: list[CheckResult]
    leakage_findings: list[str] = Field(default_factory=list)
    accounting_findings: list[str] = Field(default_factory=list)
    replication_ref: ArtifactRef | None = None
    evaluator_version: str
    reviewer_identity: str
    status: Literal["PASS", "FAIL", "QUALIFIED"]
    permitted_evidence_ceiling: EvidenceGrade


class ResearchFinding(Contract):
    id: str
    campaign_id: str
    hypothesis_id: str
    experiment_id: str | None
    outcome: FindingOutcome
    claim: str
    estimate_refs: list[ArtifactRef] = Field(default_factory=list)
    evidence_grade: EvidenceGrade
    dataset_id: str
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    search_family_id: str
    validation_refs: list[ArtifactRef] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_ceiling(self):
        if self.outcome == FindingOutcome.INDEPENDENTLY_SUPPORTED:
            g = self.evidence_grade
            if (
                g.independence != "protected_confirmation"
                or g.replication != "independently_reconstructed"
                or g.implementation != "verified"
                or g.fidelity == Fidelity.F0
            ):
                raise ValueError(
                    "independent support requires real protected confirmed reconstructed evidence"
                )
        return self


class Approval(Contract):
    id: str
    scope: Literal["campaign", "data_access", "confirmation"]
    subject_hash: str
    principal: str
    approved_at: AwareDatetime
    expires_at: AwareDatetime
    signature: str

    @model_validator(mode="after")
    def expiry(self):
        if self.expires_at <= self.approved_at:
            raise ValueError("approval must expire after issuance")
        return self


class WorkerEvent(Contract):
    id: str
    run_id: str
    attempt_id: str
    fencing_token: int = Field(ge=1)
    type: Literal["STARTED", "HEARTBEAT", "COMPLETED", "FAILED", "CANCELLED"]
    occurred_at: AwareDatetime
    result_ref: ArtifactRef | None = None


class Capability(Contract):
    name: str
    supported: bool
    evidence_ref: ArtifactRef | None = None
    limitation: str | None = None


CONTRACTS = [
    ArtifactRef,
    HypothesisSpec,
    ExperimentSpec,
    DatasetManifest,
    RunManifest,
    BacktestResult,
    ValidationReport,
    ResearchFinding,
    CampaignSpec,
    BudgetSpec,
    Approval,
    WorkerEvent,
    Capability,
    EvidenceGrade,
]
