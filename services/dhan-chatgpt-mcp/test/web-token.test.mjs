import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { claims, sessionEnd, needsRecovery, mergeEnv, atomicPrivate, privateRead, ensureToken, verifyProfile, renewWebToken, invalidateTokenCache } from '../src/web-token.mjs';
import { uniqueClick } from '../src/web-token-browser.mjs';
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
test('official RenewToken request returns and validates the replacement web token', async () => {
  const oldToken = token(now + 3600000);
  const replacement = token(now + 86400000);
  let request;
  const result = await renewWebToken(oldToken, 'test-client', async (url, opts) => {
    request = { url, opts };
    return { ok: true, status: 200, json: async () => ({ accessToken: replacement, expiryTime: '2026-09-30T09:30:00' }) };
  });
  assert.equal(result, replacement);
  assert.equal(request.url, 'https://api.dhan.co/v2/RenewToken');
  assert.equal(request.opts.method, 'GET');
  assert.equal(request.opts.headers['access-token'], oldToken);
  assert.equal(request.opts.headers.dhanClientId, 'test-client');
});
test('browser click helper scopes strictness to visible actionable controls', async () => {
  let clicked = 0;
  const visible = { count: async () => 1, click: async () => { clicked++; } };
  const locator = { filter: ({ visible: flag }) => { assert.equal(flag, true); return visible; } };
  await uniqueClick(locator, 'VISIBLE_CONTROL_AMBIGUOUS');
  assert.equal(clicked, 1);
  const ambiguous = { filter: () => ({ count: async () => 2, click: async () => { throw Error('should not click'); } }) };
  await assert.rejects(uniqueClick(ambiguous, 'VISIBLE_CONTROL_AMBIGUOUS'), /VISIBLE_CONTROL_AMBIGUOUS/);
});
test('valid token is reused without browser and network failure does not generate', async t => {
  const root = fixture(t, token(Date.now() + 86400000)); let calls = 0;
  const opts = { root, allowBrowser: true, cleanup: noCleanup, fetchFn: goodProfile, recover: async () => { calls++; } };
  assert.equal((await ensureToken(opts)).action, 'REUSED'); assert.equal(calls, 0);
  invalidateTokenCache();
  await assert.rejects(ensureToken({ ...opts, fetchFn: async () => { throw Error('network'); } }), /NETWORK_UNVERIFIED/);
  assert.equal(calls, 0);
});
test('near-expiry Dhan Web token renews by API before browser recovery', async t => {
  invalidateTokenCache();
  const end = sessionEnd(now);
  const oldToken = token(end + 60000);
  const replacement = token(now + 86400000);
  const root = fixture(t, oldToken);
  fs.appendFileSync(path.join(root, '.env'), 'DHAN_TOKEN_SOURCE=DHAN_WEB\nDHAN_TOKEN_NAME=Dusty\n');
  let renewCalls = 0, browserCalls = 0;
  const result = await ensureToken({
    root, now, allowBrowser: true, cleanup: noCleanup, fetchFn: goodProfile,
    renew: async (seenToken, seenClient) => {
      renewCalls++;
      assert.equal(seenToken, oldToken);
      assert.equal(seenClient, 'test-client');
      return replacement;
    },
    recover: async () => { browserCalls++; throw Error('browser should not run'); }
  });
  assert.equal(result.action, 'API_TOKEN_RENEWED');
  assert.equal(result.token, replacement);
  assert.equal(renewCalls, 1);
  assert.equal(browserCalls, 0);
  const saved = privateRead(path.join(root, '.env'));
  assert.ok(saved.includes(`DHAN_ACCESS_TOKEN=${replacement}`));
  assert.ok(saved.includes('DHAN_TOKEN_SOURCE=DHAN_WEB'));
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
