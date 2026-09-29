import * as z from 'zod/v4';
import { timingSafeEqual } from 'node:crypto';
import { readFileSync, statSync, mkdirSync, writeFileSync, rmdirSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { isIP } from 'node:net';
import { McpServer } from '@modelcontextprotocol/server';
import { ButterflyExecutor, ExecutionStore, planSchema } from './butterfly-executor.mjs';

export function bearerAuthorized(header, token) {
  if (!token || token.length < 32 || typeof header !== 'string') return false;
  const expected = Buffer.from(`Bearer ${token}`), supplied = Buffer.from(header);
  return supplied.length === expected.length && timingSafeEqual(supplied, expected);
}
export function loadExecutionToken(file) {
  if (!file) return '';
  const mode = statSync(file).mode;
  if ((mode & 0o077) !== 0) throw new Error('Execution token file must be private (chmod 600)');
  const token = readFileSync(file, 'utf8').trim();
  if (token.length < 32) throw new Error('Execution token must have at least 32 characters');
  return token;
}

// Prevent two server processes from managing one account/state store concurrently.
export function acquireExecutionLock(dir) {
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const lock = join(dir, 'process.lock');
  try { mkdirSync(lock, { mode: 0o700 }); }
  catch (e) {
    if (e.code !== 'EEXIST') throw e;
    const oldPid = Number(readFileSync(join(lock, 'pid'), 'utf8'));
    if (!Number.isInteger(oldPid) || oldPid < 1) throw new Error('Invalid execution lock; inspect manually');
    try { process.kill(oldPid, 0); throw new Error('Another MCP executor process owns the state directory'); }
    catch (err) { if (err.code !== 'ESRCH') throw err; }
    unlinkSync(join(lock, 'pid')); rmdirSync(lock); mkdirSync(lock, { mode: 0o700 });
  }
  writeFileSync(join(lock, 'pid'), String(process.pid), { mode: 0o600 });
  return () => { unlinkSync(join(lock, 'pid')); rmdirSync(lock); };
}

export function makeReadiness({ broker, enabled, token, expectedIp, staticIpConfirmed, fetchFn = fetch }) {
  return async () => {
    if (!enabled) throw new Error('Live execution disabled: DHAN_EXECUTION_ENABLED is not true');
    if (!token) throw new Error('Authenticated execution token is not configured');
    if (!isIP(expectedIp || '') || !staticIpConfirmed) throw new Error('Configure and confirm a static outbound IP before enabling');
    const response = await fetchFn('https://api.ipify.org?format=json', { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error('Could not verify outbound IP');
    const { ip } = await response.json();
    if (ip !== expectedIp) throw new Error('Current outbound IP differs from configured static IP');
    const raw = await broker.getWhitelistedIps(); const ips = raw?.data ?? raw;
    if (![ips?.primaryIP, ips?.secondaryIP].includes(expectedIp)) throw new Error('Outbound IP is not present in Dhan whitelist');
    const p = await broker.getProfile(); const profile = p?.data ?? p;
    if (String(profile?.dhanClientId) !== String(broker.clientId)) throw new Error('Dhan account identity mismatch');
    return { ready: true, authenticated: true, staticIpWhitelisted: true };
  };
}

export function buildExecutionServer(executor, readiness, enabled) {
  const server = new McpServer({ name: 'dhan-butterfly-executor', version: '0.3.0' });
  const register = (name, description, schema, readOnly, fn) => server.registerTool(name, {
    description, inputSchema: schema,
    _meta: { securitySchemes: [{ type: 'oauth2', scopes: ['butterfly:execute'] }] },
    annotations: { readOnlyHint: readOnly, destructiveHint: !readOnly, idempotentHint: readOnly || name !== 'dhan_preview_butterfly', openWorldHint: true }
  }, async args => {
    try { const data = await fn(args); return { content: [{ type: 'text', text: JSON.stringify({ data }) }], structuredContent: { data } }; }
    catch (e) { return { isError: true, content: [{ type: 'text', text: JSON.stringify({ error: e.message }) }] }; }
  });
  register('dhan_executor_readiness', 'Check authenticated executor configuration and static outbound IP against Dhan whitelist. Does not place any orders.', z.object({}), true, async () => {
    try { return await readiness(); } catch (e) { return { ready: false, enabled, blocker: e.message }; }
  });
  register('dhan_preview_butterfly', 'Prepare an iron-butterfly ENTRY or EXIT; NO broker mutations. Explicit strikes, expiry, lots and all four rupee/unit price limits required. BUY limit=max; SELL limit=min. Preview valid 60 seconds. ENTRY: buy put wing, sell put body, buy call wing, sell call body. EXIT reverses that sequence. Present exact plan to user before execute. Use only after the user has chosen a trade; this tool does not approve strategy risk.', planSchema, false, args => executor.preview(args));
  register('dhan_execute_butterfly', 'LIVE TRADING: execute precisely the user-approved preview via bounded LIMIT orders. Requires planId and matching confirmation from preview. Never infer approval from a research recommendation. Returns immediately with persistent status. Repeated calls do not restart or duplicate the job. No market-order fallback. Must request exit separately; no position monitoring/automatic 15:00 square-off.', z.object({ planId: z.string().uuid(), confirmation: z.string().length(24) }), false, a => executor.execute(a.planId, a.confirmation));
  register('dhan_butterfly_execution_status', 'Read persisted execution state, fills, pending orders and blockers. This is not fresh broker reconciliation or a financial ledger.', z.object({ planId: z.string().uuid().optional() }), true, a => executor.status(a.planId));
  register('dhan_stop_butterfly_execution', 'Stop new legs and request cancellation of this executor job’s pending order. Does NOT flatten filled exposure. Poll status for verified cancellation; uncertain outcomes require Dhan reconciliation. Preserves protective wings.', z.object({ planId: z.string().uuid() }), false, a => executor.stop(a.planId));
  register('dhan_reconcile_butterfly_execution', 'Read fresh broker order/trade/position evidence after interruption. Does not cancel, retry or resume orders. Pending or ambiguous orders must be resolved in Dhan first. Once reconciled, a fresh EXIT preview can close residual inventory.', z.object({ planId: z.string().uuid() }), true, a => executor.reconcile(a.planId));
  return server;
}
export function createExecutor({ broker, master, env = process.env }) {
  const dir = env.DHAN_EXECUTION_STATE_DIR || join(process.cwd(), '.private', 'execution');
  const token = loadExecutionToken(env.MCP_EXECUTION_TOKEN_FILE);
  const enabled = env.DHAN_EXECUTION_ENABLED === 'true';
  if (enabled && !token) throw new Error('Cannot enable execution without authenticated endpoint');
  const release = acquireExecutionLock(dir);
  const readiness = makeReadiness({ broker, enabled, token, expectedIp: env.DHAN_EXECUTION_EGRESS_IP, staticIpConfirmed: env.DHAN_EXECUTION_STATIC_IP_CONFIRMED === 'true' });
  const executor = new ButterflyExecutor({ broker, master, store: new ExecutionStore(dir), enabled, readiness });
  return { executor, token, enabled, readiness, release };
}
