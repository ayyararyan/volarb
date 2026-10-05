const key = vid => Array.isArray(vid) ? vid.join(',') : '';
const modes = new Set(['PURE_AGENTIC', 'PURE_ALGORITHMIC', 'HYBRID']);
const nonempty = value => typeof value === 'string' && value.trim().length > 0;

// Decision metadata is separate from immutable identity registries.
export function validateDecisionModes(inventory, expectedEntities) {
  const errors = [];
  if (inventory.schema_version !== '1.0' || !Array.isArray(inventory.entries)) {
    return ['invalid decision-mode inventory schema'];
  }
  const expected = new Map(expectedEntities
    .filter(e => e.status !== 'retired' && e.kind !== 'edge')
    .map(e => [key(e.vid), e]));
  const seen = new Set();
  const counts = {};
  for (const entry of inventory.entries) {
    const id = key(entry.vid);
    if (seen.has(id)) errors.push(`duplicate decision-mode VID: ${id}`);
    seen.add(id);
    const entity = expected.get(id);
    if (!entity) {
      errors.push(`unknown, retired or out-of-scope decision-mode VID: ${id}`);
      continue;
    }
    if (entry.name !== entity.name || entry.kind !== entity.kind) errors.push(`decision-mode identity drift: ${id}`);
    if (!modes.has(entry.classification)) errors.push(`invalid decision mode: ${id}`);
    if (!nonempty(entry.rationale) || !nonempty(entry.authority_policy)) errors.push(`missing decision rationale or authority: ${id}`);
    const expectedRole = entity.kind === 'root' ? 'AGGREGATE'
      : entity.kind === 'data_contract' ? 'CONTRACT'
      : entity.kind === 'state' ? 'STATE'
      : ['interface', 'resource', 'scheduler'].includes(entity.kind) ? 'SUPPORTING_RUNTIME'
      : 'DECISION_OR_PROCESS';
    if (entry.role !== expectedRole) errors.push(`decision-mode role drift: ${id}`);
    if (['CONTRACT', 'STATE'].includes(expectedRole) && entry.classification !== 'PURE_ALGORITHMIC') {
      errors.push(`contract/state cannot acquire discretionary authority: ${id}`);
    }
    if (entry.classification === 'HYBRID') {
      for (const field of ['llm_may', 'code_must', 'invalid_or_unavailable']) {
        if (!nonempty(entry.hybrid_boundary?.[field])) errors.push(`missing hybrid ${field}: ${id}`);
      }
    }
    if (id === '5,0,8,1,2' && entry.classification !== 'PURE_ALGORITHMIC') {
      errors.push('Command Commit Guard must remain PURE_ALGORITHMIC');
    }
    counts[entry.classification] = (counts[entry.classification] ?? 0) + 1;
  }
  for (const id of expected.keys()) if (!seen.has(id)) errors.push(`unclassified active VID: ${id}`);
  if (inventory.summary?.active_non_edge_entities !== expected.size) errors.push('decision-mode coverage summary is stale');
  for (const mode of modes) {
    if ((inventory.summary?.by_classification?.[mode] ?? 0) !== (counts[mode] ?? 0)) errors.push(`decision-mode count is stale: ${mode}`);
  }
  return errors;
}
