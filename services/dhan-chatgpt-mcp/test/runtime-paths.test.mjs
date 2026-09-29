import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { runtimePaths, browserSettings } from '../src/runtime-paths.mjs';

test('portable state paths use data root, independent of working directory', () => {
  const p = runtimePaths({VOLARB_DATA_DIR:'/tmp/portable data'}, '/home/example');
  assert.equal(p.root, '/tmp/portable data/dhan');
  assert.equal(p.evidence, '/tmp/portable data/Trading/snapshots/dhan-workflow-private');
  assert.equal(runtimePaths({}, '/home/example').root, '/home/example/.local/share/volarb/dhan');
  assert.equal(runtimePaths({DHAN_RUNTIME_DIR:'/tmp/existing-mcp'}, '/home/example').root, '/tmp/existing-mcp');
});
test('browser recovery is explicitly macOS-specific and configurable', () => {
  assert.throws(() => browserSettings({}, 'linux'), /MACOS_ONLY/);
  const s=browserSettings({DHAN_PIN_FILE:'/private/pin.env',DHAN_BROWSER_PORT:'18902',DHAN_BROWSER_EXECUTABLE:'/custom/chrome'}, 'darwin');
  assert.equal(s.endpoint,'http://127.0.0.1:18902');
  assert.equal(s.chrome,'/custom/chrome');
  assert.equal(s.pinFile,'/private/pin.env');
  assert.throws(() => browserSettings({DHAN_BROWSER_PORT:'0'},'darwin'), /INVALID_BROWSER_PORT/);
});
test('shadow capture fails before authentication and never creates evidence', () => {
  const data=fs.mkdtempSync(path.join(os.tmpdir(),'volarb-shadow-'));
  try {
    assert.throws(() => execFileSync(process.execPath, ['src/workflow-data-cli.mjs','--scope','account'], {
      env:{...process.env,VOLARB_DATA_DIR:data,DHAN_RUNTIME_DIR:path.join(data,'dhan'),VOLARB_OBSERVE_ENABLED:'false'},
      encoding:'utf8'
    }), error => {
      const result=JSON.parse(error.stdout);
      assert.equal(result.code,'READ_ONLY_PROFILE_REQUIRED');
      assert.equal(result.orders_sent,false);
      return true;
    });
    assert.deepEqual(fs.readdirSync(data),[]);
  } finally {fs.rmSync(data,{recursive:true,force:true});}
});
