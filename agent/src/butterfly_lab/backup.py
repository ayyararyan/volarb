"""Consistent SQLite snapshots plus verified immutable artifacts; no raw data copy."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .artifacts import canonical_bytes, fsync_directory
from .registry import Registry, RegistryError


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _sqlite_copy(source: Path, target: Path) -> None:
    # SQLite backup API includes committed WAL contents, unlike copying db bytes.
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dest = sqlite3.connect(target)
    try:
        src.backup(dest)
        if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RegistryError("Database backup failed integrity check")
        dest.commit()
    finally:
        dest.close()
        src.close()


def backup(root: Path | str, destination: Path | str) -> dict[str, Any]:
    registry = Registry(root)
    destination = Path(destination).expanduser().resolve()
    if destination.exists() or destination == registry.root or registry.root in destination.parents:
        raise RegistryError("Backup destination must be new and outside active runtime")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / (".backup-" + uuid.uuid4().hex)
    staging.mkdir(mode=0o700)
    try:
        # Freeze registry mutations, but do NOT begin a write transaction while
        # SQLite's backup API reads the same database: that can self-deadlock.
        import fcntl

        with registry.lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            databases = sorted(
                {
                    p
                    for suffix in ("*.sqlite3", "*.sqlite", "*.db")
                    for p in registry.root.glob(suffix)
                    if p.is_file()
                }
            )
            for source in databases:
                _sqlite_copy(source, staging / source.name)
            # These are generated reservation state, NOT user configuration or
            # credentials. Retain them so restore cannot erase already spent
            # local call/USD allowances. Respect each writer's actual lock.
            for name in ("codex-usage.json", "provider-budget.json"):
                source = registry.root / name
                if not source.exists():
                    continue
                if source.is_symlink():
                    raise RegistryError("Provider budget backup refuses symlinks")
                lock_path = (
                    source.with_suffix(source.suffix + ".lock")
                    if name == "codex-usage.json"
                    else source
                )
                with lock_path.open("a+") as provider_lock:
                    fcntl.flock(provider_lock, fcntl.LOCK_EX)
                    # Validate JSON before copying; never copy .env/auth/config.
                    json.loads(source.read_text())
                    shutil.copyfile(source, staging / name)
                    os.chmod(staging / name, 0o600)
            source_artifacts = registry.artifacts.root
            for source in source_artifacts.rglob("*"):
                if source.is_symlink():
                    raise RegistryError("Artifact backup refuses symlinks")
                if source.is_file() and not source.name.startswith("."):
                    if _hash(source) != source.name:
                        raise RegistryError("Corrupted content-addressed artifact during backup")
                    relative = source.relative_to(registry.root)
                    target = staging / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            # Published markers preserve the crash-after-publication recovery path.
            for source in (registry.root / "jobs").glob("**/published.json"):
                target = staging / source.relative_to(registry.root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            fcntl.flock(lock, fcntl.LOCK_UN)
        files = {
            str(path.relative_to(staging)): {
                "sha256": _hash(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }
        manifest = {
            "format": "butterfly-lab-backup/1",
            "created_at_unix": time.time(),
            "schema_version": "1",
            "files": files,
            "raw_data_included": False,
            "recovery": "Reconcile external attempts before dispatch; checkpoint stores are individually consistent snapshots.",
        }
        (staging / "backup-manifest.json").write_bytes(canonical_bytes(manifest))
        for path in staging.rglob("*"):
            if path.is_file():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
        fsync_directory(staging)
        os.rename(staging, destination)
        fsync_directory(destination.parent)
        return {
            "destination": str(destination),
            "files": len(files),
            "manifest_sha256": _hash(destination / "backup-manifest.json"),
        }
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_backup(source: Path | str, *, manifest_sha256: str | None = None) -> dict[str, Any]:
    source = Path(source).expanduser().resolve()
    manifest_path = source / "backup-manifest.json"
    if manifest_sha256 is not None and _hash(manifest_path) != manifest_sha256:
        raise RegistryError("Backup manifest does not match trusted receipt")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != "butterfly-lab-backup/1" or manifest.get("schema_version") != "1":
        raise RegistryError("Incompatible backup format")
    for name, evidence in manifest["files"].items():
        relative = Path(name)
        path = source / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or path.is_symlink()
            or source not in path.resolve().parents
        ):
            raise RegistryError("Unsafe backup path")
        if (
            not path.is_file()
            or path.stat().st_size != evidence["size_bytes"]
            or _hash(path) != evidence["sha256"]
        ):
            raise RegistryError("Backup hash/size mismatch: " + name)
    if "registry.sqlite3" not in manifest["files"]:
        raise RegistryError("Backup lacks registry")
    return manifest


def restore(
    source: Path | str, destination: Path | str, *, manifest_sha256: str | None = None
) -> dict[str, Any]:
    source = Path(source).expanduser().resolve()
    manifest = verify_backup(source, manifest_sha256=manifest_sha256)
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise RegistryError("Restore refuses an existing destination; preserve unrelated runtime")
    from .config import runtime_root

    # Validate policy using a new destination. It creates only this fresh root.
    runtime_root(destination)
    try:
        for name in manifest["files"]:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(source / name, target)
        registry = Registry(destination)
        with registry.transaction() as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RegistryError("Restored registry integrity failure")
            for row in db.execute(
                "SELECT a.run_id,j.attempt_id FROM jobs j JOIN attempts a ON a.attempt_id=j.attempt_id"
            ).fetchall():
                db.execute(
                    "UPDATE jobs SET scratch=? WHERE attempt_id=?",
                    (
                        str(destination / "jobs" / row["run_id"] / row["attempt_id"]),
                        row["attempt_id"],
                    ),
                )
            # Freeze external owners. No restored job is automatically launched.
            db.execute(
                "UPDATE runs SET state='LOST_UNRESOLVED' WHERE state IN ('RUNNING','CANCEL_REQUESTED')"
            )
            registry._event(
                db,
                "BACKUP_RESTORED",
                "runtime",
                {
                    "source_manifest_sha256": _hash(source / "backup-manifest.json"),
                    "files_verified": len(manifest["files"]),
                },
            )
        for path in registry.artifacts.root.rglob("*"):
            if path.is_file() and _hash(path) != path.name:
                raise RegistryError("Restored artifact verification failed")
        return {
            "destination": str(destination),
            "verified_files": len(manifest["files"]),
            "requires_reconciliation": True,
            "raw_data_must_be_available_separately": True,
        }
    except BaseException:
        # Destination was created by this call only; keep any evidence recoverable.
        failed = destination.with_name(destination.name + ".failed-restore-" + uuid.uuid4().hex[:8])
        if destination.exists():
            os.rename(destination, failed)
        raise
