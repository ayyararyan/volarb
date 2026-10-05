import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { validateDecisionModes } from './decision-modes.mjs';

const read = relative => JSON.parse(fs.readFileSync(new URL(relative, import.meta.url), 'utf8'));
const engine = read('../components/execution-engine/decision-modes.json');
const strategy = read('../strategies/volarb/decision-modes.json');
const engineEntities = read('../components/execution-engine/vector-id-registry.json').entities;
const strategyEntities = read('../../docs/workflows/vector-id-registry.json').entities.filter(e => e.vid[0] !== 5);

test('every active entity has exactly one decision with an explicit authority boundary', () => {
  assert.deepEqual(validateDecisionModes(engine, engineEntities), []);
  assert.deepEqual(validateDecisionModes(strategy, strategyEntities), []);
});

test('missing, duplicate and retired entries cannot silently pass coverage', () => {
  const missing = structuredClone(engine);
  missing.entries.pop();
  assert.match(validateDecisionModes(missing, engineEntities).join('\n'), /unclassified active VID/);
  const duplicate = structuredClone(engine);
  duplicate.entries.push(structuredClone(duplicate.entries[0]));
  assert.match(validateDecisionModes(duplicate, engineEntities).join('\n'), /duplicate decision-mode VID/);
  const retired = structuredClone(engine);
  retired.entries.push({ vid: [5,0,2,1,1] });
  assert.match(validateDecisionModes(retired, engineEntities).join('\n'), /retired or out-of-scope/);
});

test('hybrid decisions require code authority and invalid-output behavior', () => {
  for (const field of ['code_must', 'invalid_or_unavailable']) {
    const bad = structuredClone(strategy);
    delete bad.entries.find(e => e.classification === 'HYBRID').hybrid_boundary[field];
    assert.match(validateDecisionModes(bad, strategyEntities).join('\n'), new RegExp(`missing hybrid ${field}`));
  }
});

test('the guard and supporting state cannot acquire LLM decision authority', () => {
  const guard = structuredClone(engine);
  guard.entries.find(e => e.vid.join(',') === '5,0,8,1,2').classification = 'PURE_AGENTIC';
  assert.match(validateDecisionModes(guard, engineEntities).join('\n'), /Command Commit Guard must remain PURE_ALGORITHMIC/);
  const state = structuredClone(engine);
  state.entries.find(e => e.kind === 'state').classification = 'PURE_AGENTIC';
  assert.match(validateDecisionModes(state, engineEntities).join('\n'), /contract\/state cannot acquire discretionary authority/);
});
