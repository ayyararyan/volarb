#!/usr/bin/env python3
"""Offline tripwire for accidental private material in the public source tree.

This is NOT a secret scanner, Git-history audit, data-license review or publication
clearance. It checks narrow, known repository boundaries and prints path, line and
category only, never matched content. Run dedicated secret/history scans as well.
Synthetic labels are assertions, not proof: the RV fixture checker separately
runs generate_synthetic_fixtures.py --check to establish reproducibility.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
RV_ROOT = "skill/intraday-realized-volatility-forecast/scripts"
RV_GENERATOR = f"{RV_ROOT}/generate_synthetic_fixtures.py"
RV_FIXTURES = {f"{RV_ROOT}/test_{name}.json": name for name in
               ("stable", "trend", "jump", "mode_bucket_jump")}
VRP_FIXTURE = "skill/butterfly-market-outlook/tests/fixtures_session_vrp_synthetic.json"
REQUIRED = ("LICENSE", "THIRD_PARTY_NOTICES.md", RV_GENERATOR,
            *RV_FIXTURES, VRP_FIXTURE)

# Narrow path rules, not a ban on source modules named ledger/data/auth.
PRIVATE_DIRECTORIES = {".private", ".secrets", "auth-cache", "browser-profile",
                       "browser-state", "runtime-state", "node_modules", ".venv",
                       "__pycache__"}
AUTH_FILES = {"auth.json", "credentials.json", "client_secret.json", "token.json",
              "tokens.json", "oauth-tokens.json", "cookies.json", "cookies.txt",
              "storage-state.json", "storagestate.json", "browser-state.json",
              "cookies", "login data", "local state"}
RUNTIME_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".pyc", ".pyo"}
DATA_SUFFIXES = {".parquet", ".pq", ".feather", ".arrow", ".h5", ".hdf5",
                 ".pickle", ".pkl"}
MACHINE_PATH = re.compile(r"/(?:Users|home)/([A-Za-z0-9_][A-Za-z0-9_.-]*)(?=/|\b)")
PLACEHOLDER_USERS = {"example", "user", "username", "runner", "test", "test-user",
                     "synthetic-user", "fixture-user", "your-user", "your-username"}
TUNNEL_HOST = re.compile(
    r"(?<![A-Za-z0-9_.-])([A-Za-z0-9][A-Za-z0-9.-]*)\."
    r"(?:ngrok(?:-free)?\.(?:app|dev|io))(?![A-Za-z0-9_.-])", re.IGNORECASE)
PLACEHOLDER_HOSTS = {"example", "your-domain", "your-subdomain", "your-ngrok-host",
                     "private-tunnel-domain", "example-host", "example-tunnel"}


def issue(name: str, line: int, category: str) -> str:
    """Escape filenames so malicious names cannot inject terminal output lines."""
    return f"{json.dumps(name, ensure_ascii=True)}:{line}: {category}"


def content_issues(name: str, text: str) -> list[str]:
    errors = []
    for number, line in enumerate(text.splitlines(), 1):
        if any(m[1].lower() not in PLACEHOLDER_USERS for m in MACHINE_PATH.finditer(line)):
            errors.append(issue(name, number, "personal-machine-path"))
        if any(m[1].lower() not in PLACEHOLDER_HOSTS for m in TUNNEL_HOST.finditer(line)):
            errors.append(issue(name, number, "non-placeholder-tunnel-host"))
    return errors


def inspect(root: Path, names: list[str]) -> list[str]:
    """Inspect listed working-tree files, including files force-added past ignores."""
    errors = []
    present = set(names)
    for required in REQUIRED:
        path = root / required
        if required not in present or not path.is_file() or path.is_symlink():
            errors.append(issue(required, 0, "required-publication-file-missing"))
        elif not path.stat().st_size:
            errors.append(issue(required, 0, "required-publication-file-empty"))

    for name in sorted(present):
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(issue(name, 0, "unsafe-source-path"))
            continue
        path = root / name
        if path.is_symlink():
            errors.append(issue(name, 0, "source-symlink"))
            continue
        if not path.exists():
            continue  # A tracked deletion pending commit is not published content.
        if not path.is_file():
            errors.append(issue(name, 0, "non-file-source-entry"))
            continue

        parts = tuple(p.lower() for p in relative.parts)
        basename = relative.name.lower()
        suffix = relative.suffix.lower()
        if parts[0] in {"market-outlook", "trade-log"} and name not in {
                "market-outlook/README.md", "trade-log/README.md"}:
            errors.append(issue(name, 0, "personal-journal-or-trade-payload"))
        if (basename == ".env" or basename.startswith(".env.")) and basename != ".env.example":
            errors.append(issue(name, 0, "environment-secrets-file"))
        if set(parts[:-1]) & PRIVATE_DIRECTORIES or "trading/ledger" in "/".join(parts) or "trading/snapshots" in "/".join(parts):
            errors.append(issue(name, 0, "private-runtime-directory"))
        if basename in AUTH_FILES or basename.startswith(("id_rsa", "id_ed25519")):
            errors.append(issue(name, 0, "authentication-artifact"))
        if suffix in RUNTIME_SUFFIXES or re.search(r"\.(?:sqlite3?|db)-(?:wal|shm|journal)$", basename):
            errors.append(issue(name, 0, "runtime-database-log-or-cache"))
        if suffix in DATA_SUFFIXES:
            errors.append(issue(name, 0, "raw-or-serialized-dataset"))
        if suffix in {".csv", ".jsonl", ".ndjson"} and set(parts[:-1]) & {
                "raw", "raw-data", "market-data", "broker-data", "snapshots"}:
            errors.append(issue(name, 0, "raw-market-or-broker-records"))

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            # Known source image/font binaries are handled by their asset review.
            # All runtime/data file checks above apply even to binary inputs.
            continue
        except OSError:
            errors.append(issue(name, 0, "unreadable-source-file"))
            continue
        errors.extend(content_issues(name, text))
        if name in RV_FIXTURES or name == VRP_FIXTURE:
            try:
                payload = json.loads(text)
                provenance = payload.get("provenance")
                valid = isinstance(provenance, dict) and provenance.get("kind", "").upper() == "SYNTHETIC"
                if valid and name in RV_FIXTURES:
                    valid = (provenance.get("observed_market_data") is False
                             and provenance.get("generator") == Path(RV_GENERATOR).name
                             and provenance.get("scenario") == RV_FIXTURES[name])
                elif valid:
                    valid = provenance.get("observed_market_data") is not True
                if not valid:
                    errors.append(issue(name, 0, "synthetic-fixture-provenance-required"))
            except (ValueError, AttributeError, TypeError):
                errors.append(issue(name, 0, "synthetic-fixture-provenance-required"))
    return errors


def main() -> int:
    try:
        names = subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        ).decode().split("\0")
        errors = inspect(ROOT, list(filter(None, names)))
    except (OSError, UnicodeError, subprocess.CalledProcessError):
        print(issue(".", 0, "source-inventory-unavailable"))
        return 1
    if errors:
        print("\n".join(errors))
        print(f"Public-source guard failed: {len(errors)} issue(s)")
        return 1
    print("Public-source guard passed; not a secret/history scan or publication clearance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
