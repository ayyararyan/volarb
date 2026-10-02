from __future__ import annotations

import json
import os
import sqlite3

import pytest

from butterfly_lab.backup import backup, restore, verify_backup
from butterfly_lab.registry import Registry, RegistryError
from test_registry import setup_registry, register


def test_backup_restore_registry_checkpoint_and_artifact_hashes(tmp_path):
    reg, exp, data = setup_registry(tmp_path)
    run = register(reg, exp, data)
    job = reg.claim("worker", os.getpid())
    ref = reg.artifacts.put_json({"outcome": "INCONCLUSIVE"})
    reg.complete(run, job["attempt_id"], job["fence"], ref)
    reg.ingest(run)
    checkpoint = sqlite3.connect(reg.root / "checkpoints.sqlite3")
    checkpoint.execute("PRAGMA journal_mode=WAL")
    checkpoint.execute("CREATE TABLE checkpoints(id PRIMARY KEY,value)")
    checkpoint.execute("INSERT INTO checkpoints VALUES('graph-thread','await')")
    checkpoint.commit()
    receipt = backup(reg.root, tmp_path / "snapshot")
    checkpoint.close()
    result = restore(
        tmp_path / "snapshot", tmp_path / "restored", manifest_sha256=receipt["manifest_sha256"]
    )
    assert result["verified_files"] >= 3
    copied = Registry(tmp_path / "restored")
    assert copied.ingest(run)["outcome"] == "INCONCLUSIVE"
    copied.artifacts.verify(ref)
    with sqlite3.connect(copied.root / "checkpoints.sqlite3") as db:
        assert db.execute("SELECT value FROM checkpoints").fetchone()[0] == "await"


def test_backup_corruption_and_overwrite_rejected(tmp_path):
    reg, _, _ = setup_registry(tmp_path)
    backup(reg.root, tmp_path / "snapshot")
    with pytest.raises(RegistryError):
        restore(tmp_path / "snapshot", reg.root)
    with (tmp_path / "snapshot/registry.sqlite3").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(RegistryError, match="hash/size"):
        verify_backup(tmp_path / "snapshot")


def test_restore_rejects_path_traversal(tmp_path):
    reg, _, _ = setup_registry(tmp_path)
    backup(reg.root, tmp_path / "snapshot")
    path = tmp_path / "snapshot/backup-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"]["../escape"] = {"sha256": "0" * 64, "size_bytes": 0}
    path.write_text(json.dumps(manifest))
    with pytest.raises(RegistryError, match="Unsafe backup path"):
        verify_backup(tmp_path / "snapshot")
