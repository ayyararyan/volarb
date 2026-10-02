"""Protected, one-release confirmation service for frozen paired session panels.

The service is trusted; generator and worker subprocesses are OS sandboxed. The
host operator is not an adversary. Confirmation inputs never enter agent state.
An attempt consumes its partition before numerical access, including failures.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import secrets
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field

from .artifacts import plain
from .config import environment_hash, evaluator_hash
from .schemas import canonical_json, digest
from .security import SandboxPolicy, run_sandboxed, verify_boundary


class ConfirmationError(RuntimeError):
    pass


class ConfirmationClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    hypothesis_id: str
    experiment_hash: str = Field(min_length=1)
    implementation_hash: str = Field(min_length=1)
    replication_report_id: str = Field(min_length=1)
    replication_passed: bool
    practical_effect: float = Field(ge=0)
    effect_scale: Literal["absolute", "relative_baseline"] = "absolute"
    higher_is_better: bool = True


class ConfirmationInference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    alpha: float = Field(default=0.05, gt=0, le=0.05)
    program_id: str = "initial-program"
    program_alpha_limit: float = Field(default=0.05, gt=0, le=0.05)
    minimum_sessions: int = Field(default=30, ge=5)
    block_length: int = Field(default=5, ge=1)
    bootstrap_samples: int = Field(default=1999, ge=999, le=100000)
    seed: int = 17
    max_wall_seconds: int = Field(default=60, ge=1, le=3600)
    memory_mb: int = Field(default=1024, ge=128, le=8192)


# Pure-standard-library independent numerical worker. Input contains paired raw
# outcomes, never caller-provided p-values. Hash is frozen in each batch.
_EVALUATION_CODE = r"""
import hashlib, json, math, random, statistics, sys
from datetime import date
request = json.loads(sys.stdin.read())
raw = open(request['source_path'], 'rb').read()
if hashlib.sha256(raw).hexdigest() != request['source_sha256']:
    raise ValueError('Protected source hash changed')
if request['dataset']['kind'] == 'session_panel':
    panel = json.loads(raw)
else:
    from pathlib import Path
    from butterfly_lab.evaluators import evaluate
    panel = {'claims': {}}
    for index, experiment in enumerate(request['frozen_experiments']):
        result = evaluate(experiment, request['dataset'], Path(request['output_dir']) / str(index))
        if result.get('outcome') in ('DATA_LIMITED', 'INVALID_RESULT', 'IMPLEMENTATION_FAILED'):
            raise ValueError('Protected raw evaluation failed validation')
        estimates = result.get('session_estimates', [])
        if not estimates: raise ValueError('No paired session estimates from protected evaluator')
        loss = 'baseline_loss' in estimates[0]
        claim = request['claims'][index]
        if claim['higher_is_better'] == loss:
            raise ValueError('Frozen outcome direction differs from protected evaluator')
        bcol, ccol = ('baseline_loss', 'candidate_loss') if loss else ('baseline_pnl', 'candidate_pnl')
        observed_sessions = [row['session'] for row in estimates]
        expected_sessions = request['dataset']['metadata'].get('confirmation_session_dates')
        if not expected_sessions or observed_sessions != expected_sessions:
            raise ValueError('Evaluated sessions differ from frozen protected opportunity set')
        panel['claims'][claim['hypothesis_id']] = {'session_ids': observed_sessions,
             'baseline': [row[bcol] for row in estimates], 'candidate': [row[ccol] for row in estimates]}
    if hashlib.sha256(open(request['source_path'], 'rb').read()).hexdigest() != request['source_sha256']:
        raise ValueError('Protected source changed during evaluation')
