#!/usr/bin/env python3
"""Check VolArb's skill metadata contract without executing skill code.

Implementation replaced for the 2026-10-04 publication audit. The public
``validate_skill(path) -> (bool, explanation)`` interface is retained.
Copyright © 2026 Shunya. All Rights Reserved. See the repository LICENSE.
"""

import argparse
from collections.abc import Mapping
from pathlib import Path

import yaml

METADATA_FIELDS = frozenset({"name", "description", "license", "allowed-tools", "metadata"})


def _metadata(document):
    lines = document.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must start with a YAML frontmatter delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("SKILL.md frontmatter has no closing delimiter") from error
    values = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(values, Mapping):
        raise ValueError("Skill metadata must be a mapping")
    extra = set(values).difference(METADATA_FIELDS)
    if extra:
        raise ValueError("Unsupported skill metadata field(s): " + ", ".join(sorted(map(str, extra))))
    return values


def validate_skill(skill_path):
    """Return a validation result; malformed documents do not escape as errors."""
    directory = Path(skill_path)
    try:
        values = _metadata((directory / "SKILL.md").read_text(encoding="utf-8"))
        name = values.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 64:
            raise ValueError("A skill name of 1–64 characters is required")
        segments = name.split("-")
        if any(not segment or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789" for char in segment)
               for segment in segments):
            raise ValueError("Skill names must contain lowercase ASCII words separated by single hyphens")
        description = values.get("description")
        if not isinstance(description, str) or len(description.strip()) > 1024:
            raise ValueError("A text description of at most 1024 characters is required")
        if set(description).intersection("<>"):
            raise ValueError("Skill descriptions cannot contain angle brackets")
        if not (directory / "agents" / "openai.yaml").is_file():
            raise ValueError("The skill must include agents/openai.yaml")
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
        return False, str(error)
    return True, f"Metadata and agent entrypoint verified for {name}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", type=Path)
    arguments = parser.parse_args()
    accepted, explanation = validate_skill(arguments.skill_path)
    print(explanation)
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
