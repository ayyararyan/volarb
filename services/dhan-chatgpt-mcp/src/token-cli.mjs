import { ensureToken, AuthError } from './web-token.mjs';
const args = process.argv.slice(2);
const known = new Set(['--check', '--recover', '--force-browser', '--session-end']);
try {
  for (let i = 0; i < args.length; i++) {
    if (!known.has(args[i])) throw new AuthError('UNKNOWN_OPTION');
    if (args[i] === '--session-end') {
      if (!args[i + 1] || args[i + 1].startsWith('--')) throw new AuthError('SESSION_END_VALUE_REQUIRED');
      i++;
    }
  }
  const i = args.indexOf('--session-end');
  const result = await ensureToken({ allowBrowser: args.includes('--recover'), forceBrowser: args.includes('--force-browser'), sessionUntil: i < 0 ? undefined : args[i + 1] });
  const { token, ...safe } = result;
  console.log(JSON.stringify(safe));
  process.exitCode = result.status === 'VALID' ? 0 : 2;
} catch (e) {
  console.log(JSON.stringify({ status: 'BLOCKED', reason: e instanceof AuthError ? e.code : 'AUTH_INTERNAL_ERROR' }));
  process.exitCode = 2;
}
