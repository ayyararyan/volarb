#!/usr/bin/env python3
"""Offline repository hygiene: local Markdown paths/anchors, JSON and JS imports.

External URLs, command examples and historical prose are deliberately not executed.
This is a source-tree check, not a network link checker or production readiness test.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r'\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)')
REFERENCE = re.compile(r'^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)', re.MULTILINE)
IMPORT = re.compile(r'''(?:\bfrom\s*|\bimport\s*\(?\s*)['"](\.[^'"]+)['"]''')


def prose(text: str) -> str:
    """Strip fenced code without mistaking nested/inline backticks for fences."""
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence):
                fence = None
            continue
        if match:
            fence = match[1]
            continue
        lines.append(line)
    return '\n'.join(lines)


def anchors(text: str) -> set[str]:
    found = set(re.findall(r'''<(?:a|[a-z][a-z0-9]*)\b[^>]*\b(?:id|name)=["']([^"']+)["']''', text, re.I))
    counts: dict[str, int] = {}
    for line in prose(text).splitlines():
        match = re.match(r'^\s{0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$', line)
        if not match:
            continue
        heading = re.sub(r'<[^>]*>', '', match[1]).lower()
        heading = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', heading)
        slug = re.sub(r'[^\w\-\s]', '', heading).replace(' ', '-')
        n = counts.get(slug, 0)
        counts[slug] = n + 1
        found.add(f'{slug}-{n}' if n else slug)
    return found


def markdown_errors(path: Path, root: Path) -> list[str]:
    content = prose(path.read_text())
    errors = []
    for match in list(LINK.finditer(content)) + list(REFERENCE.finditer(content)):
        dest = match[1].strip('<>')
        url = urlsplit(dest)
        source_prefix = '/ayyararyan/volarb/blob/main/'
        if url.scheme and url.netloc == 'github.com' and url.path.startswith(source_prefix):
            target = root / unquote(url.path[len(source_prefix):])
        else:
            if url.scheme or dest.startswith('//'):
                continue
            decoded = unquote(url.path)
            target = (root / decoded.lstrip('/')) if decoded.startswith('/') else path.parent / decoded
            if not decoded:
                target = path
        if not target.exists():
            errors.append(f'missing local link: {dest}')
        elif url.fragment and target.suffix.lower() == '.md' and unquote(url.fragment) not in anchors(target.read_text()):
            errors.append(f'missing Markdown anchor: {dest}')
    return errors


def inspect(root: Path, names: list[str]) -> list[str]:
    errors = []
    for name in names:
        path = root / name
        if not path.is_file():
            continue  # Deleted tracked files during an uncommitted cleanup.
        if path.suffix.lower() == '.md':
            errors.extend(f'{name}: {e}' for e in markdown_errors(path, root))
        elif path.suffix == '.json':
            try:
                json.loads(path.read_text())
            except (ValueError, UnicodeError) as exc:
                errors.append(f'{name}: invalid JSON: {exc}')
        elif path.suffix in {'.mjs', '.js'} and '/vendor/' not in name:
            for match in IMPORT.finditer(path.read_text()):
                if not (path.parent / match[1]).is_file():
                    errors.append(f'{name}: missing relative JS import: {match[1]}')
    archive = root / 'archive'
    if archive.exists():
        for directory in [archive, *sorted(p for p in archive.rglob('*') if p.is_dir())]:
            if not (directory / 'README.md').is_file():
                errors.append(f'{directory.relative_to(root)}: archive directory has no README.md')
    return errors


def main() -> int:
    names = subprocess.check_output(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT
    ).decode().split('\0')
    names = sorted(set(filter(None, names)))
    errors = inspect(ROOT, names)
    if errors:
        print('\n'.join(errors))
        print(f'Repository hygiene failed: {len(errors)} issue(s)')
        return 1
    print(f'Repository hygiene passed: {len(names)} source paths; local links/anchors, JSON, JS imports and archive indexes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
