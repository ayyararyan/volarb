#!/usr/bin/env python3
"""Package a validated skill folder into skill.zip."""
import sys
import zipfile
from pathlib import Path
from quick_validate import validate_skill

MAX_SKILL_ZIP_BYTES = 25 * 1024 * 1024

def package_skill(skill_path, output_dir=None):
    skill_path = Path(skill_path).resolve()
    if not skill_path.exists() or not skill_path.is_dir():
        print(f"Skill folder not found: {skill_path}")
        return None
    if not (skill_path / "SKILL.md").exists():
        print(f"SKILL.md not found in {skill_path}")
        return None

    print("Validating skill...")
    valid, message = validate_skill(skill_path)
    if not valid:
        print(f"Validation failed: {message}")
        return None
    print(message)

    output_path = Path(output_dir).resolve() if output_dir else Path.cwd()
    output_path.mkdir(parents=True, exist_ok=True)
    skill_filename = output_path / "skill.zip"

    with zipfile.ZipFile(skill_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in skill_path.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(skill_path.parent)
                zipf.write(file_path, arcname)
                print(f"Added: {arcname}")

    archive_size = skill_filename.stat().st_size
    print(f"Archive size: {archive_size:,} bytes")
    if archive_size > MAX_SKILL_ZIP_BYTES:
        print("skill.zip exceeds the 25 MB upload limit")
        return None
    print(f"Successfully packaged: {skill_filename}")
    return skill_filename

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: package_skill.py <skill-folder> [output-directory]")
        raise SystemExit(1)
    result = package_skill(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    raise SystemExit(0 if result else 1)
