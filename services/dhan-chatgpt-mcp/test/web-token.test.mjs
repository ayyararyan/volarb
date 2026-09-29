import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { claims, sessionEnd, needsRecovery, mergeEnv, atomicPrivate, privateRead, ensureToken, verifyProfile, invalidateTokenCache } from '../src/web-token.mjs';
import { DhanClient } from '../src/dhan-client.mjs';
const now = Date.parse('2026-09-29T04:00:00Z');
const token = (exp, id = 'test-client') => `e30.${Buffer.from(JSON.stringify({ exp: exp / 1000, dhanClientId: id })).toString('base64url')}.signature`;
const noCleanup = async () => ({ status: 'VERIFIED', revoked: 0 });
const goodProfile = async () => ({ ok: true, status: 200, json: async () => ({ dhanClientId: 'test-client' }) });
function fixture(t, oldToken) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dhan-auth-test-')); fs.chmodSync(root, 0o700);
  fs.writeFileSync(path.join(root, '.env'), `# keep comment\nDHAN_CLIENT_ID=test-client\nDHAN_ACCESS_TOKEN=${oldToken || ''}\nUNRELATED=preserved\n`, { mode: 0o600 });
  t.after(() => fs.rmSync(root, { recursive: true, force: true })); return root;
}
test('regular session ends at 15:30 IST; after close uses a short current horizon, explicit special sessions need timezone', () => {
  assert.equal(sessionEnd(now), Date.parse('2026-09-29T10:00:00Z'));
  const late = Date.parse('2026-09-29T14:00:00Z'); assert.equal(sessionEnd(late), late + 300000);
  assert.throws(() => sessionEnd(now, '2026-09-29T17:00:00'), /TIMEZONE/);
  assert.equal(sessionEnd(now, '2026-09-29T17:00:00+05:30'), Date.parse('2026-09-29T11:30:00Z'));
});
test('missing, expired, malformed, short-lived and wrong-account tokens cannot pass', () => {
  const end = sessionEnd(now);
  assert.equal(needsRecovery('', 'test-client', end, now), 'MISSING_TOKEN');
  assert.equal(needsRecovery('bad', 'test-client', end, now), 'MALFORMED_TOKEN');
  assert.equal(needsRecovery(token(now), 'test-client', end, now), 'EXPIRED_TOKEN');
  assert.equal(needsRecovery(token(end), 'test-client', end, now), 'EXPIRES_BEFORE_SESSION_END');
  assert.equal(needsRecovery(token(end + 300001), 'test-client', end, now), null);
  assert.throws(() => needsRecovery(token(end + 3600000, 'other'), 'test-client', end, now), /ACCOUNT_MISMATCH/);
});
test('environment merge preserves unrelated lines and replaces duplicate token definitions', () => {
  const result = mergeEnv('# hi\nDHAN_ACCESS_TOKEN=a\nKEEP=42\nexport DHAN_ACCESS_TOKEN=b\n', { DHAN_ACCESS_TOKEN: 'new' });
  assert.equal(result, '# hi\nDHAN_ACCESS_TOKEN=new\nKEEP=42\n');
});
test('atomic write refuses concurrent edits and keeps mode 600', t => {
  const root = fixture(t, 'old'), p = path.join(root, '.env'); const old = privateRead(p);
  assert.throws(() => atomicPrivate(p, 'new', 'stale'), /ENV_CHANGED/); assert.equal(privateRead(p), old);
  atomicPrivate(p, 'new', old); assert.equal(privateRead(p), 'new'); assert.equal(fs.statSync(p).mode & 0o777, 0o600);
});
test('profile identity, 401, network and non-auth failures stay distinct', async () => {
  await assert.rejects(verifyProfile('t', 'other', goodProfile), /ACCOUNT_MISMATCH/);
  await assert.rejects(verifyProfile('t', 'test-client', async () => ({ status: 401 })), /TOKEN_REJECTED/);
  await assert.rejects(verifyProfile('t', 'test-client', async () => { throw Error('secret'); }), /NETWORK_UNVERIFIED/);
  await assert.rejects(verifyProfile('t', 'test-client', async () => ({ status: 429 })), /HTTP_429/);
});
test('valid token is reused without browser and network failure does not generate', async t => {
  const root = fixture(t, token(Date.now() + 86400000)); let calls = 0;
  const opts = { root, allowBrowser: true, cleanup: noCleanup, fetchFn: goodProfile, recover: async () => { calls++; } };
  assert.equal((await ensureToken(opts)).action, 'REUSED'); assert.equal(calls, 0);
  invalidateTokenCache();
  await assert.rejects(ensureToken({ ...opts, fetchFn: async () => { throw Error('network'); } }), /NETWORK_UNVERIFIED/);
  assert.equal(calls, 0);
});
test('missing token browser recovery validates, persists and consumes private pending capture', async t => {
  const root = fixture(t); const accessToken = token(Date.now() + 86400000);
  const result = await ensureToken({ root, allowBrowser: true, cleanup: noCleanup, fetchFn: goodProfile,
    recover: async () => ({ source: 'DHAN_WEB', applicationName: 'Dusty', accessToken }) });
  assert.equal(result.action, 'BROWSER_TOKEN_SAVED'); assert.ok(privateRead(path.join(root, '.env')).includes('UNRELATED=preserved'));
  assert.ok(privateRead(path.join(root, '.env')).includes(accessToken));
  assert.equal(fs.existsSync(path.join(root, '.private', 'pending-web-token.json')), false);
});
test('wrong-account capture never overwrites old env and remains private for inspection', async t => {
  const root = fixture(t); const before = privateRead(path.join(root, '.env'));
  await assert.rejects(ensureToken({ root, allowBrowser: true, cleanup: noCleanup, fetchFn: goodProfile,
    recover: async () => ({ source: 'DHAN_WEB', applicationName: 'Dusty', accessToken: token(Date.now()+86400000, 'other') }) }), /ACCOUNT_MISMATCH/);
  assert.equal(privateRead(path.join(root, '.env')), before);
});
test('ambiguous profile failure resumes pending capture without regenerating', async t => {
  const root = fixture(t); let generated = 0;
  const opts = { root, allowBrowser: true, cleanup: noCleanup, recover: async () => { generated++; return { source: 'DHAN_WEB', applicationName: 'Dusty', accessToken: token(Date.now()+86400000) }; } };
  await assert.rejects(ensureToken({ ...opts, fetchFn: async () => { throw Error('offline'); } }), /NETWORK_UNVERIFIED/);
  assert.equal((await ensureToken({ ...opts, fetchFn: goodProfile })).status, 'VALID'); assert.equal(generated, 1);
});
test('browser failures receive a five-minute cooldown and locks release', async t => {
  const root = fixture(t); const opts = { root, allowBrowser: true, cleanup: noCleanup, recover: async () => { throw Error('blocked'); } };
  await assert.rejects(ensureToken(opts), /blocked/);
  await assert.rejects(ensureToken(opts), /COOLDOWN/);
  assert.equal(fs.existsSync(path.join(root,'.private','token-recovery.lock')), false);
});
test('Dhan client reads replacement token each request without restart', async () => {
  const oldFetch = globalThis.fetch; const seen = []; let current = 'one';
  globalThis.fetch = async (_url, opts) => { seen.push(opts.headers['access-token']); return { ok: true, text: async () => '{}' }; };
  try { const c = new DhanClient({ clientId: 'test', tokenProvider: async () => current }); await c.getProfile(); current = 'two'; await c.getProfile(); assert.deepEqual(seen, ['one','two']); }
  finally { globalThis.fetch = oldFetch; }
});

test('cleanup preserves current and other active applications, revokes expired and superseded Dusty', async () => {
  const { cleanupEligible } = await import('../src/web-token-browser.mjs');
  const keep = token(now + 86400000);
  assert.equal(cleanupEligible({ token: keep, name: 'Dusty', status: 'Active' }, keep, now), false);
  assert.equal(cleanupEligible({ token: token(now + 7200000), name: 'Dusty', status: 'Active' }, keep, now), true);
  assert.equal(cleanupEligible({ token: token(now + 7200000), name: 'Other App', status: 'Active' }, keep, now), false);
  assert.equal(cleanupEligible({ token: token(now - 1), name: 'Other App', status: 'Expired' }, keep, now), true);
  assert.equal(cleanupEligible({ token: token(now + 172800000), name: 'Dusty', status: 'Active' }, keep, now), false);
});
