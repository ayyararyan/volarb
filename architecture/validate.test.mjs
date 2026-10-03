import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const validator = path.join(root, 'architecture/validate.mjs');

function changedResult(t, relative, mutate) {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'volarb-architecture-test-'));
  t.after(() => fs.rmSync(fixture, { recursive: true, force: true }));
  fs.cpSync(path.join(root, 'architecture'), path.join(fixture, 'architecture'), { recursive: true });
  fs.mkdirSync(path.join(fixture, 'docs/workflows'), { recursive: true });
  fs.copyFileSync(path.join(root, 'docs/workflows/vector-id-registry.json'), path.join(fixture, 'docs/workflows/vector-id-registry.json'));
  // Provider sources are read-only path targets; mutations touch copied JSON only.
  fs.symlinkSync(path.join(root, 'services'), path.join(fixture, 'services'), 'dir');
  const target = path.join(fixture, relative);
  const data = JSON.parse(fs.readFileSync(target, 'utf8'));
  mutate(data);
  fs.writeFileSync(target, JSON.stringify(data));
  const result = spawnSync(process.execPath, [validator], { cwd: fixture, encoding: 'utf8' });
  assert.equal(result.status, 1, result.stdout + result.stderr);
  return result.stderr;
}

test('current architecture paths, ownership, versions and compatibility mirrors agree', () => {
  const result = spawnSync(process.execPath, [validator], { cwd: root, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
});

test('stale composition and provider mount versions are rejected', t => {
  assert.match(changedResult(t, 'architecture/registries/composition-registry.json', d => d.compositions[0].version = '0.0.0'), /catalog version mismatch/);
  assert.match(changedResult(t, 'architecture/strategies/volarb/composition.json', d => d.mounts[1].component_version = '0.0.0'), /mount version mismatch/);
});

test('both alias and assembled registry drift are rejected', t => {
  assert.match(changedResult(t, 'architecture/components/internal-execution/vector-id-registry.json', d => d.entities[0].name = 'Old name'), /alias registry entities drift/);
  assert.match(changedResult(t, 'docs/workflows/vector-id-registry.json', d => d.identity_model.canonical_component_registries = { 'component.internal_execution': 'old.json' }), /canonical ownership metadata is stale/);
  assert.match(changedResult(t, 'docs/workflows/vector-id-registry.json', d => d.entities.find(e => e.vid[0] === 5).note = 'stale'), /compatibility registry drift/);
});

test('broken provider implementation paths and port bindings are rejected', t => {
  assert.match(changedResult(t, 'architecture/providers/dhan/manifest.json', d => d.implementation.broker_port = 'services/missing-broker.mjs'), /missing or non-repository path/);
  assert.match(changedResult(t, 'architecture/strategies/volarb/composition.json', d => d.bindings[0].target.port_id = 'port.internal_execution.intent'), /inconsistent execution port binding/);
});

test('canonical namespace, strategy ownership and provider error identity cannot drift', t => {
  assert.match(changedResult(t, 'architecture/components/execution-engine/manifest.json', d => d.canonical_identity.canonical_root_vid = [6, 0, 0, 0, 0]), /canonical root changed/);
  assert.match(changedResult(t, 'architecture/strategies/volarb/composition.json', d => d.strategy_scope.strategy_owned_box_codes.push(5)), /Volarb must not own/);
  assert.match(changedResult(t, 'architecture/providers/dhan/manifest.json', d => d.error_contract.global_provider_error_vid = [5, 0, 1, 7, 1]), /global Provider Error Envelope/);
});
