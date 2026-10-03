import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const root = process.cwd();
const readJson = p => JSON.parse(fs.readFileSync(path.join(root, p), 'utf8'));
const key = vid => vid.join(',');

const componentCatalog = readJson('architecture/registries/component-registry.json');
const compositionCatalog = readJson('architecture/registries/composition-registry.json');
const executionManifest = readJson('architecture/components/internal-execution/manifest.json');
const executionRegistry = readJson('architecture/components/internal-execution/vector-id-registry.json');
const dhanManifest = readJson('architecture/providers/dhan/manifest.json');
const volarb = readJson('architecture/strategies/volarb/composition.json');
const legacy = readJson('docs/workflows/vector-id-registry.json');

const fail = message => {
  console.error(`architecture validation failed: ${message}`);
  process.exitCode = 1;
};

const unique = (values, label) => {
  const seen = new Set();
  for (const value of values) {
    if (seen.has(value)) fail(`duplicate ${label}: ${value}`);
    seen.add(value);
  }
};

unique(componentCatalog.components.map(x => x.component_id), 'component_id');
unique(compositionCatalog.compositions.map(x => x.composition_id), 'composition_id');
unique(volarb.mounts.map(x => x.mount_id), 'mount_id');
unique(volarb.bindings.map(x => x.binding_id), 'binding_id');
unique(executionRegistry.entities.map(x => key(x.vid)), 'canonical execution VID');

if (key(executionManifest.canonical_identity.canonical_root_vid) !== '5,0,0,0,0') {
  fail('Internal Execution canonical root changed');
}

for (const entity of executionRegistry.entities) {
  if (!Array.isArray(entity.vid) || entity.vid.length !== 5 || entity.vid[0] !== 5) {
    fail(`non-[5,...] entity in canonical Internal Execution registry: ${JSON.stringify(entity.vid)}`);
  }
  if (entity.canonical_component_id !== 'component.internal_execution') {
    fail(`missing canonical component ownership on ${key(entity.vid)}`);
  }
}

const legacyExecution = new Map(
  legacy.entities.filter(x => Array.isArray(x.vid) && x.vid[0] === 5).map(x => [key(x.vid), x])
);
if (legacyExecution.size !== executionRegistry.entities.length) {
  fail(`legacy/canonical execution entity count mismatch: ${legacyExecution.size} vs ${executionRegistry.entities.length}`);
}
for (const entity of executionRegistry.entities) {
  const mirror = legacyExecution.get(key(entity.vid));
  if (!mirror) fail(`canonical execution VID absent from compatibility registry: ${key(entity.vid)}`);
  else if (mirror.name !== entity.name || mirror.kind !== entity.kind) {
    fail(`compatibility registry drift at ${key(entity.vid)}`);
  }
}

const componentIds = new Set(componentCatalog.components.map(x => x.component_id));
for (const mount of volarb.mounts) {
  if (!componentIds.has(mount.component_id)) fail(`mount references unknown component: ${mount.component_id}`);
}
const mountIds = new Set(volarb.mounts.map(x => x.mount_id));
const canonicalVids = new Set(executionRegistry.entities.map(x => key(x.vid)));

for (const binding of volarb.bindings) {
  for (const endpointName of ['source','target','consumer','provider']) {
    const endpoint = binding[endpointName];
    if (!endpoint) continue;
    if (endpoint.mount_id && !mountIds.has(endpoint.mount_id)) {
      fail(`${binding.binding_id} references unknown mount ${endpoint.mount_id}`);
    }
    if (endpoint.canonical_vid && !canonicalVids.has(key(endpoint.canonical_vid))) {
      fail(`${binding.binding_id} references unknown Internal Execution canonical VID ${key(endpoint.canonical_vid)}`);
    }
  }
}

if (dhanManifest.canonical_identity.vector_id !== null) {
  fail('Dhan must not receive a canonical Volarb VID');
}

const expectedLegacyBindings = new Map([
  ['0,0,5,4,1','binding.volarb.position-management-to-execution.intent'],
  ['0,0,4,4,1','binding.volarb.execution-to-position-management.facts'],
  ['0,0,6,4,1','binding.volarb.position-management-to-execution.interrupt']
]);

for (const [edgeVid, bindingId] of expectedLegacyBindings) {
  const edge = legacy.entities.find(x => Array.isArray(x.vid) && key(x.vid) === edgeVid);
  if (!edge) fail(`missing legacy composition edge ${edgeVid}`);
  else if (edge.binding_id !== bindingId || edge.identity_scope !== 'composition_binding') {
    fail(`legacy edge ${edgeVid} is not mapped to ${bindingId}`);
  }
}

if (!process.exitCode) {
  console.log(`architecture validation passed: ${executionRegistry.entities.length} canonical execution entities, ${volarb.mounts.length} mounts, ${volarb.bindings.length} bindings`);
}
