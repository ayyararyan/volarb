"""Installer tests use temporary workspaces; no OpenClaw registration or broker calls."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('volarb_kit', ROOT/'tools/volarb.py')
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='volarb-kit-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.args = argparse.Namespace(data_dir=str(self.base/'private data'), workspace=str(self.base/'workspace'),
            agent_id='test-agent', profile='dhandho', mode='shadow', register_agent=False,
            no_install=True, dev=False, python='python3.12')

    def install(self):
        with patch.object(kit, 'command', side_effect=AssertionError('No external commands during files-only setup')):
            return kit.setup(self.args)

    def test_repeatable_preserves_private_and_personal_files(self):
        result = self.install()
        data = Path(self.args.data_dir); workspace = Path(self.args.workspace)
        (data/'dhan/.env').write_text('DHAN_CLIENT_ID=synthetic\nPRIVATE_SENTINEL=not-a-real-secret\n')
        (workspace/'SOUL.md').write_text('Personal edits must survive\n')
        before = {p: p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        self.install()
        self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))
        self.assertFalse((data/'Trading/ledger').exists())
        self.assertFalse(result['services_started'])
        self.assertFalse(result['trading_ready'])
        self.assertEqual((data/'dhan/.env').stat().st_mode & 0o777, 0o600)
        for skill in kit.MANIFEST['skills']:
            self.assertTrue((workspace/'skills'/skill/'SKILL.md').is_file())

    def test_skill_conflict_refuses_without_overwrite(self):
        self.install()
        skill = Path(self.args.workspace)/'skills/butterfly-market-outlook/SKILL.md'
        skill.write_text('local custom skill\n')
        with self.assertRaisesRegex(ValueError, 'Existing file differs'):
            self.install()
        self.assertEqual(skill.read_text(), 'local custom skill\n')

    def test_symlink_cannot_redirect_install(self):
        workspace = Path(self.args.workspace); workspace.mkdir()
        outside = self.base/'outside'; outside.mkdir()
        (workspace/'skills').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(Path(self.args.data_dir).exists())

    def test_no_state_inside_source(self):
        self.args.data_dir = str(ROOT/'private-fixture-must-not-create')
        with self.assertRaisesRegex(ValueError, 'outside the source'):
            self.install()
        self.assertFalse(Path(self.args.data_dir).exists())

    def test_config_conflict_detected_before_writes(self):
        self.install()
        self.args.mode = 'read-only'
        with self.assertRaisesRegex(ValueError, 'Existing file differs'):
            self.install()
        saved = json.loads((Path(self.args.data_dir)/'config.json').read_text())
        self.assertEqual(saved['mode'], 'shadow')

    def test_readonly_environment_cannot_inherit_live_flags(self):
        self.install()
        config = kit.read_config(Path(self.args.data_dir)/'config.json')
        with patch.dict(os.environ, {'DHAN_EXECUTION_ENABLED':'true', 'DHAN_BROWSER_RECOVERY_ENABLED':'true'}):
            env = kit.runtime_env(config)
        self.assertEqual(env['DHAN_EXECUTION_ENABLED'], 'false')
        self.assertEqual(env['DHAN_BROWSER_RECOVERY_ENABLED'], 'false')
        self.assertEqual(env['VOLARB_OBSERVE_ENABLED'], 'false')
        self.assertEqual(env['VOLARB_DATA_DIR'], self.args.data_dir)
        config['mode'] = 'read-only'
        self.assertEqual(kit.runtime_env(config)['VOLARB_OBSERVE_ENABLED'], 'true')

    def test_accounting_and_node_paths_agree_after_relocation(self):
        self.install()
        env = kit.runtime_env(kit.read_config(Path(self.args.data_dir)/'config.json'))
        py = subprocess.check_output([sys.executable, '-B', '-c',
            "import volarb_paths as p, review_scorecard as r, simple_ledger as s, trade_ledger as t; "
            "assert r.ROOT==s.EXPECTED_ROOT==p.TRADING_ROOT; "
            "assert t.DEFAULT_LEDGER.parent==p.TRADING_ROOT/'ledger'; print(p.EVIDENCE_ROOT)"],
            cwd=ROOT/'services/day-workflow', env=env, text=True).strip()
        node = subprocess.check_output(['node', '--input-type=module', '-e',
            "import {runtimePaths} from './services/dhan-chatgpt-mcp/src/runtime-paths.mjs'; console.log(runtimePaths().evidence)"],
            cwd=ROOT, env=env, text=True).strip()
        self.assertEqual(py, node)
        self.assertTrue(py.startswith(self.args.data_dir))
        self.assertFalse((Path(self.args.data_dir)/'Trading/ledger').exists())

    def test_registration_refuses_existing_agent_elsewhere(self):
        with patch.object(kit.shutil, 'which', return_value='/synthetic/openclaw'), \
             patch.object(kit, 'version', return_value='OpenClaw 2026.9.5'), \
             patch.object(kit, 'command', return_value=json.dumps([{'id':'test-agent','workspace':'/unrelated'}])):
            with self.assertRaisesRegex(ValueError, 'Existing agent points elsewhere'):
                kit.registration_state('test-agent', Path(self.args.workspace))

    def test_registration_uses_supported_cli_and_verifies_skills(self):
        self.args.register_agent = True
        def response(argv, **kwargs):
            if argv[1:3] == ['agents', 'list']: return '[]'
            if argv[1:3] == ['agents', 'add']: return '{}'
            if argv[1:3] == ['skills', 'list']:
                return json.dumps({'skills':[{'name':s,'eligible':True} for s in kit.MANIFEST['skills']]})
            self.fail('Unexpected external command')
        with patch.object(kit.shutil,'which',return_value='/synthetic/openclaw'), \
             patch.object(kit,'version',return_value='OpenClaw 2026.9.5'), \
             patch.object(kit,'command',side_effect=response) as calls:
            result=kit.setup(self.args)
        self.assertTrue(result['agent_registered'])
        self.assertFalse(any('--bind' in call.args[0] for call in calls.call_args_list))

    def test_missing_credentials_and_ledgers_fail_readiness_without_leaking(self):
        self.install()
        args = argparse.Namespace(config=str(Path(self.args.data_dir)/'config.json'), require_read_only=True, probe_mcp=False)
        with patch.object(kit,'registration_state',side_effect=ValueError('not registered')):
            result=kit.doctor(args)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertFalse(result['broker_verified'])
        self.assertFalse(result['trading_ready'])
        self.assertIn('private_credentials', [c['name'] for c in result['checks'] if c['status']=='FAIL'])

    def test_package_excludes_private_artifacts(self):
        src=self.base/'source';src.mkdir()
        # Small controlled source fixture with the real packaging rules.
        for rel in kit.MANIFEST['package_files']:
            p=src/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture\n')
        for root in kit.MANIFEST['package_roots']:
            p=src/root;p.mkdir(parents=True,exist_ok=True);(p/'fixture.py').write_text('# safe\n')
        for rel in ['services/dhan/.env','services/dhan/.private/token.json',
                    'services/day-workflow/ledger/tradelog.csv','services/day-workflow/snapshots/raw.json',
                    'agent-kit/memory/MEMORY.md','services/dhan/node_modules/private.js']:
            p=src/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('PRIVATE_SENTINEL')
        output=self.base/'kit.zip'
        with patch.object(kit,'SOURCE',src):
            kit.package(argparse.Namespace(output=str(output)))
        with zipfile.ZipFile(output) as z:
            for name in z.namelist():self.assertNotIn(b'PRIVATE_SENTINEL',z.read(name))
            hashes=json.loads(z.read('volarb-agent-kit/SHA256SUMS.json'))
            for rel,sha in hashes.items():self.assertEqual(kit.digest(z.read('volarb-agent-kit/'+rel)),sha)


if __name__ == '__main__':unittest.main()
