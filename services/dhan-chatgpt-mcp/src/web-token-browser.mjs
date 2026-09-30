import fs from 'node:fs';
import path from 'node:path';
import dotenv from 'dotenv';
import { execFileSync, spawn } from 'node:child_process';
import { chromium } from 'playwright-core';
import { AuthError, privateRead, claims, needsRecovery, verifyProfile } from './web-token.mjs';

import { browserSettings } from './runtime-paths.mjs';
const ORIGINS = new Set(['https://web.dhan.co', 'https://login.dhan.co']);
function guard(page) {
  if (!ORIGINS.has(new URL(page.url()).origin)) throw new AuthError('UNEXPECTED_LOGIN_ORIGIN');
}
export async function uniqueClick(locator, errorCode = 'DHAN_UI_CHANGED') {
  const visible = locator.filter({ visible: true });
  if (await visible.count() !== 1) throw new AuthError(errorCode);
  await visible.click({ timeout: 10000 });
}
async function uniqueFill(locator, value, errorCode = 'DHAN_UI_CHANGED') {
  const visible = locator.filter({ visible: true });
  if (await visible.count() !== 1) throw new AuthError(errorCode);
  await visible.fill(value);
}
export async function login(page, root) {
  let pinSubmitted = false, mobileSubmitted = false;
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    guard(page);
    if (page.url().startsWith('https://web.dhan.co/index/')) return { pinSubmitted, mobileSubmitted };
    const visibleText = await page.locator('body').innerText();
    if (/captcha|enter.{0,20}(otp|verification code)|one.time password/i.test(visibleText)) throw new AuthError('HUMAN_VERIFICATION_REQUIRED_IN_BROWSER');
    const mobileMode = page.getByText('Show login with Mobile', { exact: true });
    if (await mobileMode.filter({ visible: true }).count()) {
      await uniqueClick(mobileMode, 'LOGIN_MOBILE_TOGGLE_AMBIGUOUS');
      await page.waitForTimeout(500);
      continue;
    }
    const mobile = page.getByPlaceholder('Enter Your Mobile Number Here', { exact: true });
    if (await mobile.filter({ visible: true }).count()) {
      const saved = path.join(root, '.private', 'dhan-login.json');
      if (!fs.existsSync(saved)) throw new AuthError('ENTER_MOBILE_DIRECTLY_IN_BROWSER');
      if (mobileSubmitted) throw new AuthError('MOBILE_LOGIN_REJECTED_OR_UI_CHANGED');
      const { mobileNumber } = JSON.parse(privateRead(saved));
      if (!/^\d{10}$/.test(mobileNumber)) throw new AuthError('PRIVATE_MOBILE_NUMBER_INVALID');
      await uniqueFill(mobile, mobileNumber, 'LOGIN_MOBILE_INPUT_AMBIGUOUS');
      await uniqueClick(page.getByText('Proceed', { exact: true }), 'LOGIN_PROCEED_AMBIGUOUS');
      mobileSubmitted = true;
      await page.waitForTimeout(1000);
      continue;
    }
    // Require an explicit PIN-labelled page; never fill an OTP/password form by guessing.
    if (/\bPIN\b/i.test(visibleText)) {
      if (pinSubmitted) { await page.waitForTimeout(500); continue; }
      const { pinFile } = browserSettings();
      if (!pinFile) throw new AuthError('DHAN_PIN_FILE_NOT_CONFIGURED');
      const pin = dotenv.parse(privateRead(pinFile)).DHAN_PIN;
      if (!/^\d{6}$/.test(pin || '')) throw new AuthError('SAVED_PIN_MISSING_OR_INVALID');
      const single = page.locator('input[type="password"]:visible, input[type="tel"][maxlength="6"]:visible');
      const digits = page.locator('input[maxlength="1"]:visible, input[type="tel"]:visible, input[type="password"]:visible');
      if (await single.count() === 1) await single.fill(pin);
      else if (await digits.count() === 6) {
        for (let i = 0; i < 6; i++) await digits.nth(i).fill(pin[i]);
      } else throw new AuthError('PIN_FIELDS_UNRECOGNIZED');
      pinSubmitted = true;
      const submit = page.getByText(/^(Proceed|Login|Continue|Verify PIN|Verify)$/).filter({ visible: true });
      if (await submit.count() === 1) await uniqueClick(submit);
    }
    await page.waitForTimeout(500);
  }
  throw new AuthError('LOGIN_NOT_COMPLETED_IN_BROWSER');
}
export async function captureWebToken({ root, clientId, until, cleanupOnly = false, keepToken }) {
  const settings = browserSettings();
  // macOS loopback only. This dedicated profile is never synced or sent elsewhere.
  const profile = path.join(root, '.private', 'dhan-browser');
  fs.mkdirSync(profile, { recursive: true, mode: 0o700 }); fs.chmodSync(profile, 0o700);
  let browser, context, owned = false, succeeded = false;
  try {
    try {
      browser = await chromium.connectOverCDP(settings.endpoint, { timeout: 1500 });
      context = browser.contexts()[0];
      // Only attach if this is the explicitly owned dedicated office-Mac profile.
      const pid = execFileSync('/usr/sbin/lsof', [`-tiTCP:${settings.port}`, '-sTCP:LISTEN'], { encoding: 'utf8' }).trim();
      if (!/^\d+$/.test(pid)) throw new AuthError('BROWSER_PROFILE_MISMATCH');
      const command = execFileSync('/bin/ps', ['-p', pid, '-o', 'command='], { encoding: 'utf8' });
      if (!command.includes(`--user-data-dir=${profile}`)) throw new AuthError('BROWSER_PROFILE_MISMATCH');
    } catch (e) {
      if (browser) throw e;
      const child = spawn(settings.chrome, [`--user-data-dir=${profile}`, `--remote-debugging-port=${settings.port}`, '--remote-debugging-address=127.0.0.1', '--no-first-run', '--no-default-browser-check', 'https://web.dhan.co/'], { detached: true, stdio: 'ignore' });
      child.unref(); owned = true;
      for (let i = 0; i < 20 && !browser; i++) {
        await new Promise(r => setTimeout(r, 250));
        try { browser = await chromium.connectOverCDP(settings.endpoint, { timeout: 500 }); } catch {}
      }
      if (!browser) throw new AuthError('OFFICE_BROWSER_START_FAILED');
      context = browser.contexts()[0];
    }
    const page = context.pages().find(p => { try { return ORIGINS.has(new URL(p.url()).origin); } catch { return false; } }) || await context.newPage();
    page.setDefaultTimeout(15000);
    if (!ORIGINS.has(new URL(page.url()).origin)) await page.goto('https://web.dhan.co/', { waitUntil: 'domcontentloaded' });
    await page.bringToFront();
    await login(page, root);
    // Observed Dhan Web route and menu, 2026-09-29. Do not click any trading controls.
    await page.goto('https://web.dhan.co/index/profile', { waitUntil: 'domcontentloaded' });
    await uniqueClick(page.getByText('Profile & Account Details', { exact: true }), 'PROFILE_DETAILS_CONTROL_AMBIGUOUS');
    await page.getByText('Client ID', { exact: true }).filter({ visible: true }).first().waitFor();
    const details = await page.locator('body').innerText();
    if (details.match(/Client ID\s+(\d+)/)?.[1] !== String(clientId)) throw new AuthError('ACCOUNT_MISMATCH');
    await uniqueClick(page.getByText('DhanHQ Trading APIs', { exact: true }), 'TRADING_API_CONTROL_AMBIGUOUS');
    await page.getByText('Generate new Access Token', { exact: true }).filter({ visible: true }).first().waitFor();
    guard(page);
    await page.locator('td.mat-column-token').first().waitFor({ timeout: 5000 }).catch(() => {});
    if (cleanupOnly) {
      const result = await cleanRows(page, root, clientId, keepToken);
      succeeded = true; return result;
    }
    const rows = page.locator('tr').filter({ has: page.getByText('Dusty', { exact: true }) });
    const oldTokens = new Set();
    for (const row of await rows.all()) {
      const token = (await row.locator('.mat-column-token').innerText()).trim().match(/[\w-]+\.[\w-]+\.[\w-]+/)?.[0];
      if (token) {
        if (String(claims(token).dhanClientId) !== String(clientId)) throw new AuthError('ACCOUNT_MISMATCH');
        oldTokens.add(token);
      }
    }
    // Recover an already-created valid web token after an interrupted generation,
    // rather than minting duplicates on retries. Latest eligible token wins.
    const reusable = [...oldTokens].filter(t => !needsRecovery(t, clientId, until)).sort((a,b) => claims(b).exp - claims(a).exp);
    for (const token of reusable) {
      try { await verifyProfile(token, clientId); }
      catch (e) { if (e.code === 'TOKEN_REJECTED') continue; throw e; }
      succeeded = true; return { source: 'DHAN_WEB', applicationName: 'Dusty', accessToken: token };
    }
    // No raw page snapshots, response logging, system clipboard, screenshots or traces.
    const name = page.getByPlaceholder('Name your Application', { exact: true });
    if (!await name.filter({ visible: true }).count()) await uniqueClick(page.getByText('Generate', { exact: true }), 'GENERATE_CONTROL_AMBIGUOUS');
    await uniqueFill(name, 'Dusty', 'APPLICATION_NAME_INPUT_AMBIGUOUS');
    await page.getByText('24 Hours', { exact: true }).filter({ visible: true }).first().waitFor();
    await uniqueClick(page.getByText('Generate Access Token', { exact: true }), 'GENERATE_TOKEN_CONTROL_AMBIGUOUS');
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      guard(page);
      for (const row of await rows.all()) {
        const token = (await row.locator('.mat-column-token').innerText()).trim().match(/[\w-]+\.[\w-]+\.[\w-]+/)?.[0];
        if (token && !oldTokens.has(token) && !needsRecovery(token, clientId, until)) {
          succeeded = true;
          return { source: 'DHAN_WEB', applicationName: 'Dusty', accessToken: token };
        }
      }
      await page.waitForTimeout(250);
    }
    throw new AuthError('GENERATION_UNVERIFIED_NO_AUTOMATIC_RETRY');
  } catch (e) {
    if (e instanceof AuthError) throw e;
    throw new AuthError('BROWSER_UNAVAILABLE_OR_UI_CHANGED');
  } finally {
    // Close successful automation; leave an interactive blocker visible for the user.
    if (succeeded && owned && browser) {
      const cdp = await browser.newBrowserCDPSession();
      await cdp.send('Browser.close').catch(() => {});
    }
    if (browser) await browser.close().catch(() => {});
  }
}