policy = request['inference']
rows = []
common_sessions = None
for index, claim in enumerate(request['claims']):
    data = panel['claims'][claim['hypothesis_id']]
    sessions, baseline, candidate = data['session_ids'], data['baseline'], data['candidate']
    if len(sessions) != len(baseline) or len(sessions) != len(candidate):
        raise ValueError('Unpaired confirmation opportunities')
    if sessions != sorted(sessions) or len(set(sessions)) != len(sessions):
        raise ValueError('Sessions must be unique and chronological')
    for session in sessions: date.fromisoformat(session)
    if common_sessions is None: common_sessions = sessions
    if sessions != common_sessions:
        raise ValueError('Confirmation claims require the frozen common opportunity set')
    if len(sessions) < policy['minimum_sessions']:
        raise ValueError('Insufficient confirmation sessions')
    values = baseline + candidate
    if any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in values):
        raise ValueError('Missing/nonfinite targets must not be silently dropped')
    sign = 1 if claim['higher_is_better'] else -1
    delta = [sign * (c-b) for b,c in zip(baseline,candidate)]
    if claim['effect_scale'] == 'relative_baseline':
        scale = statistics.mean(baseline)
        if scale <= 0: raise ValueError('Relative effect needs a strictly positive baseline scale')
        delta = [value/scale for value in delta]
    n = len(delta)
    block = policy['block_length']
    if block > n//2: raise ValueError('Block length leaves too few effective blocks')
    observed = statistics.mean(delta)
    rng = random.Random(policy['seed'] + index)
    means = []
    for _ in range(policy['bootstrap_samples']):
        sampled = []
        while len(sampled) < n:
            start = rng.randrange(n)
            sampled.extend(delta[(start+j)%n] for j in range(block))
        means.append(statistics.mean(sampled[:n]))
    threshold = claim['practical_effect']
    p = (1 + sum(m-observed+threshold >= observed for m in means))/(len(means)+1)
    means.sort()
    def quantile(q):
        at = q*(len(means)-1); low = int(at); frac = at-low
        return means[low]*(1-frac)+means[min(low+1,len(means)-1)]*frac
    rows.append({'hypothesis_id': claim['hypothesis_id'], 'sessions': n, 'estimate': observed,
                 'practical_effect': threshold, 'ci_low': quantile(policy['alpha']/2),
                 'ci_high': quantile(1-policy['alpha']/2), 'p_value': p})
ordered = sorted(range(len(rows)), key=lambda i: (rows[i]['p_value'], rows[i]['hypothesis_id']))
previous = 0.0
for rank, index in enumerate(ordered):
    previous = max(previous, min(1.0, (len(rows)-rank)*rows[index]['p_value']))
    rows[index]['holm_adjusted_p'] = previous
    supported = previous <= policy['alpha'] and rows[index]['ci_low'] > rows[index]['practical_effect']
    rows[index]['outcome'] = ('INDEPENDENTLY_SUPPORTED' if supported else
                            'REJECTED_FINDING' if rows[index]['ci_high'] < rows[index]['practical_effect'] else 'INCONCLUSIVE')
print(json.dumps({'claims': rows, 'unit': 'session', 'inference': 'circular moving-block bootstrap; one-sided practical-effect null; Holm',
                  'limitations': ['Block-bootstrap inference assumes sufficiently weak dependence and stable sampling.',
                                  'Confidence intervals are per-claim descriptive; batch decisions use Holm-adjusted p-values.',
                                  'Synthetic panels demonstrate software only, never historical edge.']}, allow_nan=False))
