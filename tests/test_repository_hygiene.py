"""Regression checks for repository links that must survive archival moves."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('hygiene', Path(__file__).parents[1] / 'tools/check_repository.py')
hygiene = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hygiene)


class RepositoryHygieneTests(unittest.TestCase):
    def test_links_anchors_and_reference_definitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'target file.md').write_text('# One\n# One\n## Runtime & Ports\n<a id="stable"></a>\n')
            source = root / 'README.md'
            source.write_text('[a](<target file.md#one-1>)\n[b](target%20file.md#runtime--ports)\n[c](target%20file.md#stable)\n[r]: missing.md\n')
            self.assertEqual(hygiene.markdown_errors(source, root), ['missing local link: missing.md'])
            source.write_text('[a](target%20file.md#removed)\n')
            self.assertEqual(hygiene.markdown_errors(source, root), ['missing Markdown anchor: target%20file.md#removed'])

    def test_examples_and_external_links_are_not_executed_or_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'README.md'
            source.write_text('```md\n[x](not-real.md)\n```\n~~~\n[x](also-not-real.md)\n~~~\n[x](https://example.invalid/a)\n')
            self.assertEqual(hygiene.markdown_errors(source, root), [])

    def test_standalone_skill_local_links_stay_inside_their_bundle(self):
        root = Path(__file__).parents[1]
        for skill in (root / 'skill').iterdir():
            if not skill.is_dir():
                continue
            for path in skill.rglob('*.md'):
                content = hygiene.prose(path.read_text())
                for match in list(hygiene.LINK.finditer(content)) + list(hygiene.REFERENCE.finditer(content)):
                    url = hygiene.urlsplit(match[1].strip('<>'))
                    if url.scheme or not url.path:
                        continue
                    target = (path.parent / hygiene.unquote(url.path)).resolve()
                    self.assertTrue(target.is_relative_to(skill.resolve()), f'{path}: unbundled local link {url.path}')
                    self.assertTrue(target.exists(), f'{path}: missing bundled target {url.path}')

    def test_canonical_repository_links_resolve_against_source_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'README.md'
            source.write_text('[a](https://github.com/ayyararyan/volarb/blob/main/missing.md)')
            self.assertEqual(len(hygiene.markdown_errors(source, root)), 1)

    def test_import_json_and_archive_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'sample.mjs').write_text('export {x} from "./missing.mjs";')
            (root / 'bad.json').write_text('{')
            (root / 'archive' / 'generation').mkdir(parents=True)
            errors = hygiene.inspect(root, ['sample.mjs', 'bad.json'])
            self.assertEqual(len(errors), 4)
            self.assertTrue(any('missing relative JS import' in error for error in errors))
            self.assertTrue(any('invalid JSON' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
