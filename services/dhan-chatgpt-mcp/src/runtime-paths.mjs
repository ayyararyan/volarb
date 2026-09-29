// Source and private runtime are separate. No file/directory creation on import.
import os from 'node:os';
import path from 'node:path';
import dotenv from 'dotenv';

export function runtimePaths(env = process.env, home = os.homedir()) {
  const data = path.resolve(env.VOLARB_DATA_DIR || path.join(home, '.local', 'share', 'volarb'));
  const root = path.resolve(env.DHAN_RUNTIME_DIR || path.join(data, 'dhan'));
  return { data, root, envFile: path.join(root, '.env'),
    evidence: path.join(data, 'Trading', 'snapshots', 'dhan-workflow-private'),
    execution: path.join(root, '.private', 'execution') };
}
export const RUNTIME = runtimePaths();
// Only the designated private env file; never a random current-directory .env.
dotenv.config({ path: RUNTIME.envFile, quiet: true });

export function browserSettings(env = process.env, platform = process.platform) {
  if (platform !== 'darwin') throw new Error('BROWSER_RECOVERY_MACOS_ONLY_USE_MANUAL_WEB_TOKEN');
  const port = Number(env.DHAN_BROWSER_PORT || 18802);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('INVALID_BROWSER_PORT');
  return { chrome: env.DHAN_BROWSER_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    pinFile: env.DHAN_PIN_FILE || '', port, endpoint: `http://127.0.0.1:${port}` };
}
