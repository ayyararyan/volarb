import test from 'node:test';
import assert from 'node:assert/strict';
import {
  makeBoundVid,
  makeMountIdentity,
  makeRuntimeIdentity,
  serializeCanonicalVid
} from './identity.mjs';

test('canonical identity is stable across mounts while bound identity changes', () => {
  const canonical = [5,0,8,1,2];

  const volarb = makeBoundVid({
    compositionId: 'composition.volarb',
    mountId: 'mount.volarb.execution.main',
    componentId: 'component.execution_engine',
    canonicalVid: canonical
  });

  const other = makeBoundVid({
    compositionId: 'composition.other',
    mountId: 'mount.other.execution.main',
    componentId: 'component.execution_engine',
    canonicalVid: canonical
  });

  assert.equal(volarb.canonical_id, other.canonical_id);
  assert.notEqual(volarb.bound_id, other.bound_id);
  assert.equal(
    volarb.canonical_id,
    serializeCanonicalVid('component.execution_engine', canonical)
  );
});

test('nested provider mount is identity-bearing without assigning a VID', () => {
  const mount = makeMountIdentity({
    compositionId: 'composition.volarb',
    mountId: 'mount.volarb.execution.main.broker.primary',
    componentId: 'provider.dhan',
    mountPath: 'execution.main/broker.primary',
    parentMountId: 'mount.volarb.execution.main'
  });

  assert.equal(mount.component_id, 'provider.dhan');
  assert.equal(mount.parent_mount_id, 'mount.volarb.execution.main');
  assert.equal('canonical_vid' in mount, false);
});

test('runtime identity references bound/canonical context without replacing it', () => {
  const bound = makeBoundVid({
    compositionId: 'composition.volarb',
    mountId: 'mount.volarb.execution.main',
    componentId: 'component.execution_engine',
    canonicalVid: [5,0,8,1,2]
  });

  const runtime = makeRuntimeIdentity({
    bound,
    intentId: 'intent-42',
    intentVersion: 3,
    sliceId: 'slice-1',
    actionId: 'action-9',
    correlationId: 'corr-9'
  });

  assert.equal(runtime.bound_id, bound.bound_id);
  assert.deepEqual(runtime.canonical_vid, [5,0,8,1,2]);
  assert.equal(runtime.intent_version, 3);
});
