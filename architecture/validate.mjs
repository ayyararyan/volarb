import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { validateDecisionModes } from './lib/decision-modes.mjs';

const root = process.cwd();
const readJson = p => JSON.parse(fs.readFileSync(path.join(root, p), 'utf8'));
const key = vid => vid.join(',');

const componentCatalog = readJson('architecture/registries/component-registry.json');
const compositionCatalog = readJson('architecture/registries/composition-registry.json');
const executionManifest = readJson('architecture/components/execution-engine/manifest.json');
const executionRegistry = readJson('architecture/components/execution-engine/vector-id-registry.json');
const legacyExecutionAlias = readJson('architecture/components/internal-execution/manifest.json');
const aliasRegistry = readJson('architecture/components/internal-execution/vector-id-registry.json');
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

if (legacyExecutionAlias.alias_of !== 'component.execution_engine' || legacyExecutionAlias.status !== 'legacy_alias') fail('Internal Execution legacy alias is invalid');

const canonicalRegistryPath = 'architecture/components/execution-engine/vector-id-registry.json';
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const requirePath = (value, label) => {
  if (typeof value !== 'string' || path.isAbsolute(value) || value.split(/[\\/]/).includes('..') || !fs.existsSync(path.join(root, value))) {
    fail(`${label} references missing or non-repository path: ${value}`);
  }
};
if (executionManifest.component_id !== 'component.execution_engine' || executionRegistry.component_id !== 'component.execution_engine' || executionRegistry.registry_role !== 'canonical_component_registry') fail('Execution Engine canonical component ownership changed');
if (executionManifest.ownership !== 'strategy_agnostic' || dhanManifest.ownership !== 'strategy_agnostic') fail('Execution Engine and Dhan must remain strategy-agnostic');
if (legacyExecutionAlias.canonical_manifest !== 'architecture/components/execution-engine/manifest.json' || legacyExecutionAlias.canonical_registry !== canonicalRegistryPath || executionManifest.canonical_identity.registry !== canonicalRegistryPath) fail('canonical execution manifest/registry pointer drift');
if (aliasRegistry.alias_of !== 'component.execution_engine' || aliasRegistry.registry_role !== 'legacy_alias_mirror' || aliasRegistry.canonical_registry !== canonicalRegistryPath || !equal(aliasRegistry.entities, executionRegistry.entities)) fail('legacy alias registry entities drift from canonical registry');

unique(componentCatalog.components.map(x => x.component_id), 'component_id');
unique(compositionCatalog.compositions.map(x => x.composition_id), 'composition_id');
unique(volarb.mounts.map(x => x.mount_id), 'mount_id');
unique(volarb.bindings.map(x => x.binding_id), 'binding_id');
unique(executionRegistry.entities.map(x => key(x.vid)), 'canonical execution VID');
unique(legacy.entities.map(x => key(x.vid)), 'assembled VID');

if (key(executionManifest.canonical_identity.canonical_root_vid) !== '5,0,0,0,0' || key(executionRegistry.canonical_root_vid) !== '5,0,0,0,0' || key(aliasRegistry.canonical_root_vid) !== '5,0,0,0,0' || executionManifest.canonical_identity.immutable_existing_vids !== true) {
  fail('Execution Engine canonical root changed');
}

