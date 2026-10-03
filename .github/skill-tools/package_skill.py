#!/usr/bin/env python3
"""Export a validated VolArb skill with its governing proprietary license.

Implementation replaced for the 2026-10-04 publication audit. The public
``package_skill(path, output_dir=None) -> Path | None`` interface is retained.
Copyright © 2026 Shunya. All Rights Reserved. See the repository LICENSE.
"""

import argparse
import os
from pathlib import Path
import tempfile
import zipfile

from quick_validate import validate_skill

MAX_SKILL_ZIP_BYTES = 25 * 1024 * 1024
ROOT_LICENSE = Path(__file__).resolve().parents[2] / "LICENSE"
_IGNORED_DIRECTORIES = frozenset({"__pycache__", ".pytest_cache"})


def _export_files(directory):
    """Build a stable inventory without following links outside the skill."""
    inventory = []
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if _IGNORED_DIRECTORIES.intersection(relative.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError(f"Skill exports do not accept symbolic links: {relative}")
        if path.is_file():
            inventory.append((path, relative))
    return inventory


def package_skill(skill_path, output_dir=None):
    """Publish skill.zip only after validation, licensing and size checks pass."""
    temporary = None
    try:
        requested = Path(skill_path).expanduser()
        if requested.is_symlink():
            raise ValueError("The skill root cannot be a symbolic link")
        directory = requested.resolve()
        accepted, explanation = validate_skill(directory)
        if not accepted:
            raise ValueError(explanation)
        license_text = ROOT_LICENSE.read_bytes()
        if not license_text.strip():
            raise ValueError("The repository LICENSE is empty")
        inventory = _export_files(directory)
        for source, relative in inventory:
            if relative == Path("LICENSE") and source.read_bytes() != license_text:
                raise ValueError("The skill LICENSE conflicts with the repository LICENSE")
        destination = Path(output_dir or Path.cwd()).expanduser().resolve()
        if destination == directory or directory in destination.parents:
            raise ValueError("Choose an output directory outside the skill source")
        destination.mkdir(parents=True, exist_ok=True)
        archive_path = destination / "skill.zip"
        with tempfile.NamedTemporaryFile(prefix=".skill-export-", suffix=".zip", dir=destination,
                                         delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source, relative in inventory:
                if relative != Path("LICENSE"):
                    archive.write(source, (Path(directory.name) / relative).as_posix())
            archive.writestr(f"{directory.name}/LICENSE", license_text)
        size = temporary.stat().st_size
        if size > MAX_SKILL_ZIP_BYTES:
            raise ValueError(f"The compressed export exceeds the {MAX_SKILL_ZIP_BYTES}-byte limit")
        os.replace(temporary, archive_path)
        print(f"Exported {directory.name}: {archive_path} ({size} bytes; LICENSE included)")
        return archive_path
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as error:
        print(f"Skill export refused: {error}")
        return None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", type=Path)
    parser.add_argument("output_dir", type=Path, nargs="?")
    arguments = parser.parse_args()
    return 0 if package_skill(arguments.skill_path, arguments.output_dir) is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