"""


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ConfirmationError("Authorization timestamp must be offset-aware")
    return parsed


class ConfirmationService:
    def __init__(
        self, registry: Any, artifacts: Any, signing_key: bytes, authorization_secret: str
    ):
        if len(signing_key) < 32 or len(authorization_secret) < 16:
            raise ValueError(
                "Confirmation requires separate strong signing and authorization secrets"
            )
        self.registry, self.artifacts = registry, artifacts
        self.signing_key, self.authorization_secret = signing_key, authorization_secret
        self.lock_path = Path(registry.root) / ".confirmation.lock"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        with self.lock_path.open("a+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def _sign(self, value: Any) -> str:
        return hmac.new(
            self.signing_key, canonical_json(value).encode(), hashlib.sha256
        ).hexdigest()

    def _verify(self, record: dict[str, Any]) -> None:
        payload = {key: value for key, value in record.items() if key != "signature"}
        if not hmac.compare_digest(str(record.get("signature", "")), self._sign(payload)):
            raise ConfirmationError("Confirmation signature mismatch")

    def eligibility(self, dataset_id: str) -> tuple[bool, str]:
        data = self.registry.get("dataset", dataset_id)
        if data is None:
            return False, "Confirmation dataset is not registered"
        if data.get("partition") != "confirmation" or data.get("prior_exposed", True):
            return False, "No verified unexamined confirmation partition"
        if data.get("exposure_history"):
            return False, "Prior data exposure is recorded"
        if not data.get("source_sha256") or not data.get("source_path"):
            return False, "Protected source identity is missing"
        if data.get("kind") not in (
            "session_panel",
            "spot_bars",
            "option_quotes",
            "option_bars",
            "model",
        ):
            return False, "No protected evaluator exists for this source kind"
        if data.get("kind") != "session_panel" and not data.get("metadata", {}).get(
            "confirmation_session_dates"
        ):
            return False, "Raw confirmation requires a frozen session opportunity set"
        if not data.get("metadata", {}).get("unexamined_attestation", False):
            return False, "Explicit prior-exposure audit attestation is missing"
        key = "consumed:" + data["source_sha256"]
        if self.registry.get("confirmation", key):
            return False, "Confirmation bytes have already been consumed"
        for event in self.registry.list("exposure"):
            if (
                event.get("dataset_id") == dataset_id
                or event.get("source_sha256") == data["source_sha256"]
            ):
                return False, "Confirmation exposure registry records prior access"
        return True, "Eligible subject to authorization and enforced boundary"

    def freeze(
        self,
        batch_id: str,
        campaign_id: str,
        dataset_id: str,
        claims: list[dict[str, Any]],
        inference: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parsed = [ConfirmationClaim.model_validate(row).model_dump(mode="json") for row in claims]
        plan = ConfirmationInference.model_validate(inference or {}).model_dump(mode="json")
        if not parsed or len({row["hypothesis_id"] for row in parsed}) != len(parsed):
            raise ConfirmationError("Freeze a nonempty unique finalist family")
        if not all(row["replication_passed"] for row in parsed):
            raise ConfirmationError(
                "Independent implementation replication must precede confirmation"
            )
        registered = self.registry.list("experiment", campaign_id)
        frozen_experiments = []
        for claim in parsed:
            matching = [
                exp
                for exp in registered
                if exp["hypothesis_id"] == claim["hypothesis_id"]
                and digest(exp) == claim["experiment_hash"]
                and exp["implementation_hash"] == claim["implementation_hash"]
            ]
            report = self.registry.get("validation", claim["replication_report_id"])
            if (
                not matching
                or not report
                or report["status"] != "PASS"
                or not all(c["passed"] for c in report["checks"])
            ):
                raise ConfirmationError(
                    "Frozen finalist lacks verified registered implementation evidence"
                )
            if report["permitted_evidence_ceiling"]["replication"] != "independently_reconstructed":
                raise ConfirmationError("Replication report is not independently reconstructed")
            if report["id"] != "replication-" + matching[0]["id"]:
                raise ConfirmationError(
                    "Replication report is not bound to the finalist experiment"
                )
            self.artifacts.verify_tree(report)
            frozen_experiments.append(matching[0])
        campaign = self.registry.get("campaign", campaign_id)
        if campaign is None or not campaign.get("approved"):
            raise ConfirmationError("Confirmation requires an approved campaign")
        ok, reason = self.eligibility(dataset_id)
        if not ok:
            raise ConfirmationError(reason)
        data = self.registry.get("dataset", dataset_id)
        record = {
            "batch_id": batch_id,
            "campaign_id": campaign_id,
            "dataset_id": dataset_id,
            "source_sha256": data["source_sha256"],
            "claims": parsed,
            "inference": plan,
            "frozen_experiments": frozen_experiments,
            "evaluation_code_hash": hashlib.sha256(_EVALUATION_CODE.encode()).hexdigest(),
            "runtime_evaluator_hash": evaluator_hash(),
            "runtime_environment_hash": environment_hash(),
            "graph_version": "1",
            "schema_version": "1",
            "provenance": data["provenance"],
        }
        record["signature"] = self._sign(record)
        self.registry.put("confirmation", "batch:" + batch_id, record)
        return record

    def authorize(
        self, batch_id: str, principal: str, expires_at: str, authorization_secret: str
    ) -> dict[str, Any]:
        if not hmac.compare_digest(authorization_secret, self.authorization_secret):
            raise PermissionError("Protected release authorization denied")
        if not principal or _aware(expires_at) <= datetime.now(timezone.utc):
            raise ConfirmationError("Authorization requires a principal and future expiry")
        with self._lock():
            batch = self.registry.get("confirmation", "batch:" + batch_id)
            if batch is None:
                raise ConfirmationError("Unknown frozen batch")
            self._verify(batch)
            prior = self.registry.get("confirmation", "auth:" + batch_id)
            if prior:
                self._verify(prior)
                return prior
            plan = batch["inference"]
            spent = sum(
                row["alpha"]
                for row in self.registry.list("confirmation")
                if row.get("kind") == "authorization"
                and row.get("program_id") == plan["program_id"]
            )
            if spent + plan["alpha"] > plan["program_alpha_limit"] + 1e-12:
                raise ConfirmationError("Program-level confirmation error budget exhausted")
            record = {
                "kind": "authorization",
                "batch_id": batch_id,
                "batch_hash": digest(batch),
                "principal": principal,
                "expires_at": expires_at,
                "campaign_id": batch["campaign_id"],
                "program_id": plan["program_id"],
                "alpha": plan["alpha"],
                "nonce": secrets.token_hex(16),
            }
            record["signature"] = self._sign(record)
            self.registry.put("confirmation", "auth:" + batch_id, record)
            return record

    def evaluate(self, batch_id: str, token: str) -> dict[str, Any]:
        # An accepted bundle is read idempotently; no numerical reevaluation.
        prior = self.registry.get("confirmation", "result:" + batch_id)
        if prior:
            return self.report(batch_id)
        with self._lock():
            batch = self.registry.get("confirmation", "batch:" + batch_id)
            authorization = self.registry.get("confirmation", "auth:" + batch_id)
            if not batch or not authorization:
                raise PermissionError("No frozen batch and explicit release authorization")
            self._verify(batch)
            self._verify(authorization)
            if not hmac.compare_digest(token, authorization["signature"]):
                raise PermissionError("Invalid confirmation release token")
            if _aware(authorization["expires_at"]) <= datetime.now(timezone.utc):
                raise PermissionError("Confirmation release authorization expired")
            if authorization["batch_hash"] != digest(batch):
                raise ConfirmationError("Authorized batch differs from frozen batch")
            if (
                batch["evaluation_code_hash"]
                != hashlib.sha256(_EVALUATION_CODE.encode()).hexdigest()
            ):
                raise ConfirmationError("Confirmation evaluator version changed")
            if (
                batch["runtime_evaluator_hash"] != evaluator_hash()
                or batch["runtime_environment_hash"] != environment_hash()
            ):
                raise ConfirmationError(
                    "Confirmation evaluator/environment differs from the frozen runtime"
                )
            ok, reason = self.eligibility(batch["dataset_id"])
            if not ok:
                raise ConfirmationError(reason)
            verify_boundary()  # fail closed before reserving/consuming an inaccessible partition
            data = self.registry.get("dataset", batch["dataset_id"])
            source = Path(data["source_path"]).expanduser().resolve()
            if not source.is_file() or source.is_symlink():
                raise ConfirmationError("Protected paired-panel source is inaccessible")
            service_id = "confirmation:" + batch_id
            self.registry.reserve_service_budget(
                batch["campaign_id"],
                service_id,
                batch["inference"]["max_wall_seconds"],
                storage_bytes=10_000_000,
                service="confirmation",
            )
            consumed = {
                "kind": "consumption",
                "batch_id": batch_id,
                "dataset_id": batch["dataset_id"],
                "source_sha256": batch["source_sha256"],
                "campaign_id": batch["campaign_id"],
                "attempt_id": secrets.token_hex(16),
                "state": "CONSUMED_BEFORE_EVALUATION",
            }
            self.registry.put("confirmation", "consumed:" + batch["source_sha256"], consumed)
            self.registry.put(
                "exposure",
                "confirmation:" + batch_id,
                {**consumed, "access_class": "confirmation", "purpose": "single protected batch"},
            )
        request = {
            "source_path": str(source),
            "source_sha256": batch["source_sha256"],
            "claims": batch["claims"],
            "inference": batch["inference"],
            "dataset": data,
            "frozen_experiments": batch["frozen_experiments"],
        }
        plan = batch["inference"]
        try:
            with tempfile.TemporaryDirectory(
                prefix="confirmation-", dir=self.registry.root
            ) as temp:
                scratch = Path(temp).resolve()
                request["output_dir"] = str(scratch)
                package_root = Path(__file__).resolve().parent.parent
                process = run_sandboxed(
                    [sys.executable, "-c", _EVALUATION_CODE],
                    SandboxPolicy(
                        read_paths=(source, package_root),
                        write_paths=(scratch,),
                        timeout_seconds=plan["max_wall_seconds"],
                        memory_mb=plan["memory_mb"],
                    ),
                    input_text=canonical_json(request),
                    env={"PYTHONPATH": str(package_root)},
                )
                protected_artifacts = {}
                if process.returncode == 0:
                    files = sorted(path for path in scratch.rglob("*") if path.is_file())
                    if sum(path.stat().st_size for path in files) > 10_000_000:
                        raise ConfirmationError(
                            "Protected output exceeded its reserved storage budget"
                        )
                    for path in files:
                        if path.is_symlink() or not path.resolve().is_relative_to(scratch):
                            raise ConfirmationError("Protected artifact escaped scratch directory")
                        media = (
                            "application/vnd.apache.parquet"
                            if path.suffix == ".parquet"
                            else "application/octet-stream"
                        )
                        protected_artifacts[str(path.relative_to(scratch))] = plain(
                            self.artifacts.put_file(path, media)
                        )
        except BaseException:
            self.registry.finish_service(service_id, success=False)
            raise
        if process.returncode:
            self.registry.finish_service(service_id, success=False)
            self.registry.add_event(
                "CONFIRMATION_FAILED_CONSUMED",
                batch_id,
                {
                    "returncode": process.returncode,
                    "stderr_hash": hashlib.sha256(process.stderr.encode()).hexdigest(),
                },
            )
            raise ConfirmationError("Protected computation failed; partition remains consumed")
        result = json.loads(process.stdout)
        result["protected_artifact_refs"] = protected_artifacts
        result.update(
            {
                "batch_id": batch_id,
                "batch_hash": digest(batch),
                "campaign_id": batch["campaign_id"],
                "source_sha256": batch["source_sha256"],
                "provenance": batch["provenance"],
                "protected_confirmation": True,
                "synthetic_demonstration": batch["provenance"] == "SYNTHETIC",
            }
        )
        if batch["provenance"] == "SYNTHETIC":
            # Software pathway is exercised, but never advertise synthetic market evidence.
            for row in result["claims"]:
                row["demonstration_outcome"] = row["outcome"]
                row["outcome"] = (
                    "EXPLORATORY_SUPPORTED"
                    if row["outcome"] == "INDEPENDENTLY_SUPPORTED"
                    else row["outcome"]
                )
                row["evidence_ceiling"] = "F0_SYNTHETIC"
        result["signature"] = self._sign(result)
        ref = plain(self.artifacts.put_json(result))
        self.registry.put(
            "confirmation",
            "result:" + batch_id,
            {
                "kind": "result",
                "batch_id": batch_id,
                "campaign_id": batch["campaign_id"],
                "artifact_ref": ref,
            },
        )
        self.registry.finish_service(service_id, success=True, result_ref=ref)
        return result

    def report(self, batch_id: str) -> dict[str, Any]:
        record = self.registry.get("confirmation", "result:" + batch_id)
        if record is None:
            raise ConfirmationError("No accepted result bundle for batch")
        bundle = self.artifacts.read_json(record["artifact_ref"])
        self._verify(bundle)
        return bundle

    def publish_findings(self, batch_id: str) -> list[dict[str, Any]]:
        """Deterministically supersede exploratory findings using the signed bundle."""
        from .schemas import ResearchFinding

        bundle = self.report(batch_id)
        batch = self.registry.get("confirmation", "batch:" + batch_id)
        dataset = self.registry.get("dataset", batch["dataset_id"])
        result_record = self.registry.get("confirmation", "result:" + batch_id)
        published = []
        for row in bundle["claims"]:
            hypothesis = self.registry.get("hypothesis", row["hypothesis_id"])
            if hypothesis is None:
                raise ConfirmationError("Finalist hypothesis disappeared from registry")
            claim = next(c for c in batch["claims"] if c["hypothesis_id"] == row["hypothesis_id"])
            experiment = next(
                e for e in batch["frozen_experiments"] if e["hypothesis_id"] == row["hypothesis_id"]
            )
            report = self.registry.get("validation", claim["replication_report_id"])
            prior = [
                finding["id"]
                for finding in self.registry.list("finding", batch["campaign_id"])
                if finding["hypothesis_id"] == row["hypothesis_id"]
                and finding["evidence_grade"]["independence"] != "protected_confirmation"
            ]
            finding = ResearchFinding(
                id="confirmed-"
                + digest({"bundle": bundle["signature"], "hypothesis": row["hypothesis_id"]})[:24],
                campaign_id=batch["campaign_id"],
                hypothesis_id=row["hypothesis_id"],
                experiment_id=experiment["id"],
                outcome=row["outcome"],
                claim="Frozen paired-session claim evaluated once under the registered protected batch.",
                estimate_refs=[result_record["artifact_ref"]],
                evidence_grade={
                    "implementation": "verified",
                    "fidelity": dataset["fidelity"],
                    "independence": "protected_confirmation",
                    "precision": "informative"
                    if row["outcome"] != "INCONCLUSIVE"
                    else "insufficient",
                    "replication": "independently_reconstructed",
                },
                dataset_id=batch["dataset_id"],
                assumptions=["Registered block-dependence and negligible-impact assumptions"],
                limitations=bundle["limitations"]
                + (
                    ["Synthetic software demonstration; no historical edge evidence"]
                    if bundle["synthetic_demonstration"]
                    else []
                ),
                search_family_id=hypothesis["family_id"],
                validation_refs=[self.artifacts.put_json(report)],
                supersedes=prior,
            )
            payload = finding.model_dump(mode="json")
            self.registry.put("finding", finding.id, payload)
            self.registry.put(
                "memory",
                finding.id,
                {
                    "id": finding.id,
                    "campaign_id": batch["campaign_id"],
                    "finding_id": finding.id,
                    "evidence_ref": result_record["artifact_ref"],
                    "evidence_grade": payload["evidence_grade"],
                    "limitations": payload["limitations"],
                    "supersedes": prior,
                },
            )
            published.append(payload)
        return published

    def register_descendant(self, parent_batch_id: str, child_hypothesis_id: str) -> str:
        if self.registry.get("confirmation", "result:" + parent_batch_id) is None:
            raise ConfirmationError("No released feedback for descendant")
        record = {
            "parent_batch_id": parent_batch_id,
            "child_hypothesis_id": child_hypothesis_id,
            "relation": "RESULT_INFORMED",
            "requires_new_confirmation_data": True,
        }
        key = "feedback:" + digest(record)
        self.registry.put("lineage", key, record)
        return key