for (const entity of executionRegistry.entities) {
  if (!Array.isArray(entity.vid) || entity.vid.length !== 5 || !entity.vid.every(x => Number.isInteger(x) && x >= 0) || entity.vid[0] !== 5 || entity.vid[1] !== 0) {
    fail(`non-[5,0,...] entity in canonical Execution Engine registry: ${JSON.stringify(entity.vid)}`);
  }
  if (entity.canonical_component_id !== 'component.execution_engine' || entity.identity_scope !== 'canonical') {
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
  else if (!equal(mirror, entity)) {
    fail(`compatibility registry drift at ${key(entity.vid)}`);
  }
}

if (legacy.identity_model.canonical_component_registries['component.execution_engine'] !== canonicalRegistryPath || Object.hasOwn(legacy.identity_model.canonical_component_registries, 'component.internal_execution') || !legacy.rules.canonical_component_ownership.includes('component.execution_engine') || legacy.schema.box_codes['5'] !== 'execution_engine_canonical_component_namespace') fail('assembled registry canonical ownership metadata is stale');

const manifests = new Map();
for (const entry of componentCatalog.components) {
  requirePath(entry.manifest, entry.component_id);
  const manifest = readJson(entry.manifest);
  manifests.set(entry.component_id, manifest);
  if (manifest.component_id !== entry.component_id) fail(`component catalog identity mismatch: ${entry.component_id}`);
  if (entry.canonical_registry) {
    requirePath(entry.canonical_registry, entry.component_id);
    if (entry.canonical_registry !== manifest.canonical_identity.registry) fail(`component catalog registry mismatch: ${entry.component_id}`);
  }
  for (const implementationPath of Object.values(manifest.implementation ?? {})) requirePath(implementationPath, entry.component_id);
}
for (const entry of compositionCatalog.compositions) {
  requirePath(entry.definition, entry.composition_id);
  const definition = readJson(entry.definition);
  for (const field of ['composition_id', 'strategy_id', 'version']) {
    if (entry[field] !== definition[field]) fail(`composition catalog ${field} mismatch: ${entry.composition_id}`);
  }
}
requirePath(volarb.strategy_scope.legacy_registry, 'Volarb strategy registry');
if (volarb.strategy_scope.strategy_owned_box_codes.includes(5) || !volarb.strategy_scope.excluded_reusable_namespace_codes.includes(5)) fail('Volarb must not own execution namespace 5');

for (const [inventoryPath, entities] of [
  [executionManifest.decision_modes, executionRegistry.entities],
  [volarb.decision_modes, legacy.entities.filter(e => e.vid[0] !== 5)]
]) {
  requirePath(inventoryPath, 'decision-mode inventory');
  if (typeof inventoryPath === 'string' && fs.existsSync(path.join(root, inventoryPath))) {
    for (const error of validateDecisionModes(readJson(inventoryPath), entities)) fail(error);
  }
}

const componentIds = new Set(componentCatalog.components.map(x => x.component_id));
for (const mount of volarb.mounts) {
  if (!componentIds.has(mount.component_id)) fail(`mount references unknown component: ${mount.component_id}`);
  const manifest = manifests.get(mount.component_id);
  if (manifest && mount.component_version !== manifest.version) fail(`mount version mismatch: ${mount.mount_id}`);
  if (manifest && mount.canonical_root_vid && !equal(mount.canonical_root_vid, manifest.canonical_identity.canonical_root_vid)) fail(`mount canonical root mismatch: ${mount.mount_id}`);
}
const mountIds = new Set(volarb.mounts.map(x => x.mount_id));
const canonicalVids = new Set(executionRegistry.entities.map(x => key(x.vid)));
for (const mount of volarb.mounts) {
  if (mount.parent_mount_id && !mountIds.has(mount.parent_mount_id)) fail(`unknown parent mount: ${mount.parent_mount_id}`);
}
for (const entity of executionRegistry.entities) {
  for (const field of ['parent_vid', 'source_vid', 'target_vid']) {
    if (entity[field] && !canonicalVids.has(key(entity[field]))) fail(`${key(entity.vid)} references unknown ${field}: ${key(entity[field])}`);
  }
}
const ports = new Map([...executionManifest.boundary_ports, ...executionManifest.extension_ports].map(x => [x.port_id, x]));
for (const port of ports.values()) {
  const entity = executionRegistry.entities.find(x => key(x.vid) === key(port.canonical_vid));
  if (!entity || entity.status === 'retired') fail(`port references missing or retired canonical VID: ${port.port_id}`);
}

for (const binding of volarb.bindings) {
  for (const endpointName of ['source','target','consumer','provider']) {
    const endpoint = binding[endpointName];
    if (!endpoint) continue;
    if (endpoint.mount_id && !mountIds.has(endpoint.mount_id)) {
      fail(`${binding.binding_id} references unknown mount ${endpoint.mount_id}`);
    }
    if (endpoint.canonical_vid && !canonicalVids.has(key(endpoint.canonical_vid))) {
      fail(`${binding.binding_id} references unknown Execution Engine canonical VID ${key(endpoint.canonical_vid)}`);
    }
    if (endpoint.scope === 'strategy_local' && (!legacy.entities.some(x => key(x.vid) === key(endpoint.vid)) || endpoint.vid[0] === 5)) fail(`${binding.binding_id} references invalid strategy-local VID`);
    const mount = volarb.mounts.find(x => x.mount_id === endpoint.mount_id);
    if (endpoint.port_id) {
      const port = ports.get(endpoint.port_id);
      if (!port || !equal(port.canonical_vid, endpoint.canonical_vid) || mount?.component_id !== 'component.execution_engine') fail(`${binding.binding_id} has inconsistent execution port binding`);
    }
    if (endpoint.interface_id) {
      const provider = manifests.get(mount?.component_id);
      const contract = provider?.interfaces?.find(x => x.interface_id === endpoint.interface_id);
      if (!contract || endpoint.component_id !== mount?.component_id || contract.implements !== binding.consumer?.port_id) fail(`${binding.binding_id} has inconsistent provider implementation binding`);
    }
  }
}

if (dhanManifest.canonical_identity.vector_id !== null) {
  fail('Dhan must not receive a canonical Volarb VID');
}
if (!equal(dhanManifest.error_contract.global_provider_error_vid, [0, 0, 1, 7, 1])) fail('Dhan must use the global Provider Error Envelope');

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
