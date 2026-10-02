"""Real LangGraph campaign and durable experiment graphs; numerical work is external."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt
from pydantic import ValidationError

from .artifacts import ArtifactStore, plain
from .compiler import admission, validate_dsl
from .config import environment_hash, evaluator_hash, runtime_root, workflow_hash
from .evidence import ResearchMemory, make_finding
from .registry import BudgetExceeded, Registry, SourceBindingError, QueueFull
from .schemas import (
    CampaignSpec,
    DatasetManifest,
    ExperimentSpec,
    HypothesisSpec,
    InferencePlan,
    ValidationReport,
    EvidenceGrade,
    CheckResult,
    digest,
)


def merge_refs(left: dict, right: dict) -> dict:
    result = dict(left)
    for key, value in right.items():
        if key in result and result[key] != value:
            raise ValueError("conflicting parallel result: " + key)
        result[key] = value
    return dict(sorted(result.items()))


class ExperimentState(TypedDict, total=False):
    workflow_hash: str
    experiment_id: str
    run_id: str
    outcome: str | None
    reasons: list[str]
    event_id: str
    result_ref: dict
    result: dict
    independent: bool
    reconstruction_ref: dict
    confirmation: dict | None
    finding_id: str
    repair_count: int


class CampaignState(TypedDict, total=False):
    workflow_hash: str
    campaign_id: str
    dataset_id: str
    capabilities: list[str]
    candidates: list[dict]
    cursor: int
    batch: list[dict]
    prepared: Annotated[dict[str, str], merge_refs]
    report_ref: dict
    synthesis_ref: dict
    steward_ref: dict


class PreparationState(TypedDict, total=False):
    workflow_hash: str
    campaign_id: str
    dataset_id: str
    candidate: dict
    initial_specification: dict | None
    hypothesis: dict
    qualification: dict
    original_draft: dict
    draft: dict
    specification: dict
    revision: int
    reviews: list[dict]
    context: dict
    critic: dict
    methodological: dict
    outcome: str | None
    reasons: list[str]
    experiment_id: str
    finding_id: str


class ConfirmationState(TypedDict, total=False):
    workflow_hash: str
    campaign_id: str
    batch_id: str
    result_ref: dict
    finding_ids: list[str]


class ReviewState(TypedDict, total=False):
    hypothesis: dict
    dataset: dict
    qualification: dict
    report: dict


def build_specification_subgraph():
    def normalize(state):
        spec = HypothesisSpec.model_validate(state["hypothesis"])
        return {"hypothesis": spec.model_dump(mode="json")}

    graph = StateGraph(ReviewState)
    graph.add_node("strict_contract", normalize)
    graph.add_edge(START, "strict_contract")
    graph.add_edge("strict_contract", END)
    return graph.compile()


def build_critique_subgraph():
    def critique(state):
        spec = HypothesisSpec.model_validate(state["hypothesis"])
        return {"report": admission(spec, state["dataset"], state["qualification"])}

    graph = StateGraph(ReviewState)
    graph.add_node("methodological_admission", critique)
    graph.add_edge(START, "methodological_admission")
    graph.add_edge("methodological_admission", END)
    return graph.compile()


def build_review_subgraph():
    def review(state):
        report = dict(state["report"])
        report["checks"] = {
            "falsifiable": bool(state["hypothesis"]["falsification_rule"]),
            "alternatives_registered": bool(state["hypothesis"]["alternative_explanations"]),
            "no_confirmation_access": state["dataset"]["partition"] != "confirmation",
        }
        return {"report": report}

    graph = StateGraph(ReviewState)
    graph.add_node("independent_contract_review", review)
    graph.add_edge(START, "independent_contract_review")
    graph.add_edge("independent_contract_review", END)
    return graph.compile()


class Laboratory:
    def __init__(
        self, root: Path | str, agent_service=None, *, pending_limit=None, max_concurrency=2
    ):
        self.root = runtime_root(root)
        self.registry = Registry(self.root)
        self.pending_limit = pending_limit
        self.max_concurrency = max_concurrency
        self.artifacts = ArtifactStore(self.root / "artifacts")
        if agent_service is None:
            from .agents import AgentService, fixture_provider, load_seeds

            seed_path = Path(__file__).parent / "resources" / "seeds.json"
            if not seed_path.exists():
                seed_path = Path(__file__).resolve().parents[2] / "configs" / "seeds.json"
            agent_service = AgentService(
                fixture_provider(load_seeds(seed_path)), self.registry, max_calls=4000
            )
        self.agent_service = agent_service
        self.connection = sqlite3.connect(
            self.root / "checkpoints.sqlite3", check_same_thread=False
        )
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.checkpointer = SqliteSaver(self.connection)
        self.checkpointer.setup()
        self.preparation_graph = self._build_preparation()
        self.experiment_graph = self._build_experiment()
        self.campaign_graph = self._build_campaign()
        self.confirmation_graph = self._build_confirmation()

    def close(self):
        self.connection.close()
        close = getattr(self.agent_service.provider, "close", None)
        if close:
            close()

    def _config(self, id: str):
        return {
            "configurable": {"thread_id": id},
            "max_concurrency": self.max_concurrency,
            "recursion_limit": 2000,
        }

    def _records(self, state):
        exp = self.registry.get("experiments", state["experiment_id"])
        if exp is None:
            raise ValueError("unregistered experiment")
        return (
            exp,
            self.registry.get("hypotheses", exp["hypothesis_id"]),
            self.registry.get("datasets", exp["dataset_id"]),
        )

    def _validation(self, id, exp, data, report):
        ref = self.artifacts.put_json(report)
        failed = report.get("status") in ("FAIL", "DATA_LIMITED", "UNSUPPORTED")
        value = ValidationReport(
            id=id,
            subject_ref=ref,
            checks=[
                CheckResult(
                    name=id.split("-")[0],
                    passed=not failed,
                    detail=str(report.get("errors", report.get("status", "PASS"))),
                )
            ],
            evaluator_version="1",
            reviewer_identity="protected-deterministic-review",
            status="FAIL" if failed else "PASS",
            permitted_evidence_ceiling=EvidenceGrade(
                implementation="invalid" if failed else "qualified",
                fidelity=data["fidelity"],
                independence="exposed_temporal" if data.get("prior_exposed") else "development",
                precision="insufficient",
                replication="absent",
            ),
        )
        self.registry.put("validations", id, value)
        return ref

    def _build_preparation(self):
        """Pre-result, checkpointed specification/review lifecycle; no worker access."""
        from .agents import SpecificationOutput
        from .compiler import methodological_admission
        from .review_context import build_critic_context
        from .schemas import CriticContext

        def records(state):
            return (
                self.registry.get("campaigns", state["campaign_id"]),
                HypothesisSpec.model_validate(state["hypothesis"]),
                self.registry.get("datasets", state["dataset_id"]),
            )

        def review_context(state, draft):
            campaign, hypothesis, dataset = records(state)
            return build_critic_context(
                campaign,
                hypothesis,
                dataset,
                state["qualification"],
                draft,
                revision=state.get("revision", 0),
                prior_reviews=state.get("reviews", []),
                admission_report=state.get("methodological"),
            )

        def begin(state):
            from .dedup import deduplicate

            campaign = CampaignSpec.model_validate(
                self.registry.get("campaigns", state["campaign_id"])
            )
            self.agent_service.bind_campaign(campaign.id)
            h = HypothesisSpec.model_validate(state["candidate"])
            if h.campaign_id != campaign.id:
                raise ValueError("Hypothesis escaped its approved campaign")
            data = self.registry.get("datasets", state["dataset_id"])
            existing = [
                row for row in self.registry.list("hypotheses", campaign.id) if row["id"] != h.id
            ]
            lineage = self.registry.get("lineage", "dedup-" + h.id)
            if lineage is None:
                decision = deduplicate(h.model_dump(mode="json"), existing)
                lineage = {
                    "id": "dedup-" + h.id,
                    "campaign_id": campaign.id,
                    "hypothesis_id": h.id,
                    "decision": plain(decision),
                }
                self.registry.put("lineage", "dedup-" + h.id, lineage)
            self.registry.put("hypotheses", h.id, h)
            draft = ExperimentSpec(
                id="exp-" + h.id,
                campaign_id=campaign.id,
                hypothesis_id=h.id,
                trial_id="trial-" + h.id,
                dataset_id=data["id"],
                evaluator=h.evaluator,
                baseline_id=h.baseline_id,
                relation="RESULT_INFORMED"
                if h.informed_by_result_ids
                else ("VARIANT" if lineage["decision"]["relation"] == "VARIANT" else "NEW"),
                informed_by_result_ids=h.informed_by_result_ids,
                dsl=h.proposed_dsl,
                fidelity=data["fidelity"],
                inference=InferencePlan(practical_effect=h.practical_effect),
                seed=campaign.seed,
                environment_hash=environment_hash(),
                implementation_hash=evaluator_hash(),
            )
            self.registry.put(
                "trials",
                draft.trial_id,
                {
                    "id": draft.trial_id,
                    "campaign_id": campaign.id,
                    "hypothesis_id": h.id,
                    "relation": draft.relation.value,
                    "family_id": h.family_id,
                    "informed_by_result_ids": h.informed_by_result_ids,
                },
            )
            return {
                "hypothesis": plain(h),
                "original_draft": plain(draft),
                "draft": plain(draft),
                "revision": 0,
                "reviews": [],
                "outcome": None,
                "reasons": [],
            }

        def capability(state):
            from .data import qualify_dataset

            _, hyp, data = records(state)
            if data["partition"] == "confirmation":
                return {
                    "outcome": "UNSUPPORTED_HYPOTHESIS",
                    "reasons": ["Protected data cannot enter research preparation."],
                }
            try:
                self.registry.check_ordinary_dataset(data)
                report = qualify_dataset(data)
            except (SourceBindingError, PermissionError) as error:
                report = {"status": "DATA_LIMITED", "errors": [str(error)], "capabilities": []}
            self.registry.put(
                "source",
                "preparation-qualification-" + hyp.id,
                {
                    "campaign_id": hyp.campaign_id,
                    "hypothesis_id": hyp.id,
                    "dataset_id": data["id"],
                    "report": report,
                },
            )
            self._validation("qualification-exp-" + hyp.id, state["draft"], data, report)
            checked = admission(hyp, data, report)
            if report.get("status") != "PASS" or report.get("qualified") is False:
                checked = {
                    "admitted": False,
                    "outcome": "DATA_LIMITED",
                    "reasons": report.get(
                        "errors", report.get("reasons", ["qualification failed"])
                    ),
                }
            return {
                "qualification": report,
                "outcome": checked["outcome"],
                "reasons": checked["reasons"],
            }

        def construct(state):
            _, hyp, _ = records(state)
            context = review_context(state, ExperimentSpec.model_validate(state["original_draft"]))
            try:
                if state.get("initial_specification") is not None:
                    # Explicit imported proposal, never represented as a model call.
                    # It still traverses context, critic and all deterministic gates.
                    output = SpecificationOutput.model_validate(state["initial_specification"])
                else:
                    output = self.agent_service.specify(
                        hyp,
                        review_context=context,
                        call_id=f"specification-{hyp.campaign_id}-{hyp.id}-v0",
                    )
                return save_specification(state, output, 0)
            except ValidationError:
                return {
                    "outcome": "IMPLEMENTATION_FAILED",
                    "reasons": [
                        "Specification role failed strict executable contract after bounded format correction."
                    ],
                }

        def save_specification(state, output, revision):
            _, hyp, data = records(state)
            draft = ExperimentSpec.model_validate(
                {
                    **state["original_draft"],
                    "dsl": output.dsl,
                    "split": plain(output.split)
                    if output.split is not None
                    else state["draft"]["split"],
                    "inference": plain(output.inference)
                    if output.inference is not None
                    else state["draft"]["inference"],
                    "robustness": output.robustness
                    if output.robustness is not None
                    else state["draft"]["robustness"],
                }
            )
            original = ExperimentSpec.model_validate(state["original_draft"])
            checked = methodological_admission(
                hyp, data, state["qualification"], draft, original=original
            )
            prior = state["draft"]
            changed = [key for key, value in plain(draft).items() if prior.get(key) != value]
            record = {
                "id": f"preparation-{hyp.id}-v{revision}",
                "campaign_id": hyp.campaign_id,
                "hypothesis_id": hyp.id,
                "hypothesis_hash": digest(state["hypothesis"]),
                "revision": revision,
                "specification": plain(output),
                "origin": "supplied_draft"
                if revision == 0 and state.get("initial_specification") is not None
                else "model",
                "experiment": plain(draft),
                "specification_hash": digest(plain(draft)),
                "previous_specification_hash": digest(prior) if revision else None,
                "changed_fields": changed,
                "methodological_admission": checked,
                "prior_critic_ids": [r["id"] for r in state.get("reviews", [])],
                "pre_numerical": True,
            }
            self.registry.put("preparation", record["id"], record)
            self.registry.add_event(
                "SPECIFICATION_REVISED" if revision else "SPECIFICATION_CREATED",
                hyp.id,
                {
                    "specification_id": record["id"],
                    "revision": revision,
                    "specification_hash": record["specification_hash"],
                    "changed_fields": changed,
                },
                event_id=record["id"],
            )
            return {
                "draft": plain(draft),
                "specification": plain(output),
                "revision": revision,
                "methodological": checked,
            }

        def assemble(state):
            _, hyp, _ = records(state)
            context = review_context(state, ExperimentSpec.model_validate(state["draft"]))
            record_id = f"review-context-{hyp.id}-v{state['revision']}"
            record = {
                "id": record_id,
                "campaign_id": hyp.campaign_id,
                "hypothesis_id": hyp.id,
                "context": plain(context),
                "specification_hash": digest(state["draft"]),
            }
            self.registry.put("review_context", record_id, record)
            return {"context": plain(context)}

        def critique(state):
            _, hyp, _ = records(state)
            context = CriticContext.model_validate(state["context"])
            output = self.agent_service.critique(
                context, call_id=f"critic-{hyp.campaign_id}-{hyp.id}-v{state['revision']}"
            )
            record_id = f"critic-{hyp.id}-v{state['revision']}"
            report = {
                "id": record_id,
                "campaign_id": hyp.campaign_id,
                "hypothesis_id": hyp.id,
                "revision": state["revision"],
                "context_hash": digest(state["context"]),
                "specification_hash": digest(state["draft"]),
                "report": plain(output),
            }
            self.registry.put("critic_review", record_id, report)
            self.registry.add_event(
                "CRITIC_REVIEWED",
                hyp.id,
                {
                    "critic_id": record_id,
                    "revision": state["revision"],
                    "recommendation": output.recommendation,
                    "specification_hash": report["specification_hash"],
                },
                event_id=record_id,
            )
            return {"critic": plain(output), "reviews": [*state.get("reviews", []), report]}

        def critic_route(state):
            if state["critic"]["recommendation"] == "ADMIT":
                return "deterministic_admission"
            if state["critic"]["recommendation"] == "REVISE" and state["revision"] < 2:
                return "revise_specification"
            return "nonadmission"

        def revise(state):
            _, hyp, _ = records(state)
            if self.registry.runs(hyp.campaign_id):
                # Other campaign hypotheses may already have jobs; only this identity
                # must remain strictly pre-result and never consume result feedback.
                if any(
                    r["experiment_id"] == state["draft"]["id"]
                    for r in self.registry.runs(hyp.campaign_id)
                ):
                    raise ValueError("Specification revision forbidden after numerical dispatch")
            if state["revision"] >= 2:
                raise ValueError("Critic revision budget exhausted")
            try:
                output = self.agent_service.specify(
                    hyp,
                    review_context=CriticContext.model_validate(state["context"]),
                    previous=SpecificationOutput.model_validate(state["specification"]),
                    concerns=state["critic"]["concerns"] + state["critic"]["recommendations"],
                    call_id=f"specification-{hyp.campaign_id}-{hyp.id}-v{state['revision'] + 1}",
                )
                return save_specification(state, output, state["revision"] + 1)
            except ValidationError:
                return {
                    "outcome": "IMPLEMENTATION_FAILED",
                    "reasons": [
                        "Revision role failed strict executable contract after bounded format correction."
                    ],
                }

        def deterministic(state):
            _, hyp, data = records(state)
            checked = methodological_admission(
                hyp,
                data,
                state["qualification"],
                ExperimentSpec.model_validate(state["draft"]),
                original=ExperimentSpec.model_validate(state["original_draft"]),
            )
            record = {
                "campaign_id": hyp.campaign_id,
                "hypothesis_id": hyp.id,
                "specification_hash": digest(state["draft"]),
                "critic_report_id": state["reviews"][-1]["id"],
                "report": checked,
            }
            self.registry.put("methodological_admission", "admission-" + hyp.id, record)
            return {
                "methodological": checked,
                "outcome": checked["outcome"],
                "reasons": checked["reasons"],
            }

        def nonadmission(state):
            checked = state["methodological"]
            advisory = state["critic"]
            # Deterministic failures are authoritative. A semantic critic veto is
            # recorded as a veto, never disguised as a theorem proved by the compiler.
            if not checked["admitted"]:
                outcome, reasons = checked["outcome"], checked["reasons"]
            else:
                outcome = "UNSUPPORTED_HYPOTHESIS"
                reasons = [
                    "Bounded methodological revisions exhausted before numerical admission."
                    if advisory["recommendation"] == "REVISE"
                    else "Scoped methodological critic veto; no claim of deterministic proof of its scientific rationale.",
                    *advisory["concerns"],
                    *advisory["recommendations"],
                ]
            _, hyp, _ = records(state)
            self.registry.put(
                "methodological_admission",
                "admission-" + hyp.id,
                {
                    "campaign_id": hyp.campaign_id,
                    "hypothesis_id": hyp.id,
                    "specification_hash": digest(state["draft"]),
                    "critic_report_id": state["reviews"][-1]["id"],
                    "report": checked,
                    "authorized": False,
                    "outcome": outcome,
                    "reasons": reasons,
                },
            )
            return {"outcome": outcome, "reasons": reasons}

        def freeze(state):
            _, hyp, _ = records(state)
            if (
                state["critic"]["recommendation"] != "ADMIT"
                or not state["methodological"]["admitted"]
            ):
                raise PermissionError(
                    "Executable registration requires both review and deterministic admission"
                )
            draft = ExperimentSpec.model_validate(state["draft"])
            self.registry.put("experiments", draft.id, draft)
            self.registry.add_event(
                "EXPERIMENT_FROZEN",
                draft.id,
                {
                    "hypothesis_id": hyp.id,
                    "specification_hash": digest(state["draft"]),
                    "revision": state["revision"],
                    "critic_report_id": state["reviews"][-1]["id"],
                },
                event_id="frozen-" + draft.id,
            )
            return {"experiment_id": draft.id}

        def terminal(state):
            _, hyp, data = records(state)
            finding = make_finding(
                state["draft"],
                plain(hyp),
                data,
                {},
                forced_outcome=state["outcome"],
                reasons=state["reasons"],
            ).model_copy(update={"experiment_id": None})
            ResearchMemory(self.registry).ingest(finding)
            self.registry.add_event(
                "PREPARATION_TERMINATED",
                hyp.id,
                {
                    "finding_id": finding.id,
                    "outcome": finding.outcome.value,
                    "draft_hash": digest(state["draft"]),
                    "revision": state["revision"],
                },
                event_id="preparation-terminal-" + hyp.id,
            )
            return {"finding_id": finding.id}

        graph = StateGraph(PreparationState)
        for name, node in {
            "register_hypothesis": begin,
            "deterministic_capability_check": capability,
            "construct_specification": construct,
            "assemble_review_context": assemble,
            "critic_review": critique,
            "revise_specification": revise,
            "deterministic_admission": deterministic,
            "nonadmission": nonadmission,
            "freeze_experiment": freeze,
            "terminal_finding": terminal,
        }.items():
            graph.add_node(name, node)
        graph.add_edge(START, "register_hypothesis")
        graph.add_edge("register_hypothesis", "deterministic_capability_check")
        graph.add_conditional_edges(
            "deterministic_capability_check",
            lambda s: "terminal_finding" if s.get("outcome") else "construct_specification",
            ["terminal_finding", "construct_specification"],
        )
        graph.add_conditional_edges(
            "construct_specification",
            lambda s: "terminal_finding" if s.get("outcome") else "assemble_review_context",
            ["terminal_finding", "assemble_review_context"],
        )
        graph.add_edge("assemble_review_context", "critic_review")
        graph.add_conditional_edges(
            "critic_review",
            critic_route,
            ["deterministic_admission", "revise_specification", "nonadmission"],
        )
        graph.add_conditional_edges(
            "revise_specification",
            lambda s: "terminal_finding" if s.get("outcome") else "assemble_review_context",
            ["terminal_finding", "assemble_review_context"],
        )
        graph.add_conditional_edges(
            "deterministic_admission",
            lambda s: "terminal_finding" if s.get("outcome") else "freeze_experiment",
            ["terminal_finding", "freeze_experiment"],
        )
        graph.add_edge("nonadmission", "terminal_finding")
        graph.add_edge("terminal_finding", END)
        graph.add_edge("freeze_experiment", END)
        return graph.compile(checkpointer=self.checkpointer)

    def prepare_hypothesis(self, campaign_id, dataset_id, candidate, *, initial_specification=None):
        """Prepare a generated or explicitly supplied draft without bypassing review.

        Normal campaigns generate their own draft. Imported proposals enable
        transparent review/reproduction of a known pre-result specification.
        """
        from .agents import SpecificationOutput

        supplied = (
            plain(SpecificationOutput.model_validate(initial_specification))
            if initial_specification is not None
            else None
        )
        config = self._config("preparation-" + campaign_id + "-" + candidate["id"])
        state = self.preparation_graph.get_state(config)
        if state.values:
            if state.values.get("workflow_hash") != workflow_hash():
                raise ValueError("incompatible preparation graph implementation")
            if (
                state.values.get("candidate") != candidate
                or state.values["dataset_id"] != dataset_id
                or state.values.get("initial_specification") != supplied
            ):
                raise ValueError(
                    "Preparation resume cannot change registered hypothesis or dataset"
                )
            return (
                self.preparation_graph.invoke(None, config, durability="sync")
                if state.next
                else state.values
            )
        return self.preparation_graph.invoke(
            {
                "campaign_id": campaign_id,
                "dataset_id": dataset_id,
                "candidate": candidate,
                "initial_specification": supplied,
                "workflow_hash": workflow_hash(),
            },
            config,
            durability="sync",
        )

    def _build_experiment(self):
        specification = build_specification_subgraph()
        critique = build_critique_subgraph()
        review = build_review_subgraph()

        def qualify(state):
            from .data import qualify_dataset

            exp, hyp, data = self._records(state)
            if (
                exp["environment_hash"] != environment_hash()
                or exp["implementation_hash"] != evaluator_hash()
            ):
                raise ValueError("incompatible evaluator/environment; new experiment required")
            ExperimentSpec.model_validate(exp)
            DatasetManifest.model_validate(data)
            if data["partition"] == "confirmation":
                return {
                    "outcome": "UNSUPPORTED_HYPOTHESIS",
                    "reasons": ["Protected data cannot enter an ordinary experiment graph."],
                }
            try:
                self.registry.check_ordinary_dataset(data)
            except (SourceBindingError, PermissionError) as error:
                return {"outcome": "DATA_LIMITED", "reasons": [str(error)]}
            report = qualify_dataset(data)
            self._validation(f"qualification-{exp['id']}", exp, data, report)
            if (
                report.get("status") in ("FAIL", "DATA_LIMITED", "UNSUPPORTED")
                or report.get("qualified") is False
            ):
                return {
                    "outcome": "DATA_LIMITED",
                    "reasons": report.get(
                        "errors", report.get("reasons", ["qualification failed"])
                    ),
                }
            scoped = specification.invoke(
                {"hypothesis": hyp, "dataset": data, "qualification": report}
            )
            checked = review.invoke(critique.invoke(scoped))
            if not checked["report"]["admitted"]:
                return {
                    "outcome": checked["report"]["outcome"],
                    "reasons": checked["report"]["reasons"],
                }
            return {"outcome": None, "reasons": []}

        def compile_node(state):
            exp, _, _ = self._records(state)
            try:
                report = validate_dsl(exp)
            except ValueError as error:
                return {"outcome": "UNSUPPORTED_HYPOTHESIS", "reasons": [str(error)]}
            self._validation(
                f"compile-{exp['id']}",
                exp,
                self.registry.get("datasets", exp["dataset_id"]),
                report,
            )
            return {}

        def verify(state):
            from .baselines import certify_baseline, baseline_golden_cases

            exp, _, _ = self._records(state)
            # Scientific primitives are release-tested; each invocation binds their bytes.
            if exp["evaluator"] == "iron_butterfly":
                report = certify_baseline(
                    exp["baseline_id"], baseline_golden_cases(exp["baseline_id"])
                )
                if report.get("status") == "FAIL":
                    return {
                        "outcome": "IMPLEMENTATION_FAILED",
                        "reasons": ["baseline certification failed"],
                    }
            self.registry.add_event(
                "IMPLEMENTATION_VERIFIED",
                exp["id"],
                {
                    "evaluator_hash": evaluator_hash(),
                    "dsl_hash": digest(exp["dsl"]),
                    "repair_count": state.get("repair_count", 0),
                },
                event_id="verify-" + exp["id"],
            )
            return {}

        def submit(state):
            exp, _, data = self._records(state)
            if any(
                e["event_type"] == "CAMPAIGN_CANCELLED"
                for e in self.registry.events(exp["campaign_id"])
            ):
                return {"outcome": "CANCELLED", "reasons": ["Campaign cancelled before submission"]}
            try:
                run = self.registry.register_run(
                    exp,
                    data,
                    environment_hash(),
                    evaluator_hash(),
                    pending_limit=self.pending_limit,
                )
            except QueueFull:
                interrupt({"kind": "queue_capacity", "campaign_id": exp["campaign_id"]})
                run = self.registry.register_run(
                    exp,
                    data,
                    environment_hash(),
                    evaluator_hash(),
                    pending_limit=self.pending_limit,
                )
            except BudgetExceeded as error:
                return {"outcome": "BUDGET_EXHAUSTED", "reasons": [str(error)]}
            except SourceBindingError as error:
                return {"outcome": "DATA_LIMITED", "reasons": [str(error)]}
            return {"run_id": run}

        def await_job(state):
            run_id = state["run_id"]
            self.registry.add_event(
                "WAIT_REGISTERED",
                run_id,
                {"experiment_id": state["experiment_id"]},
                event_id="wait-" + run_id,
            )
            event = self.registry.terminal_event(run_id)
            if event is None:
                payload = interrupt({"kind": "external_job", "run_id": run_id})
                event = self.registry.validate_terminal_event(run_id, payload["event_id"])
            else:
                self.registry.validate_terminal_event(run_id, event["event_id"])
            return {"event_id": event["event_id"]}

        def ingest(state):
            run = self.registry.get_run(state["run_id"])
            if run["state"] in ("FAILED", "CANCELLED", "INVALID_RESULT"):
                outcome = "CANCELLED" if run["state"] == "CANCELLED" else "IMPLEMENTATION_FAILED"
                if (run.get("failure") or {}).get("kind") == "SourceBindingError":
                    outcome = "DATA_LIMITED"
                return {"outcome": outcome, "reasons": [str(run.get("failure"))]}
            result = self.registry.ingest(state["run_id"])
            if result.get("outcome") not in {
                "DATA_LIMITED",
                "INVALID_RESULT",
                "IMPLEMENTATION_FAILED",
            }:
                from .evidence import result_contract

                try:
                    typed = result_contract(result, state["run_id"])
                except ValueError as error:
                    return {"outcome": "INVALID_RESULT", "reasons": [str(error)]}
                result["typed_result_ref"] = plain(self.artifacts.put_json(typed))
            # ingest returns verified numerical payload, not trusted worker narration.
            return {
                "result": {
                    k: v
                    for k, v in result.items()
                    if k not in ("session_estimates", "trade_history")
                },
                "result_ref": run["result_ref"],
            }

        def robustness(state):
            result = state["result"]
            if result.get("outcome") in ("DATA_LIMITED", "INVALID_RESULT", "IMPLEMENTATION_FAILED"):
                return {"outcome": result["outcome"], "reasons": result.get("limitations", [])}
            checks = result.get("robustness")
            if not checks:
                return {
                    "outcome": "INVALID_RESULT",
                    "reasons": ["registered robustness report missing"],
                }
            return {}

        def replicate(state):
            exp, _, _ = self._records(state)
            self.agent_service.bind_campaign(exp["campaign_id"])
            output = self.agent_service.replicate(
                {
                    "experiment_id": exp["id"],
                    "evaluator": exp["evaluator"],
                    "evaluator_hash": exp["implementation_hash"],
                    "dsl": exp["dsl"],
                    "baseline_id": exp["baseline_id"],
                    "inference": exp["inference"],
                    "split": exp["split"],
                    "fidelity": exp["fidelity"],
                    "robustness": state["result"].get("robustness", {}),
                    "registered_tolerance": 1e-8,
                },
                call_id="replication-" + exp["id"],
            )
            record = {
                "campaign_id": exp["campaign_id"],
                "experiment_id": exp["id"],
                "output": plain(output),
            }
            self.registry.put("source", "replication-support-" + exp["id"], record)
            self.registry.add_event(
                "REPLICATION_SUPPORT_COMPLETED",
                exp["id"],
                record,
                event_id="replication-support-" + exp["id"],
            )
            return {}

        def reconstruct(state):
            from .replication import verify_registered_reconstruction

            exp, _, data = self._records(state)
            record_id = "reconstruction-" + exp["id"]
            recorded = self.registry.get("source", record_id)
            if recorded is None:
                numerical = verify_registered_reconstruction(
                    state["result"], exp, data, self.artifacts
                )
                recorded = {
                    "campaign_id": exp["campaign_id"],
                    "experiment_id": exp["id"],
                    "report": numerical,
                }
                self.registry.put("source", record_id, recorded)
            report = {
                "worker_reconstruction": state["result"].get("replication", {}),
                "post_role_reconstruction": recorded["report"],
            }
            valid = all(row.get("status") == "PASS" for row in report.values())
            report["status"] = "PASS" if valid else "FAIL"
            self.registry.add_event(
                "INDEPENDENT_RECONSTRUCTION_COMPLETED",
                exp["id"],
                {"status": report["status"], "report_hash": digest(report)},
                event_id=record_id,
            )
            if not valid:
                return {
                    "outcome": "INVALID_RESULT",
                    "reasons": ["independent reconstruction absent or failed"],
                    "independent": False,
                }
            from .schemas import ValidationReport, CheckResult, EvidenceGrade

            data = self.registry.get("datasets", exp["dataset_id"])
            ref = self.artifacts.put_json(report)
            validated = ValidationReport(
                id="replication-" + exp["id"],
                subject_ref=ref,
                checks=[
                    CheckResult(
                        name="independent_reconstruction",
                        passed=True,
                        detail="Independent numerical transformations/metric checks passed",
                        evidence_ref=ref,
                    )
                ],
                evaluator_version="1",
                reviewer_identity="independent-numerical-implementation",
                status="PASS",
                permitted_evidence_ceiling=EvidenceGrade(
                    implementation="verified",
                    fidelity=data["fidelity"],
                    independence="exposed_temporal",
                    precision="insufficient",
                    replication="independently_reconstructed",
                ),
            )
            self.registry.put("validations", validated.id, validated)
            return {"independent": True, "reconstruction_ref": plain(ref)}

        def confirmation(state):
            exp, _, _ = self._records(state)
            campaign = self.registry.get("campaigns", exp["campaign_id"])
            target = campaign.get("confirmation_dataset_id")
            if not target:
                return {
                    "confirmation": None,
                    "reasons": [
                        *state.get("reasons", []),
                        "No eligible protected partition configured.",
                    ],
                }
            data = self.registry.get("datasets", target)
            if not data or data.get("prior_exposed") or data.get("partition") != "confirmation":
                return {
                    "confirmation": None,
                    "reasons": [
                        *state.get("reasons", []),
                        "Configured partition is not eligible pristine confirmation.",
                    ],
                }
            # Authorization/evaluation are separate durable service operations. A completed
            # bundle can be attached; no approval means finite exploratory termination.
            self.registry.add_event(
                "CONFIRMATION_CANDIDATE",
                exp["id"],
                {"campaign_id": exp["campaign_id"], "dataset_id": target},
                event_id="confirmation-candidate-" + exp["id"],
            )
            return {
                "confirmation": None,
                "reasons": state.get("reasons", [])
                + [
                    "Eligible confirmation candidate registered; campaign-level frozen batch required."
                ],
            }

        def grade(state):
            exp, hyp, data = self._records(state)
            finding = make_finding(
                exp,
                hyp,
                data,
                state.get("result", {}),
                result_ref=state.get("result_ref"),
                independent=state.get("independent", False),
                confirmation=state.get("confirmation"),
                validation_refs=[
                    self.artifacts.put_json(
                        self.registry.get("validations", "replication-" + exp["id"])
                    )
                ]
                if state.get("independent")
                else [],
                forced_outcome=state.get("outcome"),
                reasons=state.get("reasons", []),
            )
            ResearchMemory(self.registry).ingest(finding)
            return {"outcome": finding.outcome.value, "finding_id": finding.id}

        graph = StateGraph(ExperimentState)
        nodes = {
            "qualify": qualify,
            "compile": compile_node,
            "verify": verify,
            "submit": submit,
            "await_job": await_job,
            "ingest": ingest,
            "robustness": robustness,
            "replicate": replicate,
            "reconstruct": reconstruct,
            "confirmation": confirmation,
            "grade_memory": grade,
        }
        for name, node in nodes.items():
            graph.add_node(name, node)
        graph.add_edge(START, "qualify")
        for first, second in [
            ("qualify", "compile"),
            ("compile", "verify"),
            ("verify", "submit"),
            ("submit", "await_job"),
            ("ingest", "robustness"),
            ("robustness", "replicate"),
            ("replicate", "reconstruct"),
            ("reconstruct", "confirmation"),
        ]:
            graph.add_conditional_edges(
                first,
                lambda s, n=second: "grade_memory" if s.get("outcome") else n,
                [second, "grade_memory"],
            )
        graph.add_edge("await_job", "ingest")
        graph.add_edge("confirmation", "grade_memory")
        graph.add_edge("grade_memory", END)
        return graph.compile(checkpointer=self.checkpointer)

    def _build_campaign(self):
        def contract(state):
            campaign = CampaignSpec.model_validate(
                self.registry.get("campaigns", state["campaign_id"])
            )
            self.agent_service.bind_campaign(campaign.id)
            if not campaign.approved:
                raise PermissionError("campaign contract not approved")
            from .providers import OpenAIProvider, ReplayProvider

            if campaign.provider == "openai" and not isinstance(
                self.agent_service.provider, OpenAIProvider
            ):
                raise PermissionError(
                    "Real-provider campaign requires configured real adapter; no fixture substitution"
                )
            if campaign.provider == "replay" and not isinstance(
                self.agent_service.provider, ReplayProvider
            ):
                raise PermissionError(
                    "Replay campaign requires explicit recorded-response provider"
                )
            if campaign.max_hypotheses < len(state.get("candidates", [])):
                raise ValueError("campaign hypothesis budget exceeded")
            return {"cursor": 0, "prepared": {}}

        def audit(state):
            from .data import qualify_dataset

            data = self.registry.get("datasets", state["dataset_id"])
            if data["partition"] == "confirmation":
                raise PermissionError("Campaign generation cannot access protected data")
            try:
                self.registry.check_ordinary_dataset(data)
                report = qualify_dataset(data)
            except (SourceBindingError, PermissionError) as error:
                report = {"status": "DATA_LIMITED", "errors": [str(error)], "capabilities": []}
            self.registry.put(
                "source",
                "campaign-capabilities-" + state["campaign_id"],
                {
                    "campaign_id": state["campaign_id"],
                    "report_ref": plain(self.artifacts.put_json(report)),
                },
            )
            return {"capabilities": report.get("capabilities", [])}

        def generate(state):
            if state.get("candidates"):
                return {}
            campaign = self.registry.get("campaigns", state["campaign_id"])
            if self.agent_service:
                candidates = self.agent_service.design(
                    campaign,
                    state.get("capabilities", []),
                    [
                        f
                        for f in ResearchMemory(self.registry).retrieve(campaign["objective"], 10)
                        if f["evidence_grade"]["independence"] != "protected_confirmation"
                    ],
                    call_id="designer-" + campaign["id"],
                )
            else:
                raise ValueError("campaign provider not configured")
            return {"candidates": [plain(x) for x in candidates[: campaign["max_hypotheses"]]]}

        def batch(state):
            campaign = self.registry.get("campaigns", state["campaign_id"])
            cursor = state["cursor"]
            return {
                "batch": state["candidates"][cursor : cursor + campaign["preparation_batch"]],
                "cursor": cursor + campaign["preparation_batch"],
            }

        def dispatch(state):
            return [
                Send(
                    "prepare",
                    {
                        "campaign_id": state["campaign_id"],
                        "dataset_id": state["dataset_id"],
                        "candidate": h,
                    },
                )
                for h in state["batch"]
            ] or "join"

        def prepare(state):
            prepared = self.prepare_hypothesis(
                state["campaign_id"], state["dataset_id"], state["candidate"]
            )
            return {"prepared": {state["candidate"]["id"]: prepared.get("experiment_id", "")}}

        def join(state):
            return {}

        def launch(state):
            from .dedup import deduplicate

            ordered = self.registry.list("hypotheses", state["campaign_id"])
            for hyp in state["batch"]:
                exp_id = state["prepared"][hyp["id"]]
                if not exp_id:
                    continue  # Preparation already registered a non-executable finding.
                current = self.registry.get("hypotheses", hyp["id"])
                previous = ordered[: next(i for i, h in enumerate(ordered) if h["id"] == hyp["id"])]
                decision = deduplicate(current, previous)
                if decision.relation == "DUPLICATE":
                    exp = self.registry.get("experiments", exp_id)
                    data = self.registry.get("datasets", state["dataset_id"])
                    self.registry.put(
                        "lineage",
                        "alias-" + hyp["id"],
                        {
                            "campaign_id": state["campaign_id"],
                            "parent_id": decision.matched_id,
                            "child_id": hyp["id"],
                            "relation": "DUPLICATE",
                        },
                    )
                    finding = make_finding(
                        exp,
                        current,
                        data,
                        {},
                        forced_outcome="UNSUPPORTED_HYPOTHESIS",
                        reasons=[
                            "Registered alias of "
                            + decision.matched_id
                            + "; not a new statistical trial."
                        ],
                    )
                    ResearchMemory(self.registry).ingest(finding)
                else:
                    self.run_experiment(exp_id)
            return {}

        def next_route(state):
            return "batch" if state["cursor"] < len(state["candidates"]) else "await_findings"

        def await_findings(state):
            report = self.campaign_report(state["campaign_id"])
            if report["pending_experiments"]:
                interrupt(
                    {
                        "kind": "campaign_findings",
                        "campaign_id": state["campaign_id"],
                        "pending_experiments": report["pending_experiments"],
                    }
                )
                # Never trust a resume notification to assert numerical completion.
                report = self.campaign_report(state["campaign_id"])
                if report["pending_experiments"]:
                    raise ValueError("Campaign still has pending registered experiments")
            return {}

        def synthesize(state):
            report = self.campaign_report(state["campaign_id"])
            if report["pending_experiments"]:
                raise ValueError("Synthesis cannot precede authoritative numerical findings")
            self.agent_service.bind_campaign(state["campaign_id"])
            result = self.agent_service.synthesize(
                report["findings"], call_id="synthesis-" + state["campaign_id"]
            )
            record = {
                "campaign_id": state["campaign_id"],
                "finding_ids": [finding["id"] for finding in report["findings"]],
                "output": plain(result),
            }
            self.registry.put("source", "synthesis-" + state["campaign_id"], record)
            self.registry.add_event(
                "CAMPAIGN_SYNTHESIZED",
                state["campaign_id"],
                record,
                event_id="synthesized-" + state["campaign_id"],
            )
            return {"synthesis_ref": plain(self.artifacts.put_json(record))}

        def steward(state):
            report = self.campaign_report(state["campaign_id"])
            result = self.agent_service.steward(
                {
                    "campaign_id": state["campaign_id"],
                    "pending": 0,
                    "findings": report["findings"],
                    "synthesis": self.artifacts.read_json(state["synthesis_ref"])["output"],
                },
                call_id="steward-" + state["campaign_id"],
            )
            record = {"campaign_id": state["campaign_id"], "output": plain(result)}
            self.registry.put("source", "steward-" + state["campaign_id"], record)
            self.registry.add_event(
                "CAMPAIGN_STEWARDED",
                state["campaign_id"],
                record,
                event_id="stewarded-" + state["campaign_id"],
            )
            return {"steward_ref": plain(self.artifacts.put_json(record))}

        def complete(state):
            existing = self.registry.get("source", "campaign-report-" + state["campaign_id"])
            if existing:
                self.registry.add_event(
                    "CAMPAIGN_COMPLETED",
                    state["campaign_id"],
                    {"report_ref": existing["report_ref"]},
                    event_id="completed-" + state["campaign_id"],
                )
                return {"report_ref": existing["report_ref"]}
            report = self.campaign_report(state["campaign_id"])
            report.update(
                lifecycle_status="COMPLETED",
                synthesis_ref=state["synthesis_ref"],
                steward_ref=state["steward_ref"],
            )
            ref = plain(self.artifacts.put_json(report))
            self.registry.put(
                "source",
                "campaign-report-" + state["campaign_id"],
                {"campaign_id": state["campaign_id"], "report_ref": ref},
            )
            self.registry.add_event(
                "CAMPAIGN_COMPLETED",
                state["campaign_id"],
                {"report_ref": ref},
                event_id="completed-" + state["campaign_id"],
            )
            return {"report_ref": ref}

        graph = StateGraph(CampaignState)
        for name, node in {
            "contract": contract,
            "audit": audit,
            "generate": generate,
            "batch": batch,
            "prepare": prepare,
            "join": join,
            "launch": launch,
            "await_findings": await_findings,
            "synthesize": synthesize,
            "steward": steward,
            "complete": complete,
        }.items():
            graph.add_node(name, node)
        graph.add_edge(START, "contract")
        graph.add_edge("contract", "audit")
        graph.add_edge("audit", "generate")
        graph.add_edge("generate", "batch")
        graph.add_conditional_edges("batch", dispatch, ["prepare", "join"])
        graph.add_edge("prepare", "join")
        graph.add_edge("join", "launch")
        graph.add_conditional_edges("launch", next_route, ["batch", "await_findings"])
        graph.add_edge("await_findings", "synthesize")
        graph.add_edge("synthesize", "steward")
        graph.add_edge("steward", "complete")
        graph.add_edge("complete", END)
        return graph.compile(checkpointer=self.checkpointer)

    def _build_confirmation(self):
        def freeze(state):
            from .cli import confirmation_service

            service, _ = confirmation_service(self.root)
            campaign = self.registry.get("campaigns", state["campaign_id"])
            findings = self.registry.list("findings", campaign["id"])
            claims = []
            for finding in findings:
                if (
                    finding["outcome"] != "EXPLORATORY_SUPPORTED"
                    or finding["evidence_grade"]["replication"] != "independently_reconstructed"
                ):
                    continue
                exp = self.registry.get("experiments", finding["experiment_id"])
                claims.append(
                    {
                        "hypothesis_id": exp["hypothesis_id"],
                        "experiment_hash": digest(exp),
                        "implementation_hash": exp["implementation_hash"],
                        "replication_passed": True,
                        "replication_report_id": "replication-" + exp["id"],
                        "effect_scale": "absolute"
                        if exp["evaluator"] == "iron_butterfly"
                        else "relative_baseline",
                        "higher_is_better": exp["evaluator"] == "iron_butterfly",
                        "practical_effect": exp["inference"]["practical_effect"],
                    }
                )
            service.freeze(
                state["batch_id"], campaign["id"], campaign["confirmation_dataset_id"], claims
            )
            return {}

        def authorize(state):
            auth = self.registry.get("confirmation", "auth:" + state["batch_id"])
            if auth is None:
                payload = interrupt(
                    {"kind": "protected_confirmation_authorization", "batch_id": state["batch_id"]}
                )
                auth = self.registry.get("confirmation", "auth:" + state["batch_id"])
                if auth is None or payload.get("signature") != auth["signature"]:
                    raise PermissionError("No authenticated registry release authorization")
            return {}

        def evaluate(state):
            from .cli import confirmation_service

            service, _ = confirmation_service(self.root)
            auth = self.registry.get("confirmation", "auth:" + state["batch_id"])
            result = service.evaluate(state["batch_id"], auth["signature"])
            return {"result_ref": plain(self.artifacts.put_json(result))}

        def publish(state):
            from .cli import confirmation_service

            service, _ = confirmation_service(self.root)
            findings = service.publish_findings(state["batch_id"])
            return {"finding_ids": [f["id"] for f in findings]}

        g = StateGraph(ConfirmationState)
        for name, node in {
            "freeze": freeze,
            "authorize": authorize,
            "evaluate": evaluate,
            "grade_memory": publish,
        }.items():
            g.add_node(name, node)
        g.add_edge(START, "freeze")
        g.add_edge("freeze", "authorize")
        g.add_edge("authorize", "evaluate")
        g.add_edge("evaluate", "grade_memory")
        g.add_edge("grade_memory", END)
        return g.compile(checkpointer=self.checkpointer)

    def advance_confirmation(self, campaign_id):
        from .cli import confirmation_service

        campaign = self.registry.get("campaigns", campaign_id)
        target = campaign.get("confirmation_dataset_id")
        if not target:
            return {"status": "UNAVAILABLE", "reason": "No protected dataset configured"}
        service, _ = confirmation_service(self.root)
        config = self._config("confirmation-" + campaign_id)
        state = self.confirmation_graph.get_state(config)
        if state.values and state.values.get("workflow_hash") != workflow_hash():
            raise ValueError("incompatible confirmation graph implementation")
        if state.values:
            if not state.next:
                return state.values
            auth = self.registry.get("confirmation", "auth:" + state.values["batch_id"])
            if auth is None:
                return {"status": "AWAITING_AUTHORIZATION", "batch_id": state.values["batch_id"]}
            return self.confirmation_graph.invoke(
                Command(resume={"signature": auth["signature"]}), config, durability="sync"
            )
        if self.campaign_report(campaign_id)["pending_experiments"]:
            return {"status": "WAITING_FOR_REGISTERED_EXPERIMENTS"}
        eligible, reason = service.eligibility(target)
        if not eligible:
            return {"status": "UNAVAILABLE", "reason": reason}
        findings = self.registry.list("findings", campaign_id)
        if not any(f["outcome"] == "EXPLORATORY_SUPPORTED" for f in findings):
            return {"status": "NO_FINALISTS"}
        return self.confirmation_graph.invoke(
            {
                "campaign_id": campaign_id,
                "batch_id": "final-" + campaign_id,
                "workflow_hash": workflow_hash(),
            },
            config,
            durability="sync",
        )

    def run_experiment(self, id):
        config = self._config("experiment-" + id)
        snapshot = self.experiment_graph.get_state(config)
        if snapshot.values:
            if snapshot.values.get("workflow_hash") != workflow_hash():
                raise ValueError("incompatible graph implementation; migrate or create new thread")
            if not snapshot.next:
                return snapshot.values
            return self.resume(id)
        return self.experiment_graph.invoke(
            {"experiment_id": id, "repair_count": 0, "workflow_hash": workflow_hash()},
            config,
            durability="sync",
        )

    def resume(self, id):
        config = self._config("experiment-" + id)
        state = self.experiment_graph.get_state(config)
        if state.values and state.values.get("workflow_hash") != workflow_hash():
            raise ValueError("incompatible graph implementation; migrate or create new thread")
        exp, _, _ = self._records({"experiment_id": id})
        if (
            exp["environment_hash"] != environment_hash()
            or exp["implementation_hash"] != evaluator_hash()
        ):
            raise ValueError("resume incompatible with frozen evaluator/environment")
        if not state.next:
            return state.values
        run_id = state.values.get("run_id")
        event = self.registry.terminal_event(run_id) if run_id else None
        if any(task.interrupts for task in state.tasks):
            if run_id is None:
                campaign = self.registry.get("campaigns", exp["campaign_id"])
                pending = sum(
                    r["state"] in {"QUEUED", "RUNNING", "CANCEL_REQUESTED", "LOST_UNRESOLVED"}
                    for r in self.registry.runs(exp["campaign_id"])
                )
                total_pending = sum(
                    r["state"] in {"QUEUED", "RUNNING", "CANCEL_REQUESTED", "LOST_UNRESOLVED"}
                    for r in self.registry.runs()
                )
                if pending >= campaign["budget"]["max_pending"] or (
                    self.pending_limit is not None and total_pending >= self.pending_limit
                ):
                    return state.values
                return self.experiment_graph.invoke(
                    Command(resume={"capacity_rechecked": True}), config, durability="sync"
                )
            if event is None:
                return state.values
            return self.experiment_graph.invoke(
                Command(resume={"event_id": event["event_id"]}), config, durability="sync"
            )
        return self.experiment_graph.invoke(None, config, durability="sync")

    def run_campaign(self, campaign_id, dataset_id, candidates=None):
        config = self._config("campaign-" + campaign_id)
        state = self.campaign_graph.get_state(config)
        if state.values and state.values.get("workflow_hash") != workflow_hash():
            raise ValueError("incompatible campaign graph implementation")
        if state.values:
            if state.values["dataset_id"] != dataset_id:
                raise ValueError("Campaign resume cannot change its registered dataset")
            return self.advance_campaign(campaign_id)
        return self.campaign_graph.invoke(
            {
                "campaign_id": campaign_id,
                "dataset_id": dataset_id,
                "candidates": candidates or [],
                "workflow_hash": workflow_hash(),
            },
            config,
            durability="sync",
        )

    def advance_campaign(self, campaign_id):
        """Resume preparation or finalization without inventing numerical completion."""
        config = self._config("campaign-" + campaign_id)
        state = self.campaign_graph.get_state(config)
        if not state.values:
            return {"campaign_id": campaign_id, "lifecycle_status": "NOT_STARTED"}
        if state.values.get("workflow_hash") != workflow_hash():
            raise ValueError("incompatible campaign graph implementation")
        if not state.next:
            return state.values
        self.agent_service.bind_campaign(campaign_id)
        if any(task.interrupts for task in state.tasks):
            if self.campaign_report(campaign_id)["pending_experiments"]:
                return state.values
            return self.campaign_graph.invoke(
                Command(resume={"findings_rechecked": True}), config, durability="sync"
            )
        return self.campaign_graph.invoke(None, config, durability="sync")

    def campaign_report(self, id):
        findings = self.registry.list("findings", id)
        terminal = self.registry.get("source", "campaign-report-" + id)
        synthesis = self.registry.get("source", "synthesis-" + id)
        steward = self.registry.get("source", "steward-" + id)
        return {
            "lifecycle_status": "COMPLETED" if terminal else "RUNNING",
            "final_report_ref": terminal["report_ref"] if terminal else None,
            "synthesis_complete": synthesis is not None,
            "steward_complete": steward is not None,
            "campaign_id": id,
            "campaign": self.registry.get("campaigns", id),
            "status": self.registry.status(id),
            "hypotheses": len(self.registry.list("hypotheses", id)),
            "experiments": len(self.registry.list("experiments", id)),
            "findings": findings,
            "pending_experiments": [
                e["id"]
                for e in self.registry.list("experiments", id)
                if not any(f["experiment_id"] == e["id"] for f in findings)
            ],
            "interpretation": "Evidence quality, dataset scope and limitations remain attached to every finding; no trading authorization.",
        }
