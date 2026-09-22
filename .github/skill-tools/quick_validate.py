#!/usr/bin/env python3
"""Quick validator for local skill folders."""
import sys
import re
import yaml
from pathlib import Path

def validate_skill(skill_path):
    skill_path = Path(skill_path)
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"
    content = skill_md.read_text()
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"
    try:
        frontmatter = yaml.safe_load(match.group(1))
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}"

    allowed = {"name", "description", "license", "allowed-tools", "metadata"}
    unexpected = set(frontmatter.keys()) - allowed
    if unexpected:
        return False, f"Unexpected frontmatter keys: {', '.join(sorted(unexpected))}"
    if "name" not in frontmatter or "description" not in frontmatter:
        return False, "Missing required name or description"

    name = frontmatter["name"]
    if not isinstance(name, str) or not re.match(r"^[a-z0-9-]+$", name):
        return False, "Name must be lowercase hyphen-case"
    if name.startswith("-") or name.endswith("-") or "--" in name or len(name) > 64:
        return False, "Invalid skill name"

    description = frontmatter["description"]
    if not isinstance(description, str) or "<" in description or ">" in description or len(description.strip()) > 1024:
        return False, "Invalid description"

    if not (skill_path / "agents" / "openai.yaml").exists():
        return False, "agents/openai.yaml not found"

    return True, "Skill is valid!"

if __name__ == "__main__":
    valid, message = validate_skill(sys.argv[1])
    print(message)
    raise SystemExit(0 if valid else 1)
