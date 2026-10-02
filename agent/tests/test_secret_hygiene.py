"""Repository checks deliberately inspect tracked source, never private .env contents."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


AGENT = Path(__file__).parents[1]
REPO = AGENT.parent


def test_private_dotenv_is_ignored_and_not_tracked():
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "agent/.env"], cwd=REPO, capture_output=True
    )
    assert ignored.returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "agent/.env"], cwd=REPO, capture_output=True
    )
    assert tracked.returncode != 0
    template = subprocess.run(
        ["git", "check-ignore", "--no-index", "agent/.env.example"], cwd=REPO, capture_output=True
    )
    assert template.returncode == 1


def test_template_contains_no_credentials_or_oauth_material():
    text = (AGENT / ".env.example").read_text()
    values = {
        key.strip(): value.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        for key, value in [line.split("=", 1)]
    }
    assert values["OPENAI_API_KEY"] == ""
    assert not any(
        word in key.upper()
        for key in values
        for word in ("OAUTH", "REFRESH", "ACCESS_TOKEN", "SIGNING", "AUTHORIZATION")
    )
    assert not re.search(r"https?://[^\s/]+:[^\s/]+@", text)


def test_tracked_agent_sources_contain_no_probable_secrets_or_runtime_state():
    paths = (
        subprocess.check_output(["git", "ls-files", "-z", "--", "agent"], cwd=REPO)
        .decode()
        .split("\0")
    )
    # Detect credential-shaped values, not harmless variable names or clearly
    # synthetic fixtures. Errors report only filenames, never matched content.
    patterns = [
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
        re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/"),
    ]
    forbidden_suffixes = {".sqlite", ".sqlite3", ".db", ".pem", ".key"}
    failures = []
    for relative in filter(None, paths):
        path = REPO / relative
        if not path.is_file():
            continue
        if (
            (path.name == ".env" or path.name.startswith(".env.")) and path.name != ".env.example"
        ) or path.suffix in forbidden_suffixes:
            failures.append(relative)
            continue
        text = path.read_text(errors="replace")
        if any(pattern.search(text) for pattern in patterns):
            failures.append(relative)
    assert not failures, "Probable credentials or private runtime files in: " + ", ".join(failures)
