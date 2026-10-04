"""Language-boundary regression checks for the canonical Execution Engine."""

from __future__ import annotations

import unittest
from pathlib import Path


class ExecutionEngineLanguageBoundaryTests(unittest.TestCase):
    def test_canonical_engine_contains_no_javascript_or_typescript_implementation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        forbidden = sorted(
            path.relative_to(root)
            for suffix in ("*.mjs", "*.js", "*.ts")
            for path in root.rglob(suffix)
        )
        self.assertEqual(
            forbidden,
            [],
            "Execution Engine implementation is Python-only; JS compatibility belongs under "
            "compat/javascript/execution-contracts/",
        )

    def test_canonical_python_package_exists(self) -> None:
        root = Path(__file__).resolve().parents[1]
        package = root / "volarb_execution"
        self.assertTrue((package / "__init__.py").is_file())
        self.assertTrue((package / "recovery" / "command_commit_guard.py").is_file())


if __name__ == "__main__":
    unittest.main()
