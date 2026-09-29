// Native office-Mac dialog. No phone/PIN values in argv, console or chat.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';
import fs from 'node:fs';
import { atomicPrivate, ROOT } from './web-token.mjs';
const script = 'text returned of (display dialog "Save your Dhan login mobile number on this Mac for automatic login. Your existing saved PIN will be used privately. Do not enter the PIN here." default answer "" with hidden answer buttons {"Cancel", "Save locally"} default button "Save locally" with title "Dhan local login setup")';
try {
  if (process.platform !== 'darwin') throw Error('MACOS_DIALOG_ONLY');
  fs.mkdirSync(path.join(ROOT, '.private'), { recursive: true, mode: 0o700 });
  const { stdout } = await promisify(execFile)('/usr/bin/osascript', ['-e', script], { timeout: 120000 });
  const mobileNumber = stdout.trim().replace(/^\+91[ -]?/, '').replace(/[ -]/g, '');
  if (!/^[6-9]\d{9}$/.test(mobileNumber)) throw Error('invalid');
  atomicPrivate(path.join(ROOT, '.private', 'dhan-login.json'), JSON.stringify({ mobileNumber }));
  console.log('Mac login number saved privately.');
} catch { console.log('Login setup not completed; browser mobile entry remains available.'); process.exitCode = 2; }
