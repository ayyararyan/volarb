"""Single controlled SQLite writer; immutable science and fenced operational state.

Every mutation takes an interprocess flock and BEGIN IMMEDIATE. The lock is not a
substitute for SQL constraints: unique execution keys, attempts and ingestion are
also enforced by SQLite. An expired lease never by itself requeues computation.
"""

from __future__ import annotations

import fcntl
import builtins
import hashlib
import json
import math
import os
import socket
import sqlite3
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .artifacts import ArtifactStore, canonical_bytes, digest, plain

SCHEMA_VERSION = "1"
GRAPH_VERSION = "1"
TERMINAL = {"COMPLETED", "INGESTED", "FAILED", "CANCELLED", "INVALID_RESULT"}
KINDS = {
    "campaign": "campaigns",
    "hypothesis": "hypotheses",
    "dataset": "datasets",
    "experiment": "experiments",
    "trial": "trials",
    "artifact": "artifacts",
    "validation": "validations",
    "finding": "findings",
    "approval": "approval_events",
    "lineage": "lineage_edges",
    "exposure": "exposure_events",
    "spec_version": "spec_versions",
    "baseline": "baselines",
    "confirmation": "confirmations",
    "memory": "research_memory",
    "source": "sources",
    "benchmark": "benchmarks",
    "generation": "generations",
}


class RegistryError(ValueError):
    pass


class ConflictError(RegistryError):
    pass


class BudgetExceeded(RegistryError):
    pass


class QueueFull(BudgetExceeded):
    """Temporary backpressure, not exhaustion of the scientific budget."""


class SourceBindingError(RegistryError):
    """An external dataset is not bound to immutable, verified input bytes."""


def verify_source_binding(dataset: dict[str, Any]) -> tuple[Path, ...]:
    """Bind exact selected files; usable in admission and the sandboxed child.

    Directory source_sha256 is the canonical digest of metadata.file_sha256,
    whose safe relative names must exactly equal the selected glob members.
    Inline rows and controlled synthetic generators are bound by the run spec.
    """
    source = dataset.get("source_path")
    meta = dataset.get("metadata", {})
    if not source:
        if "rows" in meta or dataset.get("kind") == "synthetic":
            return ()
        raise SourceBindingError("DATA_LIMITED: external source_path and byte binding are required")
    path = Path(source).expanduser()
    expected = dataset.get("source_sha256")
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(c not in "0123456789abcdef" for c in expected)
    ):
        raise SourceBindingError("DATA_LIMITED: external source requires source_sha256")
    if path.is_symlink() or not path.exists():
        raise SourceBindingError("DATA_LIMITED: source is missing or a symlink")
    if path.is_dir():
        members = meta.get("file_sha256")
        if not isinstance(members, dict) or not members or digest(members) != expected:
            raise SourceBindingError(
                "DATA_LIMITED: directory requires an exact hash-bound file_sha256 map"
            )
        paths = {}
        for name, sha in members.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
                raise SourceBindingError("DATA_LIMITED: unsafe directory member")
            target = path / relative
            if (
                not target.is_file()
                or target.is_symlink()
                or not target.resolve().is_relative_to(path.resolve())
            ):
                raise SourceBindingError(
                    "DATA_LIMITED: directory member missing or escapes source root"
                )
            paths[name] = (target, sha)
        selected = {str(p.relative_to(path)) for p in path.glob(meta.get("glob", "*.parquet"))}
        if selected != set(paths):
            raise SourceBindingError(
                "DATA_LIMITED: selected directory members differ from byte binding"
            )
        files = list(paths.values())
    elif path.is_file():
        files = [(path, expected)]
    else:
        raise SourceBindingError("DATA_LIMITED: source is not a regular file or directory")
    for target, sha in files:
        h = hashlib.sha256()
        try:
            with target.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
        except OSError as error:
            raise SourceBindingError("DATA_LIMITED: source bytes unavailable") from error
        if h.hexdigest() != sha:
            raise SourceBindingError("DATA_LIMITED: source bytes differ from registered hash")
    return tuple(p.resolve() for p, _ in files)


class StaleFence(RegistryError):
    pass


def process_identity(pid: int) -> str | None:
    """OS process birth identity prevents PID-reuse being mistaken for liveness."""
    if pid <= 0:
        return None
    try:
        if Path("/proc").is_dir():
            raw = Path(f"/proc/{pid}/stat").read_text()
            return raw.rsplit(")", 1)[1].split()[19]
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def process_alive(pid: int | None, identity: str | None) -> bool | None:
    if pid is None or identity is None:
        return None
    current = process_identity(pid)
    if current is not None:
        return current == identity
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    return None  # alive but identity unreadable: do not replace


def _kind(value: str) -> str:
    if value in KINDS:
        return value
    for singular, plural in KINDS.items():
        if plural == value:
            return singular
    raise RegistryError("Unsupported registry entity kind: " + value)


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("payload", "experiment", "dataset", "resources", "result_ref", "failure", "limits"):
        if result.get(key) is not None:
            result[key] = json.loads(result[key])
    return result


