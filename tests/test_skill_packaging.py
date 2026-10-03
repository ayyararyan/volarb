"""Skill export boundary tests: correct license, no escaped files, no partial output."""

import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / ".github" / "skill-tools"


def load_helper(name):
    spec = importlib.util.spec_from_file_location(name, HELPERS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_helper("quick_validate")
with patch.dict(sys.modules, {"quick_validate": validator}):
    exporter = load_helper("package_skill")


class SkillExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="volarb-skill-export-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.skill = self.base / "sample-skill"
        (self.skill / "agents").mkdir(parents=True)
        (self.skill / "agents" / "openai.yaml").write_text("interface: {}\n")
        (self.skill / "SKILL.md").write_text("---\nname: sample-skill\ndescription: Synthetic test skill.\n---\n# Example\n")
        self.destination = self.base / "output"

    def export(self, directory=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return exporter.package_skill(directory or self.skill, self.destination)

    def test_real_skills_include_exact_root_license_and_no_extra_payload(self):
        for directory in sorted((ROOT / "skill").iterdir()):
            if not (directory / "SKILL.md").is_file():
                continue
            with self.subTest(skill=directory.name):
                archive_path = self.export(directory)
                self.assertIsNotNone(archive_path)
                with zipfile.ZipFile(archive_path) as archive:
                    self.assertEqual(archive.read(f"{directory.name}/LICENSE"), (ROOT / "LICENSE").read_bytes())
                    self.assertEqual(archive.testzip(), None)
                    expected = {
                        f"{directory.name}/{path.relative_to(directory).as_posix()}"
                        for path in directory.rglob("*")
                        if path.is_file() and not {"__pycache__", ".pytest_cache"}.intersection(path.parts)
                        and path.suffix not in {".pyc", ".pyo"}
                    } | {f"{directory.name}/LICENSE"}
                    self.assertEqual(set(archive.namelist()), expected)
                    self.assertTrue(all(name.startswith(directory.name + "/") for name in archive.namelist()))

    def test_malformed_or_unsupported_metadata_is_rejected_without_archive(self):
        cases = ["not frontmatter", "---\nname: unfinished", "---\n- list\n---\n",
                 "---\nname: sample-skill\ndescription: [\n---\n",
                 "---\nname: sample-skill\ndescription: test\nextra-field: no\n---\n",
                 "---\nname: Bad-Name\ndescription: test\n---\n"]
        for document in cases:
            with self.subTest(document=document):
                (self.skill / "SKILL.md").write_text(document)
                self.assertFalse(validator.validate_skill(self.skill)[0])
                self.assertIsNone(self.export())
                self.assertFalse((self.destination / "skill.zip").exists())

    def test_symbolic_link_cannot_export_an_outside_file(self):
        outside = self.base / "outside.txt"
        outside.write_text("synthetic outside-file sentinel")
        (self.skill / "external.txt").symlink_to(outside)
        self.assertIsNone(self.export())
        self.assertFalse((self.destination / "skill.zip").exists())

    def test_missing_license_refuses_to_replace_prior_artifact(self):
        self.destination.mkdir()
        prior = self.destination / "skill.zip"
        prior.write_bytes(b"prior-export-sentinel")
        with patch.object(exporter, "ROOT_LICENSE", self.base / "missing-LICENSE"):
            self.assertIsNone(self.export())
        self.assertEqual(prior.read_bytes(), b"prior-export-sentinel")

    def test_size_rejection_leaves_prior_archive_and_no_partial_file(self):
        prior = self.export()
        before = prior.read_bytes()
        with patch.object(exporter, "MAX_SKILL_ZIP_BYTES", 1):
            self.assertIsNone(self.export())
        self.assertEqual(prior.read_bytes(), before)
        self.assertEqual([path.name for path in self.destination.iterdir()], ["skill.zip"])

    def test_conflicting_skill_license_is_not_silently_replaced(self):
        (self.skill / "LICENSE").write_text("different license, not an authorization")
        self.assertIsNone(self.export())
        self.assertFalse((self.destination / "skill.zip").exists())

    def test_output_inside_source_is_refused(self):
        self.destination = self.skill / "dist"
        self.assertIsNone(self.export())
        self.assertFalse(self.destination.exists())

    def test_cli_returns_failure_for_missing_skill_without_traceback(self):
        for name in ("quick_validate", "package_skill"):
            result = subprocess.run([sys.executable, str(HELPERS / f"{name}.py"), str(self.base / "missing")],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("Traceback", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
