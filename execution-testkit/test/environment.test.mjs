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

test('production engine and provider source dependencies never import execution-testkit',()=>{
  function sourceFiles(directory){
    return fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>{
      const target=path.join(directory,entry.name);
      return entry.isDirectory()?sourceFiles(target):/\.(?:mjs|cjs|js|ts)$/.test(entry.name)?[target]:[];
    });
  }
  const importsTestkit=/(?:\bfrom\s*|\bimport\s*(?:\(\s*)?|\brequire\s*\(\s*)['"][^'"]*execution-testkit(?:\/|['"])/;
  for(const directory of ['execution-engine','services/dhan-chatgpt-mcp/src']){
    for(const file of sourceFiles(path.join(root,directory))){
      assert.doesNotMatch(fs.readFileSync(file,'utf8'),importsTestkit,path.relative(root,file));
    }
  }
});