class Registry:
    def __init__(self, root: Path | str):
        from .config import runtime_root

        self.root = runtime_root(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "registry.sqlite3"
        self.lock_path = self.root / ".registry.lock"
        self.artifacts = ArtifactStore(self.root / "artifacts")
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def _reader(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.lock_path.open("a+b") as lock:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _migrate(self) -> None:
        with self.lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            db = self._connect()
            try:
                db.execute("PRAGMA journal_mode=WAL")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1, 2):
                    raise RegistryError(f"Unsupported registry schema {version}; refusing resume")
                if version == 0:
                    db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
                    CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,campaign_id TEXT,
                      payload TEXT NOT NULL,hash TEXT NOT NULL,created_at REAL NOT NULL,
                      PRIMARY KEY(kind,id));
                    CREATE INDEX records_campaign ON records(kind,campaign_id);
                    CREATE TABLE campaign_runtime(id TEXT PRIMARY KEY,limits TEXT NOT NULL,
                      cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)));
                    CREATE TABLE runs(run_id TEXT PRIMARY KEY,execution_key TEXT NOT NULL UNIQUE,
                      campaign_id TEXT NOT NULL REFERENCES campaign_runtime(id),experiment_id TEXT NOT NULL,
                      experiment TEXT NOT NULL,dataset TEXT NOT NULL,resources TEXT NOT NULL,
                      environment_hash TEXT NOT NULL,evaluator_hash TEXT NOT NULL,
                      graph_version TEXT NOT NULL,schema_version TEXT NOT NULL,
                      state TEXT NOT NULL,fence INTEGER NOT NULL DEFAULT 0,attempt_id TEXT,
                      result_ref TEXT,failure TEXT,created_at REAL NOT NULL,updated_at REAL NOT NULL,
                      cancel_requested INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,
                      priority INTEGER NOT NULL DEFAULT 0);
                    CREATE INDEX runs_queue ON runs(state,priority,created_at);
                    CREATE TABLE attempts(attempt_id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(run_id),
                      fence INTEGER NOT NULL,worker_id TEXT NOT NULL,host TEXT NOT NULL,pid INTEGER,
                      process_identity TEXT,lease_until REAL NOT NULL,heartbeat_at REAL NOT NULL,
                      state TEXT NOT NULL,started_at REAL NOT NULL,finished_at REAL,
                      UNIQUE(run_id,fence));
                    CREATE TABLE jobs(attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),
                      child_pid INTEGER,child_identity TEXT,scratch TEXT NOT NULL,started_at REAL NOT NULL);
                    CREATE TABLE outbox(event_id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(run_id),
                      event_type TEXT NOT NULL,state TEXT NOT NULL,created_at REAL NOT NULL,
                      UNIQUE(run_id,event_type));
                    CREATE TABLE events(event_id TEXT PRIMARY KEY,event_type TEXT NOT NULL,
                      subject TEXT NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL,created_at REAL NOT NULL);
                    CREATE INDEX events_subject ON events(subject,created_at);
                    CREATE TABLE budget_reservations(run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                      campaign_id TEXT NOT NULL,runs INTEGER NOT NULL,cpu_seconds REAL NOT NULL,
                      storage_bytes INTEGER NOT NULL,state TEXT NOT NULL,actual_cpu_seconds REAL);
                    CREATE TABLE ingestion(run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                      result_hash TEXT NOT NULL,ingested_at REAL NOT NULL);
                    INSERT INTO migrations VALUES(1,strftime('%s','now'));
                    PRAGMA user_version=1;
                    COMMIT;
                    """)
                if version < 2:
                    db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS service_jobs(
                      reservation_id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL REFERENCES campaign_runtime(id),
                      service TEXT NOT NULL,cpu_seconds REAL NOT NULL,storage_bytes INTEGER NOT NULL,
                      payload_hash TEXT NOT NULL,state TEXT NOT NULL,result_ref TEXT,created_at REAL NOT NULL);
                    INSERT OR IGNORE INTO migrations VALUES(2,strftime('%s','now'));
                    PRAGMA user_version=2;
                    COMMIT;
                    """)
                for singular, plural in KINDS.items():
                    db.execute(
                        f"CREATE VIEW IF NOT EXISTS {plural} AS SELECT * FROM records WHERE kind='{singular}'"
                    )
                os.chmod(self.path, 0o600)
            finally:
                db.close()

    def _event(
        self,
        db: sqlite3.Connection,
        event_type: str,
        subject: str,
        payload: Any,
        event_id: str | None = None,
    ) -> str:
        value = canonical_bytes(payload).decode()
        hashed = digest({"type": event_type, "subject": subject, "payload": payload})
        event_id = event_id or str(uuid.uuid4())
        prior = db.execute("SELECT hash FROM events WHERE event_id=?", (event_id,)).fetchone()
        if prior:
            if prior[0] != hashed:
                raise ConflictError("Conflicting idempotent event")
            return event_id
        db.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?)",
            (event_id, event_type, subject, value, hashed, time.time()),
        )
        return event_id

    def _record(self, db: sqlite3.Connection, kind: str, id: str, payload: Any) -> None:
        payload = plain(payload)
        hashed = digest(payload)
        prior = db.execute("SELECT hash FROM records WHERE kind=? AND id=?", (kind, id)).fetchone()
        if prior:
            if prior[0] != hashed:
                raise ConflictError("Conflicting immutable evidence record")
            return
        db.execute(
            "INSERT INTO records VALUES(?,?,?,?,?,?)",
            (
                kind,
                id,
                payload.get("campaign_id"),
                canonical_bytes(payload).decode(),
                hashed,
                time.time(),
            ),
        )

    def add_event(
        self, event_type: str, subject: str, payload: Any, event_id: str | None = None
    ) -> str:
        with self.transaction() as db:
            return self._event(db, event_type, subject, payload, event_id)

    def put(self, kind: str, id: str, payload: Any) -> str:
        kind, payload = _kind(kind), plain(payload)
        from . import schemas

        model_name = {
            "campaign": "CampaignSpec",
            "hypothesis": "HypothesisSpec",
            "dataset": "DatasetManifest",
            "experiment": "ExperimentSpec",
            "validation": "ValidationReport",
            "finding": "ResearchFinding",
            "approval": "Approval",
        }.get(kind)
        if model_name:
            payload = getattr(schemas, model_name).model_validate(payload).model_dump(mode="json")
        if not isinstance(payload, dict) or not id:
            raise RegistryError("Entity must have a nonempty ID and object payload")
        if payload.get("id", id) != id:
            raise ConflictError("Entity key differs from payload ID")
        hashed = digest(payload)
        with self.transaction() as db:
            prior = db.execute(
                "SELECT hash FROM records WHERE kind=? AND id=?", (kind, id)
            ).fetchone()
            if prior:
                if prior[0] != hashed:
                    raise ConflictError("Immutable specification/evidence conflict: " + id)
                return id
            db.execute(
                "INSERT INTO records VALUES(?,?,?,?,?,?)",
                (
                    kind,
                    id,
                    payload.get("campaign_id"),
                    canonical_bytes(payload).decode(),
                    hashed,
                    time.time(),
                ),
            )
            if kind == "campaign":
                limits = payload.get("budget", {})
                if not isinstance(limits, dict):
                    raise RegistryError("Campaign requires explicit budget")
                for field in ("max_runs", "cpu_seconds", "storage_bytes"):
                    value = limits.get(field, 0)
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or value < 0
                    ):
                        raise RegistryError("Invalid campaign budget: " + field)
                db.execute(
                    "INSERT INTO campaign_runtime(id,limits) VALUES(?,?)",
                    (id, canonical_bytes(limits).decode()),
                )
            self._event(db, "ENTITY_REGISTERED", id, {"kind": kind, "hash": hashed})
            if kind in {"hypothesis", "experiment", "dataset"}:
                self._record(
                    db,
                    "spec_version",
                    f"{kind}:{id}:{hashed}",
                    {
                        "entity_kind": kind,
                        "entity_id": id,
                        "hash": hashed,
                        "campaign_id": payload.get("campaign_id"),
                        "schema_version": payload.get("schema_version", "1"),
                    },
                )
        return id

    def get(self, kind: str, id: str) -> dict[str, Any] | None:
        with self._reader() as db:
            row = db.execute(
                "SELECT payload FROM records WHERE kind=? AND id=?", (_kind(kind), id)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def list(self, kind: str, campaign_id: str | None = None) -> list[dict[str, Any]]:
        with self._reader() as db:
            query, args = "SELECT payload FROM records WHERE kind=?", [_kind(kind)]
            if campaign_id is not None:
                query += " AND campaign_id=?"
                args.append(campaign_id)
            return [json.loads(r[0]) for r in db.execute(query + " ORDER BY created_at,id", args)]

    def register_run(
        self,
        experiment: Any,
        manifest: Any,
        environment_hash: str,
        evaluator_hash: str,
        *,
        pending_limit: int | None = None,
    ) -> str:
        from .schemas import DatasetManifest, ExperimentSpec

        experiment = ExperimentSpec.model_validate(plain(experiment)).model_dump(mode="json")
        manifest = DatasetManifest.model_validate(plain(manifest)).model_dump(mode="json")
        self.check_ordinary_dataset(manifest)
        verify_source_binding(manifest)
        if not environment_hash or not evaluator_hash:
            raise RegistryError("Environment and evaluator fingerprints are required")
        campaign = experiment.get("campaign_id")
        if not campaign:
            raise RegistryError("Experiment requires campaign_id")
        if experiment.get("dataset_id", manifest["id"]) != manifest["id"]:
            raise ConflictError("Experiment and dataset identity disagree")
        schema = str(experiment.get("schema_version", SCHEMA_VERSION))
        graph = str(experiment.get("graph_version", GRAPH_VERSION))
        if schema != SCHEMA_VERSION or graph != GRAPH_VERSION:
            raise RegistryError("Incompatible graph/schema version")
        resources = {
            "cpu_seconds": 60.0,
            "wall_seconds": 60.0,
            "memory_mb": 1024,
            "storage_bytes": 10485760,
            **experiment.get("resources", {}),
        }
        for key, value in resources.items():
            if key in ("cpu_seconds", "wall_seconds", "memory_mb", "storage_bytes"):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value <= 0
                ):
                    raise RegistryError("Run resources must be finite positive numbers")
        execution_key = digest(
            {
                "experiment": experiment,
                "dataset": manifest,
                "environment": environment_hash,
                "evaluator": evaluator_hash,
            }
        )
        run_id = "run-" + execution_key[:32]
        now = time.time()
        with self.transaction() as db:
            old = db.execute(
                "SELECT run_id FROM runs WHERE execution_key=?", (execution_key,)
            ).fetchone()
            if old:
                return old[0]
            registered = db.execute(
                "SELECT payload FROM records WHERE kind='experiment' AND id=?", (experiment["id"],)
            ).fetchone()
            if registered and digest(json.loads(registered[0])) != digest(experiment):
                raise ConflictError("Run does not match registered immutable experiment")
            for kind, id in (
                ("hypothesis", experiment["hypothesis_id"]),
                ("trial", experiment["trial_id"]),
            ):
                prior = db.execute(
                    "SELECT payload FROM records WHERE kind=? AND id=?", (kind, id)
                ).fetchone()
                if prior is None:
                    raise RegistryError("Numerical run requires registered " + kind)
                parent = json.loads(prior[0])
                if parent.get("campaign_id") != campaign:
                    raise ConflictError("Numerical lineage crosses campaign budget scope")
                if kind == "trial" and parent.get("hypothesis_id") != experiment["hypothesis_id"]:
                    raise ConflictError("Trial belongs to another hypothesis")
                if kind == "hypothesis":
                    hypothesis = parent
                if kind == "trial" and parent.get("relation", "NEW") != experiment["relation"]:
                    raise ConflictError("Trial and experiment lineage relation disagree")
            # Count registered selection alternatives, not reruns or Monte Carlo draws.
            # This check shares the transaction with the run/budget/outbox writes.
            if experiment["relation"] in ("NEW", "VARIANT", "RESULT_INFORMED"):
                selection_trials = set()
                for row in db.execute(
                    "SELECT experiment FROM runs WHERE campaign_id=?", (campaign,)
                ):
                    prior_exp = json.loads(row[0])
                    if prior_exp["hypothesis_id"] == experiment["hypothesis_id"] and prior_exp[
                        "relation"
                    ] in ("NEW", "VARIANT", "RESULT_INFORMED"):
                        selection_trials.add(prior_exp["trial_id"])
                selection_trials.add(experiment["trial_id"])
                if len(selection_trials) > hypothesis["search_budget"]:
                    raise BudgetExceeded("Registered hypothesis search budget exhausted")
            state = db.execute("SELECT * FROM campaign_runtime WHERE id=?", (campaign,)).fetchone()
            if state is None or state["cancelled"]:
                raise RegistryError("Campaign absent or cancelled")
            contract = json.loads(
                db.execute(
                    "SELECT payload FROM records WHERE kind='campaign' AND id=?", (campaign,)
                ).fetchone()[0]
            )
            if not contract.get("approved"):
                raise RegistryError("Campaign budget/scope is not approved")
            limits = json.loads(state["limits"])
            used = list(
                db.execute(
                    "SELECT COALESCE(SUM(runs),0),COALESCE(SUM(cpu_seconds),0),COALESCE(SUM(storage_bytes),0) FROM budget_reservations WHERE campaign_id=?",
                    (campaign,),
                ).fetchone()
            )
            services = db.execute(
                "SELECT count(*),COALESCE(SUM(cpu_seconds),0),COALESCE(SUM(storage_bytes),0) FROM service_jobs WHERE campaign_id=?",
                (campaign,),
            ).fetchone()
            used = [a + b for a, b in zip(used, services)]
            # RLIMIT_CPU has whole-second granularity: reserve the actual ceiling.
            wanted = (1, max(1, math.ceil(resources["cpu_seconds"])), resources["storage_bytes"])
            for index, key in enumerate(("max_runs", "cpu_seconds", "storage_bytes")):
                if used[index] + wanted[index] > limits.get(key, 0):
                    raise BudgetExceeded("Campaign budget exhausted: " + key)
            if resources["memory_mb"] > limits.get("memory_mb", 4096):
                raise BudgetExceeded("Run memory exceeds approved campaign ceiling")
            pending = db.execute(
                "SELECT count(*) FROM runs WHERE campaign_id=? AND state IN ('QUEUED','RUNNING','CANCEL_REQUESTED','LOST_UNRESOLVED')",
                (campaign,),
            ).fetchone()[0]
            if pending >= limits.get("max_pending", 20):
                raise QueueFull("Backpressure: campaign pending queue is full")
            if pending_limit is not None:
                total_pending = db.execute(
                    "SELECT count(*) FROM runs WHERE state IN ('QUEUED','RUNNING','CANCEL_REQUESTED','LOST_UNRESOLVED')"
                ).fetchone()[0]
                if total_pending >= pending_limit:
                    raise QueueFull("Backpressure: machine pending queue is full")
            # Register the scientific inputs in the SAME transaction as reservation.
            for kind, value in (("experiment", experiment), ("dataset", manifest)):
                prev = db.execute(
                    "SELECT hash FROM records WHERE kind=? AND id=?", (kind, value["id"])
                ).fetchone()
                if prev and prev[0] != digest(value):
                    raise ConflictError("Immutable input conflict")
                if not prev:
                    db.execute(
                        "INSERT INTO records VALUES(?,?,?,?,?,?)",
                        (
                            kind,
                            value["id"],
                            value.get("campaign_id"),
                            canonical_bytes(value).decode(),
                            digest(value),
                            now,
                        ),
                    )
            # Freeze the already-observed model lineage with submission, before
            # any worker can claim the outbox. Model changes never rewrite it.
            generations = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM records WHERE kind='generation' AND campaign_id=? ORDER BY id",
                    (campaign,),
                )
            ]
            self._record(
                db,
                "source",
                "provider-context-" + run_id,
                {
                    "campaign_id": campaign,
                    "run_id": run_id,
                    "scope": "campaign role calls observed before numerical submission",
                    "models": sorted({g["model"] for g in generations}),
                    "model_prompt_refs": [plain(self.artifacts.put_json(g)) for g in generations],
                },
            )
            db.execute(
                """INSERT INTO runs(run_id,execution_key,campaign_id,experiment_id,experiment,dataset,resources,
                environment_hash,evaluator_hash,graph_version,schema_version,state,created_at,updated_at,priority)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,'QUEUED',?,?,?)""",
                (
                    run_id,
                    execution_key,
                    campaign,
                    experiment["id"],
                    canonical_bytes(experiment).decode(),
                    canonical_bytes(manifest).decode(),
                    canonical_bytes(resources).decode(),
                    environment_hash,
                    evaluator_hash,
                    graph,
                    schema,
                    now,
                    now,
                    int(experiment.get("priority", 0)),
                ),
            )
            db.execute(
                "INSERT INTO budget_reservations VALUES(?,?,?,?,?,'RESERVED',NULL)",
                (run_id, campaign, *wanted),
            )
            db.execute(
                "INSERT INTO outbox VALUES(?,?,'SUBMIT','PENDING',?)",
                ("submit-" + run_id, run_id, now),
            )
            self._event(db, "RUN_REGISTERED", run_id, {"execution_key": execution_key})
            self._record(
                db,
                "spec_version",
                "run-spec:" + execution_key,
                {
                    "campaign_id": campaign,
                    "run_id": run_id,
                    "experiment_hash": digest(experiment),
                    "dataset_hash": digest(manifest),
                    "environment_hash": environment_hash,
                    "evaluator_hash": evaluator_hash,
                    "graph_version": graph,
                    "schema_version": schema,
                },
            )
            if experiment.get("parent_experiment_id") or experiment.get("informed_by_result_ids"):
                self._record(
                    db,
                    "lineage",
                    "experiment:" + experiment["id"],
                    {
                        "campaign_id": campaign,
                        "experiment_id": experiment["id"],
                        "parent_experiment_id": experiment.get("parent_experiment_id"),
                        "informed_by_result_ids": experiment.get("informed_by_result_ids", []),
                        "relation": experiment["relation"],
                        "trial_id": experiment["trial_id"],
                    },
                )
        return run_id

    def check_ordinary_dataset(self, manifest: dict[str, Any]) -> None:
        """A relabeled dataset cannot confer access to registered protected bytes."""
        if manifest.get("partition") == "confirmation":
            raise SourceBindingError(
                "DATA_LIMITED: protected confirmation requires the release service"
            )
        source = manifest.get("source_path")
        sha = manifest.get("source_sha256")
        for other in self.list("dataset"):
            if other.get("partition") != "confirmation":
                continue
            same_hash = sha is not None and sha == other.get("source_sha256")
            other_source = other.get("source_path")
            same_path = (
                source is not None
                and other_source is not None
                and Path(source).expanduser().resolve() == Path(other_source).expanduser().resolve()
            )
            if same_hash or same_path:
                raise SourceBindingError(
                    "DATA_LIMITED: source aliases registered protected confirmation bytes"
                )

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._reader() as db:
            value = _row(db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone())
            if value is None:
                raise RegistryError("Unknown run: " + run_id)
            value["status"] = value["state"]
            event = db.execute(
                "SELECT event_id FROM events WHERE subject=? AND event_type IN ('RUN_COMPLETED','RUN_FAILED','RUN_CANCELLED') ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            value["event_id"] = event[0] if event else None
            return value

    def claim(
        self,
        worker_id: str,
        pid: int,
        *,
        lease_seconds: float = 30,
        max_concurrency: int = 2,
        environment_hash: str | None = None,
        evaluator_hash: str | None = None,
    ) -> dict[str, Any] | None:
        if not worker_id or lease_seconds <= 0 or max_concurrency < 1:
            raise RegistryError("Invalid worker claim")
        now, identity = time.time(), process_identity(pid)
        if identity is None:
            raise RegistryError("Worker process identity cannot be established")
        with self.transaction() as db:
            running = db.execute(
                "SELECT count(*) FROM runs WHERE state IN ('RUNNING','CANCEL_REQUESTED','LOST_UNRESOLVED')"
            ).fetchone()[0]
            if running >= max_concurrency:
                return None
            query = "SELECT r.* FROM runs r JOIN outbox o ON o.run_id=r.run_id WHERE r.state='QUEUED' AND o.state='PENDING'"
            args: list[Any] = []
            for name, value in (
                ("environment_hash", environment_hash),
                ("evaluator_hash", evaluator_hash),
            ):
                if value is not None:
                    query += " AND r." + name + "=?"
                    args.append(value)
            row = None
            for candidate in db.execute(
                query + " ORDER BY r.priority DESC,r.created_at,r.run_id", args
            ).fetchall():
                contract = json.loads(
                    db.execute(
                        "SELECT payload FROM records WHERE kind='campaign' AND id=?",
                        (candidate["campaign_id"],),
                    ).fetchone()[0]
                )
                active = db.execute(
                    "SELECT count(*) FROM runs WHERE campaign_id=? AND state IN ('RUNNING','CANCEL_REQUESTED','LOST_UNRESOLVED')",
                    (candidate["campaign_id"],),
                ).fetchone()[0]
                if active < contract.get("numerical_concurrency", 1):
                    row = candidate
                    break
            if row is None:
                return None
            if row["schema_version"] != SCHEMA_VERSION or row["graph_version"] != GRAPH_VERSION:
                raise RegistryError("Incompatible resume contract")
            attempt, fence = "attempt-" + uuid.uuid4().hex, row["fence"] + 1
            db.execute(
                "UPDATE runs SET state='RUNNING',fence=?,attempt_id=?,updated_at=? WHERE run_id=? AND state='QUEUED'",
                (fence, attempt, now, row["run_id"]),
            )
            db.execute(
                "INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,'RUNNING',?,NULL)",
                (
                    attempt,
                    row["run_id"],
                    fence,
                    worker_id,
                    socket.gethostname(),
                    pid,
                    identity,
                    now + lease_seconds,
                    now,
                    now,
                ),
            )
            db.execute("UPDATE outbox SET state='CLAIMED' WHERE run_id=?", (row["run_id"],))
            self._event(
                db,
                "RUN_CLAIMED",
                row["run_id"],
                {"attempt_id": attempt, "fence": fence, "worker_id": worker_id},
            )
            result = _row(
                db.execute("SELECT * FROM runs WHERE run_id=?", (row["run_id"],)).fetchone()
            )
            assert result is not None
            return result

    def _fenced(
        self, db: sqlite3.Connection, run_id: str, attempt_id: str, fence: int
    ) -> sqlite3.Row:
        row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None or row["attempt_id"] != attempt_id or row["fence"] != fence:
            raise StaleFence("Stale or unknown worker attempt")
        return row

    def heartbeat(
        self, run_id: str, attempt_id: str, fence: int, lease_seconds: float = 30
    ) -> bool:
        with self.transaction() as db:
            row = self._fenced(db, run_id, attempt_id, fence)
            if row["state"] not in {"RUNNING", "CANCEL_REQUESTED", "LOST_UNRESOLVED"}:
                return False
            now = time.time()
            db.execute(
                "UPDATE attempts SET heartbeat_at=?,lease_until=? WHERE attempt_id=?",
                (now, now + lease_seconds, attempt_id),
            )
            return not bool(row["cancel_requested"])

    def prepare_job(self, run_id: str, attempt_id: str, fence: int, scratch: Path | str) -> None:
        """Persist launch intent BEFORE Popen; unknown PID is not proof of no child."""
        with self.transaction() as db:
            self._fenced(db, run_id, attempt_id, fence)
            db.execute(
                "INSERT INTO jobs VALUES(?,NULL,NULL,?,?)",
                (attempt_id, str(Path(scratch).resolve()), time.time()),
            )

    def start_job(
        self, run_id: str, attempt_id: str, fence: int, child_pid: int, scratch: Path | str
    ) -> None:
        with self.transaction() as db:
            self._fenced(db, run_id, attempt_id, fence)
            identity = process_identity(child_pid)
            if identity is None:
                raise RegistryError("Cannot establish evaluator process identity")
            old = db.execute("SELECT * FROM jobs WHERE attempt_id=?", (attempt_id,)).fetchone()
            if old is None:
                db.execute(
                    "INSERT INTO jobs VALUES(?,?,?,?,?)",
                    (attempt_id, child_pid, identity, str(Path(scratch).resolve()), time.time()),
                )
            elif old["child_pid"] is None:
                db.execute(
                    "UPDATE jobs SET child_pid=?,child_identity=? WHERE attempt_id=?",
                    (child_pid, identity, attempt_id),
                )
            elif old["child_pid"] != child_pid or old["child_identity"] != identity:
                raise ConflictError("Attempt already has a different evaluator process")

    def complete(
        self,
        run_id: str,
        attempt_id: str,
        fence: int,
        result_ref: Any,
        *,
        actual_cpu_seconds: float | None = None,
    ) -> str:
        result_ref = plain(result_ref)
        self.artifacts.verify(result_ref)
        self.artifacts.verify_tree(self.artifacts.read_json(result_ref))
        with self.transaction() as db:
            row = self._fenced(db, run_id, attempt_id, fence)
            encoded = canonical_bytes(result_ref).decode()
            if row["result_ref"] is not None:
                if row["result_ref"] != encoded:
                    raise ConflictError("A different result already exists for this run")
                event = db.execute(
                    "SELECT event_id FROM events WHERE subject=? AND event_type='RUN_COMPLETED'",
                    (run_id,),
                ).fetchone()
                return event[0]
            if row["state"] not in {"RUNNING", "LOST_UNRESOLVED"} or row["cancel_requested"]:
                raise RegistryError("Cannot complete a cancelled or terminal run")
            now = time.time()
            db.execute(
                "UPDATE runs SET state='COMPLETED',result_ref=?,updated_at=? WHERE run_id=?",
                (encoded, now, run_id),
            )
            db.execute(
                "UPDATE attempts SET state='COMPLETED',finished_at=? WHERE attempt_id=?",
                (now, attempt_id),
            )
            db.execute("UPDATE outbox SET state='DONE' WHERE run_id=?", (run_id,))
            db.execute(
                "UPDATE budget_reservations SET state='SPENT',actual_cpu_seconds=? WHERE run_id=?",
                (actual_cpu_seconds, run_id),
            )
            self._record(db, "artifact", result_ref["sha256"], result_ref)
            return self._event(
                db,
                "RUN_COMPLETED",
                run_id,
                {"attempt_id": attempt_id, "fence": fence, "result_ref": result_ref},
            )

    def fail(
        self,
        run_id: str,
        attempt_id: str,
        fence: int,
        reason: Any,
        *,
        retryable: bool = False,
        cancelled: bool = False,
    ) -> str:
        with self.transaction() as db:
            row = self._fenced(db, run_id, attempt_id, fence)
            if row["state"] in TERMINAL:
                return row["state"]
            now = time.time()
            # Economic results are accepted data, never retryable failures.
            if (
                retryable
                and isinstance(reason, dict)
                and reason.get("kind") not in {"TRANSIENT_IO", "WORKER_DIED_BEFORE_RESULT"}
            ):
                raise RegistryError("Only classified operational failures may retry")
            requeue = retryable and fence < row["max_attempts"] and not row["cancel_requested"]
            if requeue:
                resources = json.loads(row["resources"])
                limits = json.loads(
                    db.execute(
                        "SELECT limits FROM campaign_runtime WHERE id=?", (row["campaign_id"],)
                    ).fetchone()[0]
                )
                used = list(
                    db.execute(
                        "SELECT COALESCE(SUM(cpu_seconds),0),COALESCE(SUM(storage_bytes),0) FROM budget_reservations WHERE campaign_id=?",
                        (row["campaign_id"],),
                    ).fetchone()
                )
                services = db.execute(
                    "SELECT COALESCE(SUM(cpu_seconds),0),COALESCE(SUM(storage_bytes),0) FROM service_jobs WHERE campaign_id=?",
                    (row["campaign_id"],),
                ).fetchone()
                used = [a + b for a, b in zip(used, services)]
                retry_cpu = max(1, math.ceil(resources["cpu_seconds"]))
                requeue = (
                    used[0] + retry_cpu <= limits["cpu_seconds"]
                    and used[1] + resources["storage_bytes"] <= limits["storage_bytes"]
                )
                if requeue:
                    db.execute(
                        "UPDATE budget_reservations SET cpu_seconds=cpu_seconds+?,storage_bytes=storage_bytes+? WHERE run_id=?",
                        (retry_cpu, resources["storage_bytes"], run_id),
                    )
            state = (
                "QUEUED"
                if requeue
                else "CANCELLED"
                if cancelled or row["cancel_requested"]
                else "FAILED"
            )
            db.execute(
                "UPDATE runs SET state=?,failure=?,updated_at=? WHERE run_id=?",
                (state, canonical_bytes(reason).decode(), now, run_id),
            )
            db.execute(
                "UPDATE attempts SET state=?,finished_at=? WHERE attempt_id=?",
                ("FAILED" if requeue else state, now, attempt_id),
            )
            db.execute(
                "UPDATE outbox SET state=? WHERE run_id=?",
                ("PENDING" if requeue else "DONE", run_id),
            )
            if not requeue:
                db.execute("UPDATE budget_reservations SET state='SPENT' WHERE run_id=?", (run_id,))
            self._event(
                db,
                "RUN_" + state,
                run_id,
                {"attempt_id": attempt_id, "fence": fence, "reason": reason},
            )
            return state

    def ingest(self, run_id: str) -> dict[str, Any]:
        row = self.get_run(run_id)
        if row["state"] not in {"COMPLETED", "INGESTED"} or not row["result_ref"]:
            raise RegistryError("Run has no accepted result")
        self.artifacts.verify(row["result_ref"])
        result = self.artifacts.read_json(row["result_ref"])
        self.artifacts.verify_tree(result)
        with self.transaction() as db:
            now = time.time()
            existing = db.execute(
                "SELECT result_hash FROM ingestion WHERE run_id=?", (run_id,)
            ).fetchone()
            if existing and existing[0] != row["result_ref"]["sha256"]:
                raise ConflictError("Conflicting ingestion")
            if not existing:
                db.execute(
                    "INSERT INTO ingestion VALUES(?,?,?)",
                    (run_id, row["result_ref"]["sha256"], now),
                )
                db.execute(
                    "UPDATE runs SET state='INGESTED',updated_at=? WHERE run_id=?", (now, run_id)
                )
                self._event(db, "RUN_INGESTED", run_id, {"result_ref": row["result_ref"]})
        return result

    def terminal_event(self, run_id: str) -> dict[str, Any] | None:
        with self._reader() as db:
            return _row(
                db.execute(
                    "SELECT * FROM events WHERE subject=? AND event_type IN ('RUN_COMPLETED','RUN_FAILED','RUN_CANCELLED') ORDER BY created_at DESC LIMIT 1",
                    (run_id,),
                ).fetchone()
            )

    def validate_terminal_event(self, run_id: str, event_id: str) -> dict[str, Any]:
        with self._reader() as db:
            event = _row(
                db.execute(
                    "SELECT * FROM events WHERE event_id=? AND subject=?", (event_id, run_id)
                ).fetchone()
            )
        if event is None or event["event_type"] not in {
            "RUN_COMPLETED",
            "RUN_FAILED",
            "RUN_CANCELLED",
        }:
            raise RegistryError("Forged/unrelated resume event")
        row = self.get_run(run_id)
        if event["payload"]["fence"] != row["fence"] or row["state"] not in TERMINAL:
            raise StaleFence("Obsolete terminal event")
        return event

    def register_wait(self, run_id: str, thread_id: str) -> dict[str, Any] | None:
        """Record first, then read completion: completion-before-wait cannot be lost."""
        self.get_run(run_id)
        self.add_event(
            "WAIT_REGISTERED",
            run_id,
            {"thread_id": thread_id},
            "wait-" + digest([run_id, thread_id]),
        )
        return self.terminal_event(run_id)

    def reserve_service_budget(
        self,
        campaign_id: str,
        reservation_id: str,
        cpu_seconds: float,
        storage_bytes: int = 10_000_000,
        service: str = "confirmation",
    ) -> dict[str, Any]:
        """Protected service jobs are registered/reserved but never ordinary queue work."""
        if service not in {"confirmation", "replication", "benchmark"}:
            raise RegistryError("Unapproved numerical service")
        if (
            not reservation_id
            or not math.isfinite(cpu_seconds)
            or cpu_seconds <= 0
            or storage_bytes <= 0
        ):
            raise RegistryError("Invalid service reservation")
        payload = {
            "campaign_id": campaign_id,
            "reservation_id": reservation_id,
            "cpu_seconds": cpu_seconds,
            "storage_bytes": storage_bytes,
            "service": service,
        }
        hashed = digest(payload)
        with self.transaction() as db:
            old = db.execute(
                "SELECT * FROM service_jobs WHERE reservation_id=?", (reservation_id,)
            ).fetchone()
            if old:
                if old["payload_hash"] != hashed:
                    raise ConflictError("Service reservation reused with changed job/budget")
                return dict(old)
            row = db.execute("SELECT * FROM campaign_runtime WHERE id=?", (campaign_id,)).fetchone()
            contract = db.execute(
                "SELECT payload FROM records WHERE kind='campaign' AND id=?", (campaign_id,)
            ).fetchone()
            if (
                row is None
                or row["cancelled"]
                or not contract
                or not json.loads(contract[0]).get("approved")
            ):
                raise RegistryError("Campaign absent, unapproved or cancelled")
            limits = json.loads(row["limits"])
            a = db.execute(
                "SELECT COALESCE(SUM(runs),0),COALESCE(SUM(cpu_seconds),0),COALESCE(SUM(storage_bytes),0) FROM budget_reservations WHERE campaign_id=?",
                (campaign_id,),
            ).fetchone()
            b = db.execute(
                "SELECT count(*),COALESCE(SUM(cpu_seconds),0),COALESCE(SUM(storage_bytes),0) FROM service_jobs WHERE campaign_id=?",
                (campaign_id,),
            ).fetchone()
            for i, (key, amount) in enumerate(
                (("max_runs", 1), ("cpu_seconds", cpu_seconds), ("storage_bytes", storage_bytes))
            ):
                if a[i] + b[i] + amount > limits[key]:
                    raise BudgetExceeded("Protected service budget exhausted: " + key)
            db.execute(
                "INSERT INTO service_jobs VALUES(?,?,?,?,?,?,'RESERVED',NULL,?)",
                (
                    reservation_id,
                    campaign_id,
                    service,
                    cpu_seconds,
                    storage_bytes,
                    hashed,
                    time.time(),
                ),
            )
            self._event(db, "SERVICE_REGISTERED", reservation_id, payload)
            return dict(
                db.execute(
                    "SELECT * FROM service_jobs WHERE reservation_id=?", (reservation_id,)
                ).fetchone()
            )

    def finish_service(
        self, reservation_id: str, success: bool = True, result_ref: Any | None = None
    ) -> dict[str, Any]:
        if result_ref is not None:
            self.artifacts.verify(result_ref)
        encoded = canonical_bytes(result_ref).decode() if result_ref is not None else None
        target = "COMPLETED" if success else "FAILED"
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM service_jobs WHERE reservation_id=?", (reservation_id,)
            ).fetchone()
            if row is None:
                raise RegistryError("Unregistered protected numerical computation")
            if row["state"] != "RESERVED":
                if row["state"] != target or row["result_ref"] != encoded:
                    raise ConflictError("Conflicting protected service completion")
                return dict(row)
            db.execute(
                "UPDATE service_jobs SET state=?,result_ref=? WHERE reservation_id=?",
                (target, encoded, reservation_id),
            )
            self._event(db, "SERVICE_" + target, reservation_id, {"result_ref": plain(result_ref)})
            return dict(
                db.execute(
                    "SELECT * FROM service_jobs WHERE reservation_id=?", (reservation_id,)
                ).fetchone()
            )

    def cancel_campaign(self, id: str) -> dict[str, int]:
        with self.transaction() as db:
            if db.execute("SELECT id FROM campaign_runtime WHERE id=?", (id,)).fetchone() is None:
                raise RegistryError("Unknown campaign")
            db.execute("UPDATE campaign_runtime SET cancelled=1 WHERE id=?", (id,))
            rows = db.execute(
                "SELECT * FROM runs WHERE campaign_id=? AND state NOT IN ('COMPLETED','INGESTED','FAILED','CANCELLED','INVALID_RESULT')",
                (id,),
            ).fetchall()
            queued, running = 0, 0
            for row in rows:
                state = "CANCELLED" if row["state"] == "QUEUED" else "CANCEL_REQUESTED"
                db.execute(
                    "UPDATE runs SET state=?,cancel_requested=1,updated_at=? WHERE run_id=?",
                    (state, time.time(), row["run_id"]),
                )
                if state == "CANCELLED":
                    queued += 1
                    db.execute("UPDATE outbox SET state='DONE' WHERE run_id=?", (row["run_id"],))
                    self._event(
                        db,
                        "RUN_CANCELLED",
                        row["run_id"],
                        {
                            "attempt_id": row["attempt_id"],
                            "fence": row["fence"],
                            "reason": "Campaign cancelled before dispatch",
                        },
                    )
                else:
                    running += 1
            self._event(
                db,
                "CAMPAIGN_CANCELLED",
                id,
                {"queued_cancelled": queued, "running_requested": running},
            )
            return {"queued_cancelled": queued, "running_requested": running}

    def reconcile(self) -> builtins.list[dict[str, Any]]:
        with self._reader() as db:
            rows = [
                dict(r)
                for r in db.execute("""SELECT r.*,a.host,a.pid,a.process_identity,a.lease_until,
              j.child_pid,j.child_identity,j.scratch FROM runs r JOIN attempts a ON a.attempt_id=r.attempt_id
              LEFT JOIN jobs j ON j.attempt_id=a.attempt_id
              WHERE r.state IN ('RUNNING','CANCEL_REQUESTED','LOST_UNRESOLVED')""")
            ]
        results = []
        for row in rows:
            if row["host"] != socket.gethostname():
                alive, child = None, None
            else:
                alive = process_alive(row["pid"], row["process_identity"])
                child = (
                    process_alive(row["child_pid"], row["child_identity"])
                    if row["child_pid"]
                    else None
                    if row["scratch"]
                    else False
                )
            if alive is True and row["lease_until"] >= time.time():
                results.append(
                    {
                        "run_id": row["run_id"],
                        "state": row["state"],
                        "reason": "Owner lease and process verified",
                    }
                )
                continue
            marker = Path(row["scratch"]) / "published.json" if row["scratch"] else None
            if (
                alive is False
                and child is False
                and marker is not None
                and marker.is_file()
                and not row["cancel_requested"]
            ):
                try:
                    data = json.loads(marker.read_text())
                    if (data["run_id"], data["attempt_id"], data["fence"]) != (
                        row["run_id"],
                        row["attempt_id"],
                        row["fence"],
                    ):
                        raise ConflictError("Publication marker belongs to another attempt")
                    self.complete(
                        row["run_id"], row["attempt_id"], row["fence"], data["result_ref"]
                    )
                    results.append(
                        {
                            "run_id": row["run_id"],
                            "state": "COMPLETED",
                            "reason": "Recovered verified published artifact",
                        }
                    )
                    continue
                except (ValueError, OSError, KeyError) as error:
                    state = self.fail(
                        row["run_id"],
                        row["attempt_id"],
                        row["fence"],
                        {"kind": "ARTIFACT_INTEGRITY", "message": str(error)},
                    )
                    results.append({"run_id": row["run_id"], "state": state})
                    continue
            if alive is False and child is False:
                state = self.fail(
                    row["run_id"],
                    row["attempt_id"],
                    row["fence"],
                    {"kind": "WORKER_DIED_BEFORE_RESULT"},
                    retryable=True,
                )
                results.append({"run_id": row["run_id"], "state": state})
            else:
                with self.transaction() as db:
                    self._fenced(db, row["run_id"], row["attempt_id"], row["fence"])
                    db.execute(
                        "UPDATE runs SET state='LOST_UNRESOLVED',updated_at=? WHERE run_id=?",
                        (time.time(), row["run_id"]),
                    )
                    self._event(
                        db,
                        "WORKER_UNRESOLVED",
                        row["run_id"],
                        {"owner_alive": alive, "child_alive": child},
                    )
                results.append({"run_id": row["run_id"], "state": "LOST_UNRESOLVED"})
        return results

    def status(self, campaign_id: str | None = None) -> dict[str, Any]:
        with self._reader() as db:
            where, args = (" WHERE campaign_id=?", [campaign_id]) if campaign_id else ("", [])
            counts = {
                r[0]: r[1]
                for r in db.execute(
                    "SELECT state,count(*) FROM runs" + where + " GROUP BY state", args
                )
            }
            budget = dict(
                db.execute(
                    "SELECT COALESCE(SUM(runs),0) runs,COALESCE(SUM(cpu_seconds),0) cpu_seconds,COALESCE(SUM(storage_bytes),0) storage_bytes,COALESCE(SUM(actual_cpu_seconds),0) measured_cpu_seconds FROM budget_reservations"
                    + where,
                    args,
                ).fetchone()
            )
            services = db.execute(
                "SELECT count(*),COALESCE(SUM(cpu_seconds),0),COALESCE(SUM(storage_bytes),0) FROM service_jobs"
                + where,
                args,
            ).fetchone()
            for key, value in zip(("runs", "cpu_seconds", "storage_bytes"), services):
                budget[key] += value
            return {
                "runs": counts,
                "budget_committed_upper_bounds": budget,
                "schema_version": SCHEMA_VERSION,
                "graph_version": GRAPH_VERSION,
                "pending_outbox": db.execute(
                    "SELECT count(*) FROM outbox WHERE state='PENDING'"
                ).fetchone()[0],
            }

    def events(self, subject: str | None = None) -> builtins.list[dict[str, Any]]:
        with self._reader() as db:
            query, args = (
                ("SELECT * FROM events WHERE subject=?", [subject])
                if subject
                else ("SELECT * FROM events", [])
            )
            return [_row(r) for r in db.execute(query + " ORDER BY created_at,event_id", args)]

    def runs(self, campaign_id: str | None = None) -> builtins.list[dict[str, Any]]:
        with self._reader() as db:
            query, args = (
                ("SELECT * FROM runs WHERE campaign_id=?", [campaign_id])
                if campaign_id
                else ("SELECT * FROM runs", [])
            )
            return [_row(r) for r in db.execute(query + " ORDER BY created_at,run_id", args)]
