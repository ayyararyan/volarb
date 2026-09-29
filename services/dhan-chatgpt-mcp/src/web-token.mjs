import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import dotenv from 'dotenv';

import { RUNTIME } from './runtime-paths.mjs';
export const ROOT = RUNTIME.root;
export class AuthError extends Error {
  constructor(code) { super(code); this.name = 'AuthError'; this.code = code; }
}
export function privateRead(file) {
  const s = fs.lstatSync(file);
  if (!s.isFile() || s.isSymbolicLink() || (s.mode & 0o077) || s.uid !== process.getuid()) throw new AuthError('PRIVATE_FILE_PERMISSIONS_REQUIRED');
  return fs.readFileSync(file, 'utf8');
}
export function atomicPrivate(file, text, expected) {
  if (expected !== undefined && privateRead(file) !== expected) throw new AuthError('ENV_CHANGED_RETRY_REQUIRED');
  const tmp = `${file}.${randomUUID()}.tmp`;
  try {
    const fd = fs.openSync(tmp, 'wx', 0o600);
    try { fs.writeFileSync(fd, text); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    if (expected !== undefined && privateRead(file) !== expected) throw new AuthError('ENV_CHANGED_RETRY_REQUIRED');
    fs.renameSync(tmp, file);
    if (privateRead(file) !== text) throw new AuthError('PRIVATE_WRITE_VERIFY_FAILED');
  } finally { if (fs.existsSync(tmp)) fs.unlinkSync(tmp); }
}
export function mergeEnv(original, changes) {
  const seen = new Set();
  const lines = original.split('\n').flatMap(line => {
    const key = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=/)?.[1];
    if (!Object.hasOwn(changes, key)) return [line];
    if (seen.has(key)) return [];
    seen.add(key); return [`${key}=${changes[key]}`];
  });
  for (const [key, value] of Object.entries(changes)) if (!seen.has(key)) lines.push(`${key}=${value}`);
  return lines.join('\n').replace(/\n*$/, '\n');
}
export function claims(token) {
  try {
    if (!/^[\w-]+\.[\w-]+\.[\w-]+$/.test(token)) throw 0;
    const c = JSON.parse(Buffer.from(token.split('.')[1], 'base64url'));
    if (!Number.isFinite(c.exp) || !c.dhanClientId) throw 0;
    return c;
  } catch { throw new AuthError('MALFORMED_TOKEN'); }
}
// NSE/BSE regular-session authentication horizon, not the strategy's 15:00 exit.
// Outside today's session, require five minutes from now; do not guess holidays/next session.
export function sessionEnd(now = Date.now(), explicit) {
  if (explicit) {
    if (!/(Z|[+-]\d\d:\d\d)$/.test(explicit)) throw new AuthError('SESSION_END_TIMEZONE_REQUIRED');
    const n = Date.parse(explicit);
    if (!Number.isFinite(n) || n <= now) throw new AuthError('SESSION_END_MUST_BE_FUTURE');
    return n;
  }
  const day = new Date(now + 330 * 60000).toISOString().slice(0, 10);
  return Math.max(Date.parse(`${day}T15:30:00+05:30`), now + 5 * 60000);
}
export function needsRecovery(token, clientId, until, now = Date.now()) {
  if (!token) return 'MISSING_TOKEN';
  let c; try { c = claims(token); } catch { return 'MALFORMED_TOKEN'; }
  if (String(c.dhanClientId) !== String(clientId)) throw new AuthError('ACCOUNT_MISMATCH');
  if (c.exp * 1000 <= now) return 'EXPIRED_TOKEN';
  return c.exp * 1000 <= until + 5 * 60000 ? 'EXPIRES_BEFORE_SESSION_END' : null;
}
export async function verifyProfile(token, clientId, fetchFn = fetch) {
  let r;
  try { r = await fetchFn('https://api.dhan.co/v2/profile', {
    headers: { 'access-token': token, 'client-id': clientId }, signal: AbortSignal.timeout(15000), redirect: 'error'
  }); } catch { throw new AuthError('PROFILE_NETWORK_UNVERIFIED'); }
  if (r.status === 401) throw new AuthError('TOKEN_REJECTED');
  if (!r.ok) throw new AuthError(`PROFILE_HTTP_${r.status}`);
  let d; try { d = await r.json(); } catch { throw new AuthError('PROFILE_RESPONSE_INVALID'); }
  if (String(d?.dhanClientId) !== String(clientId)) throw new AuthError('ACCOUNT_MISMATCH');
  return true;
}
function lock(dir) {
  const file = path.join(dir, 'token-recovery.lock');
  try { fs.mkdirSync(file, { mode: 0o700 }); }
  catch (e) { if (e.code === 'EEXIST') throw new AuthError('TOKEN_RECOVERY_BUSY'); throw e; }
  // Never automatically steal an ambiguous lock. A terminated runner needs local inspection.
  fs.writeFileSync(path.join(file, 'owner'), `${process.pid}\n`, { mode: 0o600 });
  return () => { fs.unlinkSync(path.join(file, 'owner')); fs.rmdirSync(file); };
}
let flight;
let cache;
export function invalidateTokenCache() { cache = undefined; }
export async function ensureToken(options = {}) {
  if (flight) return flight;
  flight = ensure(options).finally(() => { flight = undefined; });
  return flight;
}
async function ensure({ root = ROOT, allowBrowser = false, forceBrowser = false, sessionUntil, fetchFn = fetch, recover, cleanup, now = Date.now() } = {}) {
  const envFile = path.join(root, '.env');
  const until = sessionEnd(now, sessionUntil);
  const original = privateRead(envFile), env = dotenv.parse(original);
  if (!env.DHAN_CLIENT_ID) throw new AuthError('CLIENT_ID_MISSING');
  let reason = needsRecovery(env.DHAN_ACCESS_TOKEN, env.DHAN_CLIENT_ID, until, now);
  if (!reason && !forceBrowser) {
    if (!(cache?.token === env.DHAN_ACCESS_TOKEN && now - cache.at < 60000)) {
      try { await verifyProfile(env.DHAN_ACCESS_TOKEN, env.DHAN_CLIENT_ID, fetchFn); cache = { token: env.DHAN_ACCESS_TOKEN, at: now }; }
      catch (e) { if (e.code === 'TOKEN_REJECTED') reason = e.code; else throw e; }
    }
    if (!reason) {
      return { token: env.DHAN_ACCESS_TOKEN, status: 'VALID', action: 'REUSED', expires_at: new Date(claims(env.DHAN_ACCESS_TOKEN).exp * 1000).toISOString(), profile_verified: true };
    }
  }
  if (!allowBrowser) return { status: 'WEB_TOKEN_REQUIRED', reason: reason || 'FORCED_BROWSER_RECOVERY' };
  const dir = path.join(root, '.private'); fs.mkdirSync(dir, { recursive: true, mode: 0o700 }); fs.chmodSync(dir, 0o700);
  const release = lock(dir);
  try {
    const pending = path.join(dir, 'pending-web-token.json');
    let capture;
    if (fs.existsSync(pending)) capture = JSON.parse(privateRead(pending));
    else {
      const attempt = path.join(dir, 'token-attempt.json');
      if (fs.existsSync(attempt) && now - JSON.parse(privateRead(attempt)).at < 300000) throw new AuthError('RECOVERY_COOLDOWN_RETRY_AFTER_FIVE_MINUTES');
      atomicPrivate(attempt, JSON.stringify({ at: now }));
      const recoverFn = recover || (await import('./web-token-browser.mjs')).captureWebToken;
      capture = await recoverFn({ root, clientId: env.DHAN_CLIENT_ID, until });
      // Journal before validation/persistence; never regenerate after ambiguous network/write failure.
      atomicPrivate(pending, JSON.stringify(capture));
    }
    if (capture.source !== 'DHAN_WEB' || capture.applicationName !== 'Dusty') throw new AuthError('WEB_TOKEN_PROVENANCE_REQUIRED');
    const missing = needsRecovery(capture.accessToken, env.DHAN_CLIENT_ID, until);
    if (missing) throw new AuthError(`CAPTURE_${missing}`);
    await verifyProfile(capture.accessToken, env.DHAN_CLIENT_ID, fetchFn);
    const expiry = new Date(claims(capture.accessToken).exp * 1000).toISOString();
    const updated = mergeEnv(original, { DHAN_ACCESS_TOKEN: capture.accessToken, DHAN_TOKEN_SOURCE: 'DHAN_WEB', DHAN_TOKEN_NAME: 'Dusty', DHAN_TOKEN_EXPIRES_AT: expiry });
    atomicPrivate(envFile, updated, original);
    fs.unlinkSync(pending);
    cache = { token: capture.accessToken, at: Date.now() };
    let cleanupResult;
    try {
      const cleanupFn = cleanup || (await import('./web-token-browser.mjs')).cleanupWebTokens;
      cleanupResult = await cleanupFn({ root, clientId: env.DHAN_CLIENT_ID, keepToken: capture.accessToken });
    } catch (e) { cleanupResult = { status: 'BLOCKED', reason: e instanceof AuthError ? e.code : 'CLEANUP_UNVERIFIED' }; }
    atomicPrivate(path.join(dir, 'token-cleanup.json'), JSON.stringify(cleanupResult));
    return { token: capture.accessToken, status: 'VALID', action: 'BROWSER_TOKEN_SAVED', expires_at: expiry, profile_verified: true, cleanup: cleanupResult };
  } finally { release(); }
}
