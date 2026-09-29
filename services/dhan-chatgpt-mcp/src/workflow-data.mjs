// Read-only acquisition for VolArb. Never imports the executor or calls an order mutation.
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, lstat, open, link, unlink, realpath } from 'node:fs/promises';
import { dirname, join, resolve, relative, sep } from 'node:path';
import { DhanClient, DhanApiError } from './dhan-client.mjs';
import { normalizeDhanChain } from './surface-analytics.mjs';

export const FORMAT = 'volarb.dhan.readonly.v1';
export const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX'];
const ALLOWED = new Set(['GET /profile', 'GET /fundlimit', 'GET /positions', 'GET /orders', 'GET /trades',
  'POST /optionchain/expirylist', 'POST /optionchain', 'POST /marketfeed/quote']);
const TERMINAL = new Set(['TRADED', 'CANCELLED', 'REJECTED', 'EXPIRED']);
const KNOWN = new Set([...TERMINAL, 'TRANSIT', 'PENDING', 'PART_TRADED']);
const need = (ok, code) => { if (!ok) { const e = new Error(code); e.code = code; throw e; } };
const num = v => {
  need((typeof v === 'number' || typeof v === 'string') && String(v).trim() !== '' && Number.isFinite(Number(v)), 'INVALID_NUMERIC_EVIDENCE');
  return Number(v);
};
const stable = v => Array.isArray(v) ? v.map(stable) : v && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, stable(v[k])])) : v;
export const sha256 = v => createHash('sha256').update(typeof v === 'string' ? v : JSON.stringify(stable(v))).digest('hex');
const sorted = rows => rows.map(stable).sort((a,b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
const iso = n => new Date(n).toISOString();
const day = n => new Date(n + 19800000).toISOString().slice(0, 10);

export class ReadOnlyDhanClient extends DhanClient {
  constructor(options) {
    need(!options.baseUrl || options.baseUrl === 'https://api.dhan.co/v2', 'FIXED_DHAN_ORIGIN_REQUIRED');
    super({ ...options, baseUrl: 'https://api.dhan.co/v2' });
    this.readonlyFetch = options.fetchFn ?? fetch;
  }
  async request(path, options = {}) {
    need(ALLOWED.has(`${options.method ?? 'GET'} ${path}`), 'READ_ONLY_ROUTE_REJECTED');
    const token = this.tokenProvider ? await this.tokenProvider() : this.accessToken;
    const response = await this.readonlyFetch(`https://api.dhan.co/v2${path}`, {
      method: options.method ?? 'GET', redirect: 'error', signal: AbortSignal.timeout(this.timeoutMs),
      headers: { 'Accept': 'application/json', 'Content-Type': 'application/json',
        'access-token': token, 'client-id': this.clientId },
      body: options.body === undefined ? undefined : JSON.stringify(options.body)
    });
    if (!response.ok) {
      if (response.status === 401) this.onAuthRejected?.();
      throw new DhanApiError('Readonly Dhan request failed', { status: response.status, path });
    }
    return response.json();
  }
}

export function readonlyFacade(client) {
  const names = ['getProfile', 'getFunds', 'getPositions', 'getOrders', 'getTrades', 'getQuote', 'getOptionExpiries', 'getOptionChain'];
  return Object.freeze(Object.fromEntries([
    ['clientId', client.clientId], ...names.map(name => [name, client[name].bind(client)])
  ]));
}

function unwrap(raw) {
  need(raw && typeof raw === 'object' && !['error','failure','failed'].includes(String(raw.status).toLowerCase())
    && !raw.errorCode && !raw.errorType, 'BROKER_ERROR_ENVELOPE');
  return raw.data ?? raw;
}

function project(row, fields) {
  need(row && typeof row === 'object' && !Array.isArray(row), 'INVALID_BROKER_ROW');
  return Object.fromEntries(fields.filter(k => Object.hasOwn(row, k)).map(k => {
    need(row[k] === null || ['string','number','boolean'].includes(typeof row[k]), 'NONSCALAR_BROKER_FIELD');
    return [k, row[k]];
  }));
}
const positionFields = ['securityId','exchangeSegment','productType','netQty','tradingSymbol','positionType',
  'drvExpiryDate','drvOptionType','drvStrikePrice','buyAvg','sellAvg','costPrice','buyQty','sellQty','realizedProfit','unrealizedProfit'];
const orderFields = ['orderId','correlationId','orderStatus','securityId','exchangeSegment','productType','transactionType',
  'quantity','filledQty','remainingQuantity','price','averageTradedPrice','createTime','updateTime','exchangeTime'];
const tradeFields = ['orderId','exchangeOrderId','exchangeTradeId','tradeId','securityId','exchangeSegment','productType',
  'transactionType','tradedQuantity','tradedPrice','exchangeTime','createTime','updateTime','tradingSymbol','drvExpiryDate','drvOptionType','drvStrikePrice'];

function arrayRows(raw, fields) {
  const rows = unwrap(raw);
  need(Array.isArray(rows), 'BROKER_ARRAY_REQUIRED');
  return rows.map(r => project(r, fields));
}

function positionKey(row) {
  need(/^\d+$/.test(String(row.securityId)) && typeof row.exchangeSegment === 'string'
    && typeof row.productType === 'string', 'POSITION_IDENTITY_REQUIRED');
  const netQty = num(row.netQty);
  need(Number.isSafeInteger(netQty), 'INVALID_POSITION_QUANTITY');
  return { securityId: String(row.securityId), exchangeSegment: row.exchangeSegment,
    productType: row.productType, netQty, drvExpiryDate: row.drvExpiryDate ?? null,
    drvOptionType: row.drvOptionType ?? null, drvStrikePrice: row.drvStrikePrice ?? null };
}

function orderKey(row) {
  need(typeof row.orderId === 'string' && row.orderId && KNOWN.has(row.orderStatus), 'UNKNOWN_ORDER_STATE');
  need(/^\d+$/.test(String(row.securityId)) && typeof row.exchangeSegment === 'string', 'ORDER_IDENTITY_REQUIRED');
  return row;
}

function safeError(error) {
  if (error?.name === 'DhanApiError') return { code: 'DHAN_REQUEST_FAILED', http_status: Number.isInteger(error.status) ? error.status : null };
  const code = error?.code;
  return { code: typeof code === 'string' && /^[A-Z][A-Z0-9_]{1,90}$/.test(code) ? code : 'ACQUISITION_FAILED' };
}

export async function collectWorkflowData({ broker, master, scope = 'ACCOUNT', now = Date.now,
  chainSpacingMs = 4000, wait = ms => new Promise(r => setTimeout(r, ms)) }) {
  need(['ACCOUNT','MARKET','POSITION'].includes(scope), 'INVALID_SCOPE');
  const started = now();
  const evidence = { format: FORMAT, provenance: 'OBSERVED', mode: 'READ_ONLY', collection_id: randomUUID(),
    scope, started_at: iso(started), endpoints: {}, markets: {}, blockers: [],
    account: { verified: false, verified_flat: null, ownership: 'UNASSIGNED' },
    capabilities: { orders: false, scheduling: false, financial_ledger: false },
    missing_layers: ['NEWS_FILTER', 'HF_RV', 'EXACT_CANDIDATE_QUOTES_AND_MARGIN', 'COST_BOUNDS', 'STRATEGY_OWNERSHIP'] };
  async function record(name, fn, normalize) {
    const began = now();
    try {
      const raw = await fn();
      const data = normalize(raw);
      const ended = now();
      need(ended >= began && ended - began <= 30000, 'REQUEST_TOO_SLOW');
      evidence.endpoints[name] = { status: 'OK', requested_at: iso(began), received_at: iso(ended),
        raw_sha256: sha256(raw), data };
      return data;
    } catch (error) {
      evidence.endpoints[name] = { status: 'UNAVAILABLE', requested_at: iso(began), received_at: iso(now()), ...safeError(error) };
      evidence.blockers.push(name+':'+evidence.endpoints[name].code);
      return null;
    }
  }
  const profile = raw => {
    const p = unwrap(raw);
    need(String(p.dhanClientId) === String(broker.clientId), 'ACCOUNT_IDENTITY_MISMATCH');
    return { identity_verified: true }; // No profile PII or credentials in persisted envelope.
  };
  const funds = raw => {
    const f = unwrap(raw);
    return { available_rupees: num(f.availabelBalance ?? f.availableBalance) };
  };
  const positions = raw => arrayRows(raw, positionFields).map(r => { positionKey(r); return r; });
  const orders = raw => arrayRows(raw, orderFields).map(r => { orderKey(r); return r; });
  const prof = await record('profile_before', () => broker.getProfile(), profile);
  if (prof) {
    await Promise.all([
      record('positions_before', () => broker.getPositions(), positions),
      record('orders_before', () => broker.getOrders(), orders),
      record('funds_before', () => broker.getFunds(), funds),
      record('trades', () => broker.getTrades(), r => arrayRows(r, tradeFields))
    ]);
  }
  const initialHealthy = prof && ['positions_before','orders_before','funds_before','trades'].every(n => evidence.endpoints[n]?.status === 'OK');
  if (scope === 'MARKET' && initialHealthy) {
    need(master && chainSpacingMs >= 3000, 'MASTER_AND_RATE_SPACING_REQUIRED');
    let lastChainRequest = -Infinity;
    async function spaced(fn) {
      const delay = Math.max(0, chainSpacingMs - (now() - lastChainRequest));
      if (delay) await wait(delay);
      lastChainRequest = now();
      return fn();
    }
    for (const symbol of SYMBOLS) {
      const resolved = await record(symbol+':resolver', () => master.resolveIndex(symbol), r => {
        need(r.symbol === symbol && Number.isInteger(r.underlyingScrip) && r.underlyingScrip > 0
          && ['IDX_I','BSE_FNO'].includes(r.underlyingSeg) && r.matchedRows > 0, 'INDEX_RESOLUTION_UNVERIFIED');
        return r;
      });
      if (!resolved) { evidence.markets[symbol] = { status: 'UNAVAILABLE' }; continue; }
      const expiries = await record(symbol+':expiries', () => spaced(() => broker.getOptionExpiries(resolved)), r => {
        const rows = unwrap(r);
        need(Array.isArray(rows) && rows.every(x => typeof x === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(x)), 'INVALID_EXPIRY_LIST');
        const active = [...new Set(rows)].filter(x => x >= day(now())).sort();
        need(active.length > 0, 'NO_ACTIVE_EXPIRY');
        return active;
      });
      if (!expiries) { evidence.markets[symbol] = { status: 'UNAVAILABLE' }; continue; }
      const expiry = expiries[0];
      const snapshot = await record(symbol+':chain', () => spaced(() => broker.getOptionChain({ ...resolved, expiry })), raw => {
        unwrap(raw); // Reject HTTP-200 error envelopes before legacy normalization.
        const normalized = normalizeDhanChain(raw, { symbol, expiry, retrievedAt: iso(now()) });
        need(Number.isFinite(normalized.underlying_value) && normalized.underlying_value > 0 && normalized.chain.length > 0, 'INVALID_CHAIN');
        return normalized;
      });
      evidence.markets[symbol] = { status: snapshot ? 'OBSERVED_UNVERIFIED_FRESHNESS' : 'UNAVAILABLE', expiry,
        clock_basis: 'RECEIPT_ONLY', exchange_quote_clock_verified: false,
        exact_contract_lot_sizes_verified: false, normalized_snapshot: snapshot };
    }
  }
  if (scope === 'POSITION' && initialHealthy) {
    const instruments = evidence.endpoints.positions_before.data.filter(r => num(r.netQty) !== 0)
      .map(r => ({ exchangeSegment: r.exchangeSegment, securityId: String(r.securityId) }));
    if (instruments.length) {
      await record('position_quotes', () => broker.getQuote(instruments), raw => {
        const data = unwrap(raw);
        return instruments.map(i => {
          const q = data[i.exchangeSegment]?.[i.securityId];
          need(q && typeof q === 'object', 'POSITION_QUOTE_MISSING');
          return { ...i, last_trade_time: q.last_trade_time ?? null,
            bid: q.depth?.buy?.[0]?.price ?? null, ask: q.depth?.sell?.[0]?.price ?? null,
            bid_size: q.depth?.buy?.[0]?.quantity ?? null, ask_size: q.depth?.sell?.[0]?.quantity ?? null };
        });
      });
    }
  }
  if (initialHealthy) {
    await Promise.all([
      record('profile_after', () => broker.getProfile(), profile),
      record('positions_after', () => broker.getPositions(), positions),
      record('orders_after', () => broker.getOrders(), orders),
      record('funds_after', () => broker.getFunds(), funds)
    ]);
  }
  const required = ['profile_before','profile_after','positions_before','positions_after',
    'orders_before','orders_after','funds_before','funds_after','trades'];
  const healthy = required.every(n => evidence.endpoints[n]?.status === 'OK');
  if (healthy) {
    const data = n => evidence.endpoints[n].data;
    const p = data('positions_after'), o = data('orders_after');
    const same = sha256(sorted(data('positions_before').map(positionKey))) === sha256(sorted(p.map(positionKey)))
      && sha256(sorted(data('orders_before'))) === sha256(sorted(o))
      && data('funds_before').available_rupees === data('funds_after').available_rupees;
    const end = now();
    const fresh = required.every(n => end-Date.parse(evidence.endpoints[n].requested_at) <= 30000);
    if (!same) evidence.blockers.push('ACCOUNT_CHANGED_DURING_COLLECTION');
    if (!fresh) evidence.blockers.push('ACCOUNT_EVIDENCE_WINDOW_EXCEEDED');
    if (same && fresh) {
      const openPositions = p.filter(r => num(r.netQty) !== 0);
      const pendingOrders = o.filter(r => !TERMINAL.has(r.orderStatus));
      evidence.account = { verified: true, verified_at: iso(end), verified_flat: !openPositions.length && !pendingOrders.length,
        open_position_count: openPositions.length, pending_order_count: pendingOrders.length,
        available_rupees: data('funds_after').available_rupees, ownership: 'UNASSIGNED',
        fingerprint: sha256([sorted(p.map(positionKey)), sorted(o), data('funds_after')]) };
    }
  }
  evidence.completed_at = iso(now());
  evidence.status = !evidence.account.verified ? 'ACCOUNT_UNVERIFIED'
    : scope === 'MARKET' && SYMBOLS.some(s => !evidence.markets[s]?.normalized_snapshot) ? 'PARTIAL_MARKET_DATA'
    : 'READ_ONLY_CAPTURED';
  evidence.trading_ready = false;
  return evidence;
}

async function privateDirectory(root, directory) {
  const target = resolve(directory), base = resolve(root);
  const rel = relative(base, target);
  need(!rel.startsWith('..'+sep) && rel !== '..' && !rel.startsWith(sep), 'EVIDENCE_OUTSIDE_PRIVATE_ROOT');
  await mkdir(base, { recursive: true, mode: 0o700 });
  const baseStat = await lstat(base);
  need(baseStat.isDirectory() && !baseStat.isSymbolicLink() && !(baseStat.mode & 0o077)
    && baseStat.uid === process.getuid(), 'PRIVATE_ROOT_PERMISSIONS_REQUIRED');
  need(await realpath(base) === base, 'SYMLINKED_EVIDENCE_ROOT_REJECTED');
  let current = base;
  for (const part of rel.split(sep).filter(Boolean)) {
    current = join(current, part);
    try { await mkdir(current, { mode: 0o700 }); } catch (e) { if (e.code !== 'EEXIST') throw e; }
    const st = await lstat(current);
    need(st.isDirectory() && !st.isSymbolicLink() && !(st.mode & 0o077), 'PRIVATE_EVIDENCE_DIRECTORY_REQUIRED');
  }
  return target;
}

async function writeExclusive(file, text) {
  const tmp = file+'.'+randomUUID()+'.tmp';
  try {
    const f = await open(tmp, 'wx', 0o600);
    try { await f.writeFile(text); await f.sync(); } finally { await f.close(); }
    // Atomic no-overwrite publication, including against a pre-existing symlink.
    await link(tmp, file);
    const dir = await open(dirname(file), 'r');
    try { await dir.sync(); } finally { await dir.close(); }
  } finally { await unlink(tmp).catch(e => { if (e.code !== 'ENOENT') throw e; }); }
}

export async function saveWorkflowEvidence(evidence, root) {
  need(evidence.format === FORMAT && evidence.provenance === 'OBSERVED' && evidence.mode === 'READ_ONLY', 'OBSERVED_EVIDENCE_REQUIRED');
  need(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(evidence.collection_id), 'INVALID_COLLECTION_ID');
  const directory = await privateDirectory(root, root);
  const file = join(directory, evidence.collection_id+'.json');
  const content = JSON.stringify(evidence, null, 2)+'\n';
  await writeExclusive(file, content);
  const manifest = { format: FORMAT+'.manifest', provenance: 'OBSERVED', mode: 'READ_ONLY',
    collection_id: evidence.collection_id, evidence_file: file, sha256: sha256(content),
    completed_at: evidence.completed_at };
  const manifestFile = join(directory, evidence.collection_id+'.manifest.json');
  await writeExclusive(manifestFile, JSON.stringify(manifest, null, 2)+'\n');
  return { manifest_file: manifestFile, sha256: manifest.sha256 };
}
