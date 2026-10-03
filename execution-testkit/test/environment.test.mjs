import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root=process.cwd();
const read=name=>JSON.parse(fs.readFileSync(path.join(root,'environments/execution',name+'.json'),'utf8'));

test('execution environments are explicit and production cannot mount testkit dependencies',()=>{
  const testEnv=read('test'),replay=read('replay'),shadow=read('shadow'),production=read('production');
  assert.equal(testEnv.mutation_target,'simulated_only');
  assert.equal(replay.clock,'virtual');
  assert.equal(shadow.live_broker_mutations,false);
  assert.equal(production.live_broker_mutations,true);
  assert.equal(production.allow_execution_testkit,false);
  const serialized=JSON.stringify(production);
  assert.doesNotMatch(serialized,/simulated|execution-testkit|virtual/i);
});

test('all non-production environments fail closed for real broker mutations',()=>{
  for(const name of ['test','replay','shadow']){
    const env=read(name);
    assert.equal(env.live_broker_mutations,false,name);
  }
});
