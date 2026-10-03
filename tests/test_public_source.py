"""Public-boundary regressions; all adversarial values are invented in the test."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "public_source", Path(__file__).parents[1] / "tools/check_public_source.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class PublicSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.names = []
        self.write("LICENSE", "Proprietary test notice\n")
        self.write("THIRD_PARTY_NOTICES.md", "# Third-party notices\n")
        self.write(guard.RV_GENERATOR, "# Deterministic test generator placeholder\n")
        for name, scenario in guard.RV_FIXTURES.items():
            self.write(name, json.dumps({"provenance": {
                "kind": "synthetic", "observed_market_data": False,
                "generator": Path(guard.RV_GENERATOR).name, "scenario": scenario}}))
        self.write(guard.VRP_FIXTURE, json.dumps({"provenance": {
            "kind": "SYNTHETIC", "description": "Invented boundary case"}}))

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if name not in self.names:
            self.names.append(name)

    def inspect(self):
        return guard.inspect(self.root, self.names)

    def test_notices_placeholders_and_synthetic_fixtures_are_allowed(self):
        self.write("trade-log/README.md", "Personal records intentionally omitted\n")
        self.write("market-outlook/README.md", "Use configured private records\n")
        self.write("services/.env.example", "TOKEN=\n")
        self.write("vendor/library.LICENSE.txt", "MIT License\nCopyright Example Authors\n")
        self.write("docs/setup.md", "/Users/example/project\n/home/runner/work\n"
                   "https://YOUR-NGROK-HOST.ngrok-free.dev\n"
                   "https://example.ngrok.io\nhttp://127.0.0.1:3000\n")
        self.assertEqual(self.inspect(), [])

    def test_actual_records_are_blocked_even_when_their_content_claims_synthetic(self):
        for name in ("trade-log/trades.csv", "market-outlook/day.md", "trade-log/README.txt"):
            self.write(name, "synthetic\n")
        errors = self.inspect()
        self.assertEqual(len(errors), 3)
        self.assertTrue(all("personal-journal-or-trade-payload" in e for e in errors))

    def test_forced_tracked_secret_runtime_and_dataset_files_are_blocked(self):
        cases = {
            "service/.env": "environment-secrets-file",
            "service/.env.production": "environment-secrets-file",
            "service/.env.local.example": "environment-secrets-file",
            ".private/receipt.json": "private-runtime-directory",
            "runtime/auth.json": "authentication-artifact",
            "runtime/storageState.json": "authentication-artifact",
            "runtime/state.sqlite-wal": "runtime-database-log-or-cache",
            "datasets/ticks.parquet": "raw-or-serialized-dataset",
            "data/raw/quotes.csv": "raw-market-or-broker-records",
        }
        for name in cases:
            self.write(name, "private test content\n")
        errors = self.inspect()
        for name, category in cases.items():
            self.assertIn(guard.issue(name, 0, category), errors)

    def test_nonplaceholder_identifiers_are_detected_without_echoing_values(self):
        # Construct invented values to keep this guard's own source free of matches.
        owner = "audit-fixture-owner"
        machine = "/" + "Users" + "/" + owner + "/workspace"
        tunnel = "https://" + "audit-fixture-endpoint" + "." + "ngrok-free.app"
        self.write("docs/example.md", "heading\n" + machine + "\n" + tunnel)
        errors = self.inspect()
        self.assertIn(guard.issue("docs/example.md", 2, "personal-machine-path"), errors)
        self.assertIn(guard.issue("docs/example.md", 3, "non-placeholder-tunnel-host"), errors)
        self.assertNotIn(owner, "\n".join(errors))
        self.assertNotIn("audit-fixture-endpoint", "\n".join(errors))

    def test_test_directory_and_example_substring_do_not_bypass_detection(self):
        value = "https://" + "example-but-real-host" + "." + "ngrok.io"
        self.write("tests/fixture.txt", value)
        self.assertIn(guard.issue("tests/fixture.txt", 1, "non-placeholder-tunnel-host"), self.inspect())

    def test_required_metadata_must_be_present_nonempty_and_in_inventory(self):
        self.names.remove("LICENSE")
        self.write("THIRD_PARTY_NOTICES.md", "")
        errors = self.inspect()
        self.assertIn(guard.issue("LICENSE", 0, "required-publication-file-missing"), errors)
        self.assertIn(guard.issue("THIRD_PARTY_NOTICES.md", 0, "required-publication-file-empty"), errors)

    def test_observed_malformed_or_missing_synthetic_provenance_is_rejected(self):
        name = next(iter(guard.RV_FIXTURES))
        for content in ("{}", "[]", "not json", '{"provenance":{"kind":true}}',
                        json.dumps({"provenance": {"kind": "SYNTHETIC", "observed_market_data": True}})):
            with self.subTest(content=content):
                self.write(name, content)
                self.assertIn(guard.issue(name, 0, "synthetic-fixture-provenance-required"), self.inspect())

    def test_source_symlinks_are_not_followed(self):
        target = self.root.parent / (self.root.name + "-private")
        target.write_text("test-only private content")
        self.addCleanup(target.unlink)
        (self.root / "leak.md").symlink_to(target)
        self.names.append("leak.md")
        self.assertIn(guard.issue("leak.md", 0, "source-symlink"), self.inspect())

    def test_deleted_payload_does_not_block_working_tree_remediation(self):
        self.names.append("trade-log/deleted.csv")
        self.assertEqual(self.inspect(), [])

    def test_report_escapes_filenames_and_path_traversal_is_rejected(self):
        error = guard.issue("file\nname", 1, "category")
        self.assertNotIn("\n", error)
        self.names.append("../outside.txt")
        self.assertIn(guard.issue("../outside.txt", 0, "unsafe-source-path"), self.inspect())


if __name__ == "__main__":
    unittest.main()
