"""Durable account-scoped admission on one POSIX host/local filesystem.

SQLite transactions atomically reserve identities and the unresolved-account slot.
Nonblocking OS locks fence dispatch and reconciliation across processes. No SQLite
transaction is held across broker I/O. Lock expiry is never used as broker evidence.
"""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from .execution_action_envelope import ExecutionAction
from .execution_scope import ExecutionScope


class LedgerAdmissionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class ScopeLease:
    scope: ExecutionScope
    ledger: Any
    owner_pid: int
    active: bool = True


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class SQLiteExecutionLedger:
    """Persistent actions/events, one unresolved mutation per broker account.

    All dispatchers for an account must share this database and lock directory.
    This is local-host infrastructure; network filesystems/distributed writers and
    deleting/replacing a live DB/lock directory are outside this backend's contract.
    """

    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        if str(path) == ":memory:" or str(path).startswith("file:"):
            raise ValueError("durable ledger requires a filesystem database")
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int) or busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be a positive integer")
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._timeout_ms = busy_timeout_ms
        self._locks = self.path.with_name(self.path.name + ".locks")
        self._locks.mkdir(mode=0o700, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with self._connection() as db:
            if db.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
                raise RuntimeError("ledger requires rollback journaling")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(f"unsupported ledger schema version {version}")
            if version == 0:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                    raise RuntimeError("refusing to initialize an existing unversioned database")
                db.execute("""CREATE TABLE actions (
                    action_id TEXT PRIMARY KEY,
                    correlation_id TEXT NOT NULL UNIQUE,
                    scope_key TEXT NOT NULL,
                    action_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    dispatched_at_ms REAL,
                    outcome_json TEXT,
                    reconciliation_json TEXT
                )""")
                db.execute("""CREATE TABLE scopes (
                    scope_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    pending_action_id TEXT UNIQUE REFERENCES actions(action_id)
                )""")
                db.execute("""CREATE TABLE events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_key TEXT NOT NULL,
                    action_id TEXT NOT NULL REFERENCES actions(action_id),
                    event_json TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX events_scope ON events(scope_key,seq)")
                db.execute("""CREATE TABLE intents (
                    scope_key TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(scope_key,intent_id)
                )""")
                db.execute("PRAGMA user_version=1")
            self._verify_schema(db)
            db.commit()

    @staticmethod
    def _verify_schema(db: sqlite3.Connection) -> None:
        # Never reconstruct a missing table in an existing ledger: doing so could
        # turn durable uncertainty into an apparently empty account.
        for table, columns in {
            "actions": "action_id,correlation_id,scope_key,action_json,status,revision,dispatched_at_ms,outcome_json,reconciliation_json",
            "scopes": "scope_key,provider,account_id,pending_action_id",
            "events": "seq,scope_key,action_id,event_json",
            "intents": "scope_key,intent_id,version",
        }.items():
            db.execute(f"SELECT {columns} FROM {table} LIMIT 0")
        if [row[0] for row in db.execute("PRAGMA quick_check")] != ["ok"] or db.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("ledger integrity check failed")
        if db.execute("""SELECT 1 FROM actions a LEFT JOIN scopes s ON s.scope_key=a.scope_key
            WHERE a.status IN ('INTENDED','DISPATCHING','ACKNOWLEDGED','UNKNOWN','AMBIGUOUS')
            AND (s.pending_action_id IS NULL OR s.pending_action_id != a.action_id) LIMIT 1""").fetchone():
            raise RuntimeError("unresolved action has lost its account admission block")
        if db.execute("""SELECT 1 FROM scopes s JOIN actions a ON a.action_id=s.pending_action_id
            WHERE a.scope_key != s.scope_key OR a.status NOT IN
            ('INTENDED','DISPATCHING','ACKNOWLEDGED','UNKNOWN','AMBIGUOUS') LIMIT 1""").fetchone():
            raise RuntimeError("account admission block has an inconsistent action")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=self._timeout_ms / 1000, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=EXTRA")
            db.execute("PRAGMA foreign_keys=ON")
            yield db
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def lock_scope(self, scope: ExecutionScope) -> Iterator[ScopeLease]:
        if not isinstance(scope, ExecutionScope):
            raise TypeError("a trusted ExecutionScope is required")
        fd = os.open(self._locks / (scope.key + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        lease = ScopeLease(scope, self, os.getpid(), active=False)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise LedgerAdmissionError("SCOPE_BUSY", "account dispatch/reconciliation is in progress") from exc
            lease.active = True
            yield lease
        finally:
            lease.active = False
            os.close(fd)  # Releasing the OS lock never clears persistent uncertainty.

    def _check_lease(self, lease: ScopeLease) -> ExecutionScope:
        if not isinstance(lease, ScopeLease) or not lease.active or lease.ledger is not self or lease.owner_pid != os.getpid():
            raise LedgerAdmissionError("INVALID_LEASE", "an active local account lease is required")
        return lease.scope

    @staticmethod
    def _event(db: sqlite3.Connection, scope: ExecutionScope, action_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        row = {**event, "scopeKey": scope.key, "actionId": action_id}
        cursor = db.execute("INSERT INTO events(scope_key,action_id,event_json) VALUES(?,?,?)", (scope.key, action_id, _json(row)))
        return {**row, "ledgerSeq": cursor.lastrowid}

    def admit(self, lease: ScopeLease, action: ExecutionAction) -> dict[str, Any]:
        scope = self._check_lease(lease)
        serialized = _json(asdict(action))
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM actions WHERE action_id=?", (action.action_id,)).fetchone():
                raise LedgerAdmissionError("DUPLICATE_ACTION", "action identity has already been admitted")
            if db.execute("SELECT 1 FROM actions WHERE correlation_id=?", (action.correlation_id,)).fetchone():
                raise LedgerAdmissionError("CORRELATION_COLLISION", "correlation identity is already bound")
            db.execute("INSERT OR IGNORE INTO scopes(scope_key,provider,account_id) VALUES(?,?,?)", (scope.key, scope.provider, scope.account_id))
            if db.execute("SELECT pending_action_id FROM scopes WHERE scope_key=?", (scope.key,)).fetchone()[0] is not None:
                raise LedgerAdmissionError("SCOPE_UNRESOLVED", "reconcile the previous account mutation before admitting another")
            db.execute("INSERT INTO actions(action_id,correlation_id,scope_key,action_json,status,revision) VALUES(?,?,?,?,?,1)",
                       (action.action_id, action.correlation_id, scope.key, serialized, "INTENDED"))
            db.execute("UPDATE scopes SET pending_action_id=? WHERE scope_key=?", (action.action_id, scope.key))
            event = self._event(db, scope, action.action_id, {
                "eventType": "MUTATION_INTENDED", "status": "INTENDED",
                "correlationId": action.correlation_id, "actionClass": action.action_class,
                "originType": action.origin_type, "originId": action.origin_id,
                "intentId": action.intent_id, "intentVersion": action.intent_version,
                "sliceId": action.slice_id, "operation": action.operation.value,
                "createdAt": action.created_at, "request": action.payload,
            })
            db.commit()
            return event

    def pending(self, scope: ExecutionScope) -> dict[str, Any] | None:
        with self._connection() as db:
            row = db.execute("SELECT a.* FROM scopes s JOIN actions a ON a.action_id=s.pending_action_id WHERE s.scope_key=?", (scope.key,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            for field in ("action", "outcome", "reconciliation"):
                raw = result.pop(field + "_json")
                result[field] = json.loads(raw) if raw is not None else None
            return result

    def _transition(self, lease: ScopeLease, action_id: str, *, allowed: set[str], status: str,
                    event_type: str, details: Mapping[str, Any], clear: bool = False,
                    dispatched_at_ms: float | None = None, expected_revision: int | None = None) -> dict[str, Any]:
        scope = self._check_lease(lease)
        encoded = _json(details)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT a.* FROM actions a JOIN scopes s ON s.pending_action_id=a.action_id WHERE s.scope_key=? AND a.action_id=?", (scope.key, action_id)).fetchone()
            if row is None or row["status"] not in allowed or (expected_revision is not None and row["revision"] != expected_revision):
                raise LedgerAdmissionError("STALE_TRANSITION", "action state or reconciliation revision changed")
            column = "reconciliation_json" if event_type == "RECONCILIATION_RESULT" else "outcome_json"
            db.execute(f"UPDATE actions SET status=?,revision=revision+1,{column}=?,dispatched_at_ms=COALESCE(?,dispatched_at_ms) WHERE action_id=?",
                       (status, encoded, dispatched_at_ms, action_id))
            event = self._event(db, scope, action_id, {**details, "eventType": event_type, "status": status})
            if clear:
                db.execute("UPDATE scopes SET pending_action_id=NULL WHERE scope_key=? AND pending_action_id=?", (scope.key, action_id))
            db.commit()
            return event

    def mark_dispatch(self, lease: ScopeLease, action_id: str, now_ms: float) -> dict[str, Any]:
        return self._transition(lease, action_id, allowed={"INTENDED"}, status="DISPATCHING", event_type="DISPATCH_STARTED", details={"dispatchedAtMs": now_ms}, dispatched_at_ms=now_ms)

    def abort_before_dispatch(self, lease: ScopeLease, action_id: str, reason: str) -> dict[str, Any]:
        return self._transition(lease, action_id, allowed={"INTENDED"}, status="NOT_SENT", event_type="ADMISSION_ABORTED", details={"reason": reason}, clear=True)

    def record_outcome(self, lease: ScopeLease, action_id: str, status: str, details: Mapping[str, Any]) -> dict[str, Any]:
        if status not in {"ACKNOWLEDGED", "UNKNOWN", "KNOWN_NOT_APPLIED"}:
            raise ValueError("invalid broker outcome")
        return self._transition(lease, action_id, allowed={"DISPATCHING"}, status=status, event_type="BROKER_RESULT", details=details, clear=status == "KNOWN_NOT_APPLIED")

    def record_reconciliation(self, lease: ScopeLease, action_id: str, revision: int,
                              *, resolved: bool, details: Mapping[str, Any]) -> dict[str, Any]:
        return self._transition(lease, action_id, allowed={"DISPATCHING", "ACKNOWLEDGED", "UNKNOWN", "AMBIGUOUS"},
                                status="RECONCILED" if resolved else "AMBIGUOUS", event_type="RECONCILIATION_RESULT",
                                details=details, clear=resolved, expected_revision=revision)

    def entries(self, scope: ExecutionScope | None = None) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute("SELECT seq,event_json FROM events" + (" WHERE scope_key=?" if scope else "") + " ORDER BY seq", (scope.key,) if scope else ())
            return [{**json.loads(row["event_json"]), "ledgerSeq": row["seq"]} for row in rows]

    def publish_intent(self, scope: ExecutionScope, intent_id: str, version: int) -> None:
        if not isinstance(intent_id, str) or not intent_id.strip() or isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("intent identity and positive integer version required")
        with self.lock_scope(scope), self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT version FROM intents WHERE scope_key=? AND intent_id=?", (scope.key, intent_id)).fetchone()
            if row is not None and version <= row[0]:
                raise LedgerAdmissionError("STALE_INTENT", "intent versions must increase")
            db.execute("INSERT INTO intents VALUES(?,?,?) ON CONFLICT(scope_key,intent_id) DO UPDATE SET version=excluded.version", (scope.key, intent_id, version))
            db.commit()

    def intent_is_current(self, scope: ExecutionScope, intent_id: str, version: int) -> bool:
        with self._connection() as db:
            row = db.execute("SELECT version FROM intents WHERE scope_key=? AND intent_id=?", (scope.key, intent_id)).fetchone()
            return row is not None and row[0] == version


class LedgerIntentAuthority:
    """Read authority whose publish path shares the account dispatch fence."""

    def __init__(self, ledger: SQLiteExecutionLedger, scope: ExecutionScope) -> None:
        self.ledger, self.scope = ledger, scope

    def is_current(self, *, intent_id: str, intent_version: int, action: ExecutionAction) -> bool:
        return self.ledger.intent_is_current(self.scope, intent_id, intent_version)
