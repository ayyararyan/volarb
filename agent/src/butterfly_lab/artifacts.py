"""Atomic, immutable, content-addressed research artifacts (never conversational state)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class ArtifactError(ValueError):
    """An artifact is absent, altered or points outside its permitted store."""


def plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Naive timestamp is not evidence")
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class ArtifactStore:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, ref: Any) -> Path:
        obj = plain(ref)
        sha = obj.get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ArtifactError("Invalid SHA256")
        if obj.get("uri") != "sha256:" + sha:
            raise ArtifactError("Artifact URI/hash mismatch; external URIs are not permitted")
        path = self.root / sha[:2] / sha
        if path.is_symlink() or path.parent.is_symlink():
            raise ArtifactError("Artifact symlink forbidden")
        return path

    def put_bytes(self, value: bytes, media_type: str = "application/octet-stream") -> Any:
        from .schemas import ArtifactRef

        if not isinstance(value, bytes):
            raise TypeError("put_bytes requires bytes")
        sha = hashlib.sha256(value).hexdigest()
        ref = ArtifactRef(
            uri="sha256:" + sha, sha256=sha, media_type=media_type, schema_version="1"
        )
        dest = self.path(ref)
        dest.parent.mkdir(mode=0o700, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".publish-", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, 0o444)
            try:
                os.link(name, dest)  # atomic create-if-absent, never replace evidence
                fsync_directory(dest.parent)
            except FileExistsError:
                if dest.read_bytes() != value:
                    raise ArtifactError("Conflicting content at immutable artifact address")
        finally:
            Path(name).unlink(missing_ok=True)
        self.verify(ref)
        return ref

    def put_json(self, value: Any) -> Any:
        return self.put_bytes(canonical_bytes(value), "application/json")

    def put_file(self, path: Path | str, media_type: str = "application/octet-stream") -> Any:
        return self.put_bytes(Path(path).read_bytes(), media_type)

    def verify(self, ref: Any) -> bool:
        path = self.path(ref)
        if not path.is_file():
            raise ArtifactError("Missing artifact: " + plain(ref)["sha256"])
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        if h.hexdigest() != plain(ref)["sha256"]:
            raise ArtifactError("Artifact hash verification failed")
        return True

    def read_json(self, ref: Any) -> Any:
        self.verify(ref)
        return json.loads(
            self.path(ref).read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ArtifactError("Non-finite JSON: " + value)
            ),
        )

    def verify_tree(self, value: Any) -> int:
        """Verify every nested content reference, not just the outer result JSON."""
        value = plain(value)
        if isinstance(value, dict):
            if "sha256" in value and "uri" in value:
                self.verify(value)
                return 1
            return sum(self.verify_tree(v) for v in value.values())
        if isinstance(value, list):
            return sum(self.verify_tree(v) for v in value)
        return 0
