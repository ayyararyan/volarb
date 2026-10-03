"""Explicit caller-supplied calendars for the bounded Jan/Feb archive examples.

No calendar is inferred from weekdays or downloaded. Calendar-file hashes bind
the exact local input; source references are recorded, not independently fetched.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit


CAPTURED_ONLY = "captured-directory-only, not verified exchange calendar"


def validate_session(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise ValueError("calendar sessions must be ISO YYYY-MM-DD strings")
    date.fromisoformat(value)
    if not "2026-01-01" <= value <= "2026-02-28":
        raise ValueError("session outside registered Jan-Feb2026 source scope")
    return value


def read_calendar(path: Path) -> tuple[list[str], dict[str, Any]]:
    raw = path.read_bytes()
    value = json.loads(raw)
    sessions = value.get("expected_sessions") if isinstance(value, dict) else value
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("calendar must contain a nonempty expected_sessions list")
    sessions = [validate_session(session) for session in sessions]
    if sessions != sorted(set(sessions)):
        raise ValueError("calendar sessions must be unique and chronologically ordered")
    references = value.get("references", []) if isinstance(value, dict) else []
    if not isinstance(references, list):
        raise ValueError("calendar references must be a list")
    public_references = []
    for reference in references:
        if not isinstance(reference, dict):
            raise ValueError("calendar source reference must contain a URL and SHA-256")
        url, digest = reference.get("url"), reference.get("sha256")
        if not isinstance(url, str) or not isinstance(digest, str):
            raise ValueError("calendar source reference must contain a URL and SHA-256")
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username:
            raise ValueError("calendar source reference must use a public HTTP(S) URL")
        if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            raise ValueError("calendar source reference has an invalid SHA-256")
        public_references.append({"url": url, "sha256": digest.lower()})
    return sessions, {
        "coverage_basis": "explicit caller-supplied session calendar",
        "calendar_sha256": hashlib.sha256(raw).hexdigest(),
        "references": public_references,
        "calendar_validation": "ISO dates, Jan-Feb2026 scope, uniqueness and chronology checked; referenced evidence not fetched by builder",
    }


def archive_sessions(
    archive_root: Path, calendar: Path | None = None, *, require_months: bool = False
) -> tuple[list[tuple[str, Path]], dict[str, Any]]:
    captured: dict[str, Path] = {}
    months = {"01": "january_2026", "02": "february_2026"}
    for month in months.values():
        root = archive_root / month
        if not root.is_dir():
            if require_months and calendar is None:
                raise FileNotFoundError(f"missing expected raw month: {month}")
            continue
        for path in sorted(root.iterdir()):
            if path.is_dir() and path.name.startswith("2026_"):
                session = validate_session(path.name.replace("_", "-"))
                if session in captured:
                    raise ValueError("duplicate raw session directories")
                if months[session[5:7]] != month:
                    raise ValueError("raw session directory does not match parent month")
                captured[session] = path
    if calendar is None:
        return sorted(captured.items()), {"coverage_basis": CAPTURED_ONLY}
    expected, provenance = read_calendar(calendar)
    if set(captured) - set(expected):
        raise ValueError(
            "captured session absent from supplied calendar; refusing silent exclusion"
        )
    return [
        (
            session,
            captured.get(
                session,
                archive_root / months[session[5:7]] / session.replace("-", "_"),
            ),
        )
        for session in expected
    ], provenance