// Never revoke before the replacement is verified and durably installed.
export async function cleanupWebTokens({ root, clientId, keepToken }) {
  await verifyProfile(keepToken, clientId);
  if (dotenv.parse(privateRead(path.join(root, '.env'))).DHAN_ACCESS_TOKEN !== keepToken) throw new AuthError('ENV_CHANGED_CLEANUP_STOPPED');
  return captureWebToken({ root, clientId, until: Date.now(), cleanupOnly: true, keepToken });
}
export function cleanupEligible({ token, name, status }, keepToken, now = Date.now()) {
  if (token === keepToken) return false;
  const c = claims(token), keep = claims(keepToken);
  if (String(c.dhanClientId) !== String(keep.dhanClientId)) throw new AuthError('ACCOUNT_MISMATCH');
  if (c.exp * 1000 <= now || /^Expired$/i.test(status)) return true;
  // A newer Dusty token may belong to another concurrent recovery: preserve it.
  return name === 'Dusty' && c.exp <= keep.exp;
}
async function cleanRows(page, root, clientId, keepToken) {
  let revoked = 0;
  const all = page.locator('tr').filter({ has: page.locator('td.mat-column-token') });
  await page.getByText(keepToken, { exact: true }).waitFor();
  const inventory = [];
  for (const row of await all.all()) {
    const token = (await row.locator('.mat-column-token').innerText()).trim().match(/[\w-]+\.[\w-]+\.[\w-]+/)?.[0];
    if (!token) throw new AuthError('TOKEN_TABLE_UNRECOGNIZED');
    inventory.push({ token, name: (await row.locator('.mat-column-tokenLabel').innerText()).trim(), status: (await row.locator('.mat-column-tokenType').innerText()).trim() });
  }
  if (!inventory.some(x => x.token === keepToken && x.status === 'Active')) throw new AuthError('REPLACEMENT_NOT_ACTIVE_IN_WEB');
  for (const item of inventory) {
    if (!cleanupEligible(item, keepToken)) continue;
    guard(page);
    if (dotenv.parse(privateRead(path.join(root, '.env'))).DHAN_ACCESS_TOKEN !== keepToken) throw new AuthError('ENV_CHANGED_CLEANUP_STOPPED');
    const row = all.filter({ has: page.getByText(item.token, { exact: true }) });
    await uniqueClick(row.getByText('Revoke', { exact: true }));
    const dialog = page.getByRole('dialog');
    await dialog.getByText('Are you sure you want to delete this Access Token?', { exact: true }).waitFor();
    await uniqueClick(dialog.locator('button').filter({ has: page.locator('img[src="assets/images/confirm.svg"]') }));
    await row.waitFor({ state: 'detached', timeout: 15000 });
    revoked++;
  }
  await verifyProfile(keepToken, clientId);
  return { status: 'VERIFIED', revoked, preserved: inventory.length - revoked };
}
