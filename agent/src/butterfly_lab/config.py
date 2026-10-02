"""Local runtime selection and reproducibility fingerprints (never machine paths in source)."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path


def runtime_root(value: str | Path | None = None) -> Path:
    from .settings import get_settings

    # Explicit worker roots avoid loading user configuration inside numerical sandboxes.
    root = Path(value if value is not None else get_settings().lab_home).expanduser().resolve()
    forbidden = ("CloudStorage", "Google Drive", "Dropbox", "OneDrive", "Mobile Documents")
    if any(term in str(root) for term in forbidden):
        raise ValueError("active runtime databases must be outside cloud-synchronised paths")
    for parent in [root, *root.parents]:
        if (parent / ".git").exists():
            raise ValueError("runtime databases and datasets must be outside a repository")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def environment_hash() -> str:
    names = (
        "langgraph",
        "langgraph-checkpoint-sqlite",
        "pydantic",
        "numpy",
        "pandas",
        "pyarrow",
        "scipy",
    )
    versions = {name: importlib.metadata.version(name) for name in names}
    versions["python"] = platform.python_version()
    versions["implementation"] = sys.implementation.name
    versions["platform"] = platform.platform()
    versions["architecture"] = platform.machine()
    # Metadata discovery can visit the same site-packages directory twice when
    # a sandbox bootstrap prepends an already-installed package root. This is
    # one environment, not two installations; retain conflicting versions.
    versions["installed_packages"] = json.dumps(
        sorted(
            {
                (d.metadata["Name"].lower(), d.version)
                for d in importlib.metadata.distributions()
                if d.metadata["Name"].lower()
                not in {"pip", "setuptools", "wheel", "butterfly-research-lab"}
            }
        )
    )
    return hashlib.sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest()


def evaluator_hash() -> str:
    base = Path(__file__).parent
    h = hashlib.sha256()
    for name in (
        "data.py",
        "evaluators.py",
        "accounting.py",
        "statistics.py",
        "replication.py",
        "baselines.py",
        "observed_controller_v26.py",
        "schemas.py",
    ):
        h.update(name.encode())
        h.update((base / name).read_bytes())
    return h.hexdigest()


def workflow_hash() -> str:
    base = Path(__file__).parent
    h = hashlib.sha256()
    for name in (
        "graph.py",
        "compiler.py",
        "evidence.py",
        "confirmation.py",
        "registry.py",
        "workers.py",
    ):
        h.update(name.encode())
        h.update((base / name).read_bytes())
    return h.hexdigest()
