const VID_LENGTH = 5;

function requireString(value, name) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new TypeError(`${name} must be a non-empty string`);
  }
  return value;
}

export function assertCanonicalVid(vid) {
  if (!Array.isArray(vid) || vid.length !== VID_LENGTH || !vid.every(Number.isInteger)) {
    throw new TypeError('canonicalVid must be a five-integer array');
  }
  return Object.freeze([...vid]);
}

export function serializeCanonicalVid(componentId, canonicalVid) {
  requireString(componentId, 'componentId');
  const vid = assertCanonicalVid(canonicalVid);
  return `cvid://${encodeURIComponent(componentId)}/${vid.join('.')}`;
}

export function makeBoundVid({ compositionId, mountId, componentId, canonicalVid }) {
  requireString(compositionId, 'compositionId');
  requireString(mountId, 'mountId');
  requireString(componentId, 'componentId');
  const vid = assertCanonicalVid(canonicalVid);

  return Object.freeze({
    identity_scope: 'bound',
    composition_id: compositionId,
    mount_id: mountId,
    canonical_component_id: componentId,
    canonical_vid: vid,
    canonical_id: serializeCanonicalVid(componentId, vid),
    bound_id: `bvid://${encodeURIComponent(compositionId)}/${encodeURIComponent(mountId)}/${vid.join('.')}`
  });
}

export function makeMountIdentity({ compositionId, mountId, componentId, mountPath, parentMountId = null }) {
  requireString(compositionId, 'compositionId');
  requireString(mountId, 'mountId');
  requireString(componentId, 'componentId');
  requireString(mountPath, 'mountPath');
  if (parentMountId !== null) requireString(parentMountId, 'parentMountId');

  return Object.freeze({
    identity_scope: 'mount',
    composition_id: compositionId,
    mount_id: mountId,
    component_id: componentId,
    mount_path: mountPath,
    parent_mount_id: parentMountId
  });
}

export function makeRuntimeIdentity({
  bound,
  intentId = null,
  intentVersion = null,
  sliceId = null,
  actionId = null,
  correlationId = null
}) {
  if (!bound || bound.identity_scope !== 'bound') {
    throw new TypeError('bound must be a Bound VID created by makeBoundVid');
  }
  if (intentVersion !== null && !Number.isInteger(intentVersion)) {
    throw new TypeError('intentVersion must be an integer or null');
  }

  return Object.freeze({
    identity_scope: 'runtime',
    composition_id: bound.composition_id,
    mount_id: bound.mount_id,
    canonical_component_id: bound.canonical_component_id,
    canonical_vid: bound.canonical_vid,
    bound_id: bound.bound_id,
    intent_id: intentId,
    intent_version: intentVersion,
    slice_id: sliceId,
    action_id: actionId,
    correlation_id: correlationId
  });
}
