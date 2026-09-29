#!/usr/bin/env python3
"""Install/inspect a portable VolArb workspace. Never starts services or trades."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((SOURCE / 'agent-kit/manifest.json').read_text())
SKIP_PARTS = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', '.private', '.logs', 'dist'}
DEFAULT_DATA = Path.home() / '.local/share/volarb'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def clean_path(value):
    path = Path(value).expanduser()
    require(not any(ord(c) < 32 for c in str(path)), 'Control characters are not allowed in paths')
    require(not path.is_symlink(), 'Symlink directory is not accepted: ' + str(path))
    return path.resolve()


def command(argv, *, cwd=SOURCE, env=None, capture=False):
    result = subprocess.run([str(a) for a in argv], cwd=cwd, env=env,
                            capture_output=capture, text=True, timeout=600)
    require(result.returncode == 0, 'Command failed: ' + str(argv[0]) + ' (inspect locally; no credentials are printed)')
    return result.stdout if capture else ''


def version(executable, *args):
    try:
        result = subprocess.run([str(executable), *args], capture_output=True, text=True, timeout=20)
        return (result.stdout or result.stderr).strip() if result.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def private_dir(path):
    if path.exists():
        require(path.is_dir() and not path.is_symlink(), 'Expected a real directory: ' + str(path))
        require(not path.stat().st_mode & 0o077, 'Existing private directory needs owner-only permissions: ' + str(path))
    else:
        path.mkdir(parents=True, mode=0o700)


def safe_target(path, root):
    require(path.is_relative_to(root), 'Target outside installation root')
    current = path
    while current != root.parent:
        require(not current.is_symlink(), 'Refusing symlink target: ' + str(current))
        current = current.parent


def source_files(root):
    for p in sorted(root.rglob('*')):
        if any(part in SKIP_PARTS for part in p.relative_to(root).parts):
            continue
        require(not p.is_symlink(), 'Source symlink not allowed: ' + str(p))
        if p.is_file() and p.suffix not in {'.pyc', '.log'} and not p.name.endswith('~'):
            yield p


def registration_state(agent, workspace):
    executable = shutil.which('openclaw')
    require(executable, 'OpenClaw missing; install the version in agent-kit/manifest.json first')
    require(MANIFEST['runtimes']['openclaw'] in version(executable, '--version'), 'OpenClaw version differs from the supported pin')
    data = json.loads(command([executable, 'agents', 'list', '--json'], capture=True))
    agents = data if isinstance(data, list) else data.get('agents', [])
    existing = next((a for a in agents if a.get('id') == agent), None)
    if existing:
        require(Path(existing.get('workspace', '')).expanduser().resolve() == workspace,
                'Existing agent points elsewhere; choose another --agent-id (nothing overwritten)')
    return executable, existing


def setup(args):
    require(platform.system() in MANIFEST['platforms'], 'Use macOS, Linux or WSL2; native Windows unsupported')
    require(re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', args.agent_id), 'Invalid agent id')
    data = clean_path(args.data_dir)
    workspace = clean_path(args.workspace or Path.home() / '.openclaw/workspace' / args.agent_id)
    require(not data.is_relative_to(SOURCE) and not workspace.is_relative_to(SOURCE), 'Keep data/workspace outside the source checkout')
    require(not data.is_relative_to(workspace) and not workspace.is_relative_to(data), 'Data and workspace must be separate, non-nested directories')
    config_file = data / 'config.json'
    config = {'format': 'volarb.install.v1', 'kit_version': MANIFEST['version'], 'source_dir': str(SOURCE),
              'workspace': str(workspace), 'data_dir': str(data), 'config_file': str(config_file),
              'profile': args.profile, 'mode': args.mode, 'agent_id': args.agent_id,
              'execution_enabled': False, 'schedules_enabled': False, 'browser_recovery_enabled': False,
              'runtimes': MANIFEST['runtimes']}
    # Build the complete write plan before any mutation. Personal files are create-only.
    planned = {config_file: json_bytes(config), workspace / 'volarb-install.json': json_bytes(config)}
    for p in source_files(SOURCE / 'agent-kit/workspace'):
        target = workspace / p.relative_to(SOURCE / 'agent-kit/workspace')
        safe_target(target, workspace)
        if not target.exists():
            planned[target] = p.read_bytes()
    for skill in MANIFEST['skills']:
        src = SOURCE / 'skill' / skill
        for p in source_files(src):
            planned[workspace / 'skills' / skill / p.relative_to(src)] = p.read_bytes()
    planned[workspace / 'volarb-profile.json'] = (SOURCE / 'agent-kit/profiles' / (args.profile + '.json')).read_bytes()
    private_env = data / 'dhan/.env'
    safe_target(private_env, data)
    if not private_env.exists():
        planned[private_env] = (SOURCE / 'services/dhan-chatgpt-mcp/.env.example').read_bytes()
    for target, contents in planned.items():
        safe_target(target, data if target.is_relative_to(data) else workspace)
        require(not target.exists() or target.is_file() and target.read_bytes() == contents,
                'Existing file differs; preserve/merge it manually before retry: ' + str(target))
    if args.register_agent:
        executable, existing_agent = registration_state(args.agent_id, workspace)
    python = None
    if not args.no_install:
        python = shutil.which(args.python)
        require(python, 'Python runtime missing; install Python ' + MANIFEST['runtimes']['python'])
        require(version(python, '--version') == 'Python ' + MANIFEST['runtimes']['python'], 'Use the pinned Python ' + MANIFEST['runtimes']['python'])
        require(version('node', '--version') == 'v' + MANIFEST['runtimes']['node'], 'Use the pinned Node ' + MANIFEST['runtimes']['node'])
        require(version('npm', '--version') == MANIFEST['runtimes']['npm'], 'Use the pinned npm ' + MANIFEST['runtimes']['npm'])
        vpython = SOURCE / '.venv/bin/python'
        require(not (SOURCE/'.venv').is_symlink(), 'Refusing symlink virtual environment')
        if (SOURCE/'.venv').exists():
            require(version(vpython, '--version') == version(python, '--version'), 'Existing .venv uses a different runtime; use a fresh checkout')
    private_dir(data)
    private_dir(data/'dhan')
    private_dir(data/'dhan/.private')
    if not workspace.exists():
        workspace.mkdir(parents=True, mode=0o700)
    for target, contents in planned.items():
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not target.exists():
            # Exclusive create protects against a concurrent setup or user edit.
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(contents)
    if not args.no_install:
        if not (SOURCE/'.venv').exists():
            command([python, '-m', 'venv', SOURCE/'.venv'])
        lock = 'requirements-dev.lock' if args.dev else 'requirements.lock'
        command([vpython, '-m', 'pip', 'install', '--disable-pip-version-check', '--require-hashes', '--only-binary=:all:', '-r', SOURCE/lock])
        command(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=SOURCE/'services/dhan-chatgpt-mcp')
    if args.register_agent:
        if not existing_agent:
            command([executable, 'agents', 'add', args.agent_id, '--workspace', workspace, '--non-interactive', '--json'], capture=True)
        # The supported CLI registers discovery from workspace/skills. Verify the result.
        data_skills = json.loads(command([executable, 'skills', 'list', '--agent', args.agent_id, '--json'], capture=True))
        found = {s['name'] for s in data_skills.get('skills', []) if s.get('eligible')}
        require(set(MANIFEST['skills']) <= found, 'Agent created but some skills unavailable; run OpenClaw skills check')
    return {'status': 'SETUP_COMPLETE' if not args.no_install else 'FILES_PREPARED_DEPENDENCIES_NOT_INSTALLED',
            'config_file': str(config_file), 'skills': MANIFEST['skills'], 'mode': args.mode,
            'agent_registered': args.register_agent, 'services_started': False, 'jobs_scheduled': False,
            'credentials_copied': False, 'ledger_created': False, 'trading_ready': False}


def read_config(path):
    p = clean_path(path)
    require(not p.stat().st_mode & 0o077, 'Config must have owner-only permissions')
    c = json.loads(p.read_text())
    require(c.get('format') == 'volarb.install.v1', 'Unknown config format')
    require(c.get('mode') in MANIFEST['modes'], 'Unsupported mode; this kit never enables execution')
    require(Path(c['source_dir']).resolve() == SOURCE, 'Checkout moved; configuration must be reviewed/recreated for this source location')
    require(c.get('execution_enabled') is False and c.get('schedules_enabled') is False,
            'Execution/scheduler activation is not supported by this kit')
    return c


def runtime_env(c):
    env = os.environ.copy()
    env.update(VOLARB_SOURCE_DIR=str(SOURCE), VOLARB_DATA_DIR=c['data_dir'],
               DHAN_RUNTIME_DIR=str(Path(c['data_dir'])/'dhan'),
               VOLARB_OBSERVE_ENABLED=str(c['mode'] == 'read-only').lower(),
               DHAN_EXECUTION_ENABLED='false', DHAN_BROWSER_RECOVERY_ENABLED='false',
               PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    env['PATH'] = str(SOURCE/'.venv/bin') + os.pathsep + env.get('PATH', '')
    return env


def doctor(args):
    c = read_config(args.config)
    checks = []
    def check(name, ok, remedy, required=True):
        checks.append({'name': name, 'status': 'PASS' if ok else 'FAIL' if required else 'WARN',
                       'remedy': '' if ok else remedy})
    check('platform', platform.system() in MANIFEST['platforms'], 'Use macOS/Linux/WSL2')
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo('Asia/Kolkata')
        timezone_ok = True
    except (ImportError, KeyError):
        timezone_ok = False
    check('timezone_database', timezone_ok, 'Install the host IANA timezone database (tzdata)')
    for tool, actual, expected in [
        ('python', version(SOURCE/'.venv/bin/python', '--version'), 'Python '+MANIFEST['runtimes']['python']),
        ('node', version('node', '--version'), 'v'+MANIFEST['runtimes']['node']),
        ('npm', version('npm', '--version'), MANIFEST['runtimes']['npm'])]:
        check(tool, actual == expected, 'Install pinned runtime '+expected+' and rerun setup')
    py = SOURCE/'.venv/bin/python'
    check('python_dependencies', bool(version(py, '-c', 'import numpy; print(numpy.__version__)')) and
          version(py, '-c', 'import numpy; print(numpy.__version__)') == '2.4.3', 'Rerun setup to install requirements.lock')
    npm = shutil.which('npm')
    npm_ok = False
    if npm and (SOURCE/'services/dhan-chatgpt-mcp/node_modules').is_dir():
        proc = subprocess.run([npm, 'ls', '--all', '--json'], cwd=SOURCE/'services/dhan-chatgpt-mcp', capture_output=True, text=True, timeout=30)
        npm_ok = proc.returncode == 0
    check('node_dependencies', npm_ok, 'Rerun setup; npm ci installs package-lock.json')
    workspace = Path(c['workspace']); data = Path(c['data_dir'])
    check('private_data_permissions', data.is_dir() and not data.is_symlink() and not data.stat().st_mode & 0o077,
          'Private data root must be an owner-only directory (mode 700)')
    for skill in MANIFEST['skills']:
        src = SOURCE/'skill'/skill
        installed = workspace/'skills'/skill
        expected = {p.relative_to(src): digest(p.read_bytes()) for p in source_files(src)}
        try:
            actual = {p.relative_to(installed): digest(p.read_bytes()) for p in source_files(installed)}
            ok = expected == actual
        except ValueError:
            ok = False
        check('skill:'+skill, ok, 'Missing/drifted skill: compare source and installed copy; preserve local edits')
    for name in ['AGENTS.md', 'SOUL.md', 'USER.md', 'TOOLS.md', 'volarb-profile.json', 'volarb-install.json']:
        check('workspace:'+name, (workspace/name).is_file(), 'Run setup; personal files are never overwritten')
    check('openclaw_version', MANIFEST['runtimes']['openclaw'] in version('openclaw', '--version'),
          'Install OpenClaw '+MANIFEST['runtimes']['openclaw']+' and configure a model provider', required=False)
    try:
        _, registered = registration_state(c['agent_id'], workspace)
        check('agent_registration', bool(registered), 'Rerun setup with --register-agent to register this isolated workspace', required=False)
    except (ValueError, OSError, subprocess.SubprocessError):
        check('agent_registration', False, 'OpenClaw missing/incompatible or agent points elsewhere; inspect locally', required=False)
    env_file = data/'dhan/.env'
    values = {}
    secure = env_file.is_file() and not env_file.is_symlink() and not env_file.stat().st_mode & 0o077
    if secure:
        # Presence only. Never print values or claim authenticated broker access.
        for line in env_file.read_text().splitlines():
            match = re.match(r'^\s*([A-Z_]+)\s*=\s*(.*?)\s*$', line)
            if match:
                values[match[1]] = match[2].strip('\"\'')
    check('private_credentials', secure and bool(values.get('DHAN_CLIENT_ID')) and bool(values.get('DHAN_ACCESS_TOKEN')),
          'Provision private dhan/.env (chmod 600); renew Dhan Web token separately', required=args.require_read_only)
    for name in ['simple_ledger.csv', 'butterfly_reviews.json', 'tradelog.csv']:
        check('canonical_ledger:'+name, (data/'Trading/ledger'/name).is_file(),
              'Restore authoritative private ledger; never substitute repository trade-log or synthesize balances', required=args.require_read_only)
    check('read_only_mode', c['mode'] == 'read-only', 'Shadow mode intentionally disables broker capture', required=args.require_read_only)
    check('execution_disabled', values.get('DHAN_EXECUTION_ENABLED', 'false').lower() != 'true',
          'Set DHAN_EXECUTION_ENABLED=false in private .env before direct service use')
    check('browser_recovery', platform.system() == 'Darwin' and
          Path(values.get('DHAN_BROWSER_EXECUTABLE') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').is_file(),
          'Optional: macOS Chrome recovery; Linux/WSL requires a privately supplied Web token', required=False)
    check('github_cli', bool(shutil.which('gh')), 'Install/authenticate GitHub CLI for journal publication (not needed offline)', required=False)
    check('model_and_news_access', False, 'Configure a model provider and current-news tools in OpenClaw; authentication/capability calls are not part of offline doctor', required=False)
    if not args.probe_mcp:
        check('mcp_connection', False, 'Not probed: --probe-mcp checks local health only; broker identity needs a separate authorized read', required=False)
    if args.probe_mcp:
        ok = False
        try:
            with urllib.request.urlopen('http://127.0.0.1:3000/healthz', timeout=3) as response:
                ok = response.status == 200
        except (OSError, ValueError):
            pass
        check('local_mcp_health', ok, 'Local MCP not responding on loopback:3000; setup does not start it', required=args.require_read_only)
    return {'status': 'READY' if all(x['status'] != 'FAIL' for x in checks) else 'BLOCKED',
            'mode': c['mode'], 'checks': checks, 'broker_verified': False, 'trading_ready': False,
            'note': 'Installation checks only; no broker calls, token recovery, orders or ledger writes.'}


def package(args):
    output = Path(args.output).expanduser().resolve()
    files = set()
    for root in MANIFEST['package_roots']:
        files.update(source_files(SOURCE/root))
    files.update(SOURCE/p for p in MANIFEST['package_files'])
    allowed = []
    for p in sorted(files):
        rel = p.relative_to(SOURCE)
        require(not p.is_symlink(), 'Package source symlink forbidden')
        if p.name.startswith('.env') and p.name != '.env.example':
            continue
        if any(part in {'ledger', 'snapshots', 'market-outlook', 'trade-log', 'memory'} for part in rel.parts):
            continue
        if p.suffix in {'.log', '.pyc'} or p.name in {'.DS_Store', 'Thumbs.db'}:
            continue
        allowed.append(p)
    require(not output.exists(), 'Package already exists; choose another output path')
    output.parent.mkdir(parents=True, exist_ok=True)
    hashes = {str(p.relative_to(SOURCE)): digest(p.read_bytes()) for p in allowed}
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for p in allowed:
            archive.write(p, 'volarb-agent-kit/'+str(p.relative_to(SOURCE)))
        archive.writestr('volarb-agent-kit/SHA256SUMS.json', json_bytes(hashes))
    return {'status': 'PACKAGED', 'path': str(output), 'files': len(hashes), 'sha256': digest(output.read_bytes()),
            'private_state_included': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('setup', help='Prepare external workspace/data and install locked dependencies; starts nothing')
    p.add_argument('--data-dir', default=str(DEFAULT_DATA)); p.add_argument('--workspace')
    p.add_argument('--agent-id', default='volarb-dhandho'); p.add_argument('--profile', choices=MANIFEST['profiles'], default='dhandho')
    p.add_argument('--mode', choices=MANIFEST['modes'], default='shadow')
    p.add_argument('--python', default='python3.12'); p.add_argument('--dev', action='store_true')
    p.add_argument('--no-install', action='store_true', help='Prepare files only; diagnostics will flag missing dependencies')
    p.add_argument('--register-agent', action='store_true', help='Explicitly register new isolated agent; preserve existing agents; no channel bindings')
    p = sub.add_parser('doctor', help='Offline setup diagnostics; no broker authentication or calls')
    p.add_argument('--config', default=str(DEFAULT_DATA/'config.json'))
    p.add_argument('--require-read-only', action='store_true'); p.add_argument('--probe-mcp', action='store_true', help='Optionally check loopback /healthz only')
    p = sub.add_parser('run', help='Run an explicit local command with configured paths and execution disabled')
    p.add_argument('--config', default=str(DEFAULT_DATA/'config.json')); p.add_argument('argv', nargs=argparse.REMAINDER)
    p = sub.add_parser('package', help='Create reusable kit archive without private data or journals')
    p.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'run':
        argv = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
        require(argv, 'Provide a command after --')
        c = read_config(args.config)
        # This is an environment launcher, not a security sandbox for arbitrary commands.
        return subprocess.call(argv, cwd=SOURCE, env=runtime_env(c))
    result = {'setup': setup, 'doctor': doctor, 'package': package}[args.command](args)
    print(json.dumps(result, indent=2))
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error), 'trading_ready': False}))
        raise SystemExit(2)
