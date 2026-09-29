// One-shot readonly connectivity/market-data capture. No scheduler, executor or ledger imports.
import { resolve } from 'node:path';
import { RUNTIME } from './runtime-paths.mjs';
import dotenv from 'dotenv';
import { privateRead, ensureToken, invalidateTokenCache } from './web-token.mjs';
import { InstrumentMaster } from './instrument-master.mjs';
import { ReadOnlyDhanClient, readonlyFacade, collectWorkflowData, saveWorkflowEvidence } from './workflow-data.mjs';

import { collectHF, resolveFutures } from './workflow-hf.mjs';

const PROJECT = RUNTIME.root;
const EVIDENCE = RUNTIME.evidence;
async function main() {
  const args = process.argv.slice(2);
  if (args.length !== 2 || args[0] !== '--scope' || !['account','market','position','hf'].includes(args[1]))
    throw Object.assign(new Error(), { code: 'USE_SCOPE_ACCOUNT_OR_MARKET' });
  if (process.env.VOLARB_OBSERVE_ENABLED !== 'true')
    throw Object.assign(new Error(), { code: 'READ_ONLY_PROFILE_REQUIRED' });
  const env = dotenv.parse(privateRead(resolve(PROJECT, '.env')));
  const tokenProvider = async () => {
    const receipt = await ensureToken({ root: PROJECT, allowBrowser: false });
    if (receipt.status !== 'VALID') throw Object.assign(new Error(), { code: 'WEB_TOKEN_RECOVERY_REQUIRED' });
    return receipt.token;
  };
  // Resolve authentication once before launching concurrent account reads.
  await tokenProvider();
  const client = new ReadOnlyDhanClient({ clientId: env.DHAN_CLIENT_ID, tokenProvider, onAuthRejected: invalidateTokenCache });
  const master = new InstrumentMaster({ fetchFn: (url, options) => fetch(url, { ...options, signal: AbortSignal.timeout(20000) }) });
  if (args[1] === 'hf') {
    const instruments = resolveFutures(await master.getRows(), new Date(Date.now()+19800000).toISOString().slice(0,10));
    const evidence = await collectHF({ broker: readonlyFacade(client), instruments });
    const saved = await saveWorkflowEvidence(evidence, EVIDENCE);
    console.log(JSON.stringify({ ...saved, status:'HF_CAPTURED_UNVALIDATED', orders_sent:false, jobs_scheduled:false, trading_ready:false }));
    return;
  }
  const evidence = await collectWorkflowData({ broker: readonlyFacade(client), master, scope: args[1].toUpperCase() });
  const saved = await saveWorkflowEvidence(evidence, EVIDENCE);
  console.log(JSON.stringify({ ...saved, status: evidence.status, account_verified: evidence.account.verified,
    trading_ready: false, orders_sent: false, jobs_scheduled: false, production_ledger_written: false }));
  if (!evidence.account.verified || evidence.status === 'PARTIAL_MARKET_DATA') process.exitCode = 2;
}
main().catch(error => {
  const code = typeof error?.code === 'string' && /^[A-Z][A-Z0-9_]{1,90}$/.test(error.code) ? error.code : 'READ_ONLY_CAPTURE_FAILED';
  console.log(JSON.stringify({ status: 'BLOCKED', code, account_verified: false, trading_ready: false,
    orders_sent: false, jobs_scheduled: false, production_ledger_written: false }));
  process.exitCode = 2;
});
