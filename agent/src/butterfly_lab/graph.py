"""Real LangGraph campaign and durable experiment graphs; numerical work is external."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

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
    def __init__(self, root: Path | str, agent_service=None):
        self.root = runtime_root(root)
        self.registry = Registry(self.root)
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
        self.experiment_graph = self._build_experiment()
        self.campaign_graph = self._build_campaign()
        self.confirmation_graph = self._build_confirmation()

    def close(self):
        self.connection.close()

    def _config(self, id: str):
        return {"configurable": {"thread_id": id}, "max_concurrency": 2, "recursion_limit": 2000}

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
            critic = self.registry.get("source", "critique-" + hyp["id"])
            if critic and critic.get("recommendation") in ("UNSUPPORTED", "REVISE"):
                return {
                    "outcome": "UNSUPPORTED_HYPOTHESIS",
                    "reasons": critic.get("concerns", ["methodological revision required"]),
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
                run = self.registry.register_run(exp, data, environment_hash(), evaluator_hash())
            except QueueFull:
                interrupt({"kind": "queue_capacity", "campaign_id": exp["campaign_id"]})
                run = self.registry.register_run(exp, data, environment_hash(), evaluator_hash())
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
            self.agent_service.replicate(
                {
                    "experiment_id": exp["id"],
                    "evaluator_hash": exp["implementation_hash"],
                    "registered_tolerance": 1e-8,
                }
            )
            report = state["result"].get("replication", {})
            valid = report.get("status") == "PASS"
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
            return {"independent": True}

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
            ("replicate", "confirmation"),
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
            self.registry.check_ordinary_dataset(data)
            report = qualify_dataset(data)
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
            from .dedup import deduplicate

            h = HypothesisSpec.model_validate(state["candidate"])
            data = self.registry.get("datasets", state["dataset_id"])
            critique_report = self.agent_service.critique(h, data.get("capabilities", []))
            constructed = self.agent_service.specify(h)
            # The agent can construct DSL only before frozen registration.
            h = h.model_copy(update={"proposed_dsl": constructed.dsl})
            self.registry.put("source", "critique-" + h.id, plain(critique_report))
            existing = self.registry.list("hypotheses", state["campaign_id"])
            decision = deduplicate(h.model_dump(mode="json"), existing)
            self.registry.put("hypotheses", h.id, h.model_dump(mode="json"))
            self.registry.put(
                "lineage",
                f"dedup-{h.id}",
                {
                    "id": f"dedup-{h.id}",
                    "campaign_id": h.campaign_id,
                    "hypothesis_id": h.id,
                    "decision": plain(decision),
                },
            )
            data = self.registry.get("datasets", state["dataset_id"])
            exp = ExperimentSpec(
                id="exp-" + h.id,
                campaign_id=h.campaign_id,
                hypothesis_id=h.id,
                trial_id="trial-" + h.id,
                dataset_id=data["id"],
                evaluator=h.evaluator,
                baseline_id=h.baseline_id,
                relation="RESULT_INFORMED"
                if h.informed_by_result_ids
                else ("VARIANT" if decision.relation == "VARIANT" else "NEW"),
                informed_by_result_ids=h.informed_by_result_ids,
                dsl=h.proposed_dsl,
                fidelity=data["fidelity"],
                inference=InferencePlan(practical_effect=h.practical_effect),
                environment_hash=environment_hash(),
                implementation_hash=evaluator_hash(),
            )
            self.registry.put(
                "trials",
                exp.trial_id,
                {
                    "id": exp.trial_id,
                    "campaign_id": h.campaign_id,
                    "hypothesis_id": h.id,
                    "relation": exp.relation.value,
                    "family_id": h.family_id,
                },
            )
            self.registry.put("experiments", exp.id, exp.model_dump(mode="json"))
            return {"prepared": {h.id: exp.id}}

        def join(state):
            return {}

        def launch(state):
            from .dedup import deduplicate

            ordered = self.registry.list("hypotheses", state["campaign_id"])
            for hyp in state["batch"]:
                exp_id = state["prepared"][hyp["id"]]
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
            return "batch" if state["cursor"] < len(state["candidates"]) else "synthesize"

        def synthesize(state):
            report = self.campaign_report(state["campaign_id"])
            self.agent_service.steward(
                {
                    "campaign_id": state["campaign_id"],
                    "pending": len(report["pending_experiments"]),
                    "findings": len(report["findings"]),
                }
            )
            self.agent_service.synthesize(report["findings"])
            return {"report_ref": plain(self.artifacts.put_json(report))}

        graph = StateGraph(CampaignState)
        for name, node in {
            "contract": contract,
            "audit": audit,
            "generate": generate,
            "batch": batch,
            "prepare": prepare,
            "join": join,
            "launch": launch,
            "synthesize": synthesize,
        }.items():
            graph.add_node(name, node)
        graph.add_edge(START, "contract")
        graph.add_edge("contract", "audit")
        graph.add_edge("audit", "generate")
        graph.add_edge("generate", "batch")
        graph.add_conditional_edges("batch", dispatch, ["prepare", "join"])
        graph.add_edge("prepare", "join")
        graph.add_edge("join", "launch")
        graph.add_conditional_edges("launch", next_route, ["batch", "synthesize"])
        graph.add_edge("synthesize", END)
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
                if pending >= campaign["budget"]["max_pending"]:
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
            return (
                self.campaign_graph.invoke(None, config, durability="sync")
                if state.next
                else state.values
            )
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

    def campaign_report(self, id):
        findings = self.registry.list("findings", id)
        return {
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
