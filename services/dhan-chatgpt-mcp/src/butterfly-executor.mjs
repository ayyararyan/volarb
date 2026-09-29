import * as z from 'zod/v4';
import { randomUUID, createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, renameSync, openSync, fsyncSync, closeSync } from 'node:fs';
import { join } from 'node:path';
import { canonicalIndexSymbol } from './instrument-master.mjs';

const ROLES = ['putWing', 'putBody', 'callWing', 'callBody'];
const TERMINAL = new Set(['TRADED', 'CANCELLED', 'REJECTED', 'EXPIRED']);
const STATUSES = new Set([...TERMINAL, 'TRANSIT', 'PENDING', 'PART_TRADED']);
const positive = z.number().finite().positive();
export const planSchema = z.object({
  action: z.enum(['ENTRY', 'EXIT']),
  symbol: z.enum(['NIFTY', 'BANKNIFTY', 'SENSEX']),
  expiry: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  lower: positive, center: positive, upper: positive,
  lots: z.number().int().positive().max(100),
  // For buys: maximum premium; for sells: minimum premium, in rupees/unit.
  limits: z.object(Object.fromEntries(ROLES.map(r => [r, positive]))).strict(),
  waitSeconds: z.number().int().min(3).max(30).default(8),
  maxReprices: z.number().int().min(0).max(10).default(3),
  stepTicks: z.number().int().min(1).max(20).default(1),
  improveTicks: z.number().int().min(0).max(10).default(1),
  maxSpreadBps: z.number().int().min(1).max(5000).default(1500),
  maxQuoteAgeSeconds: z.number().int().min(1).max(30).default(15),
  maxDurationSeconds: z.number().int().min(30).max(600).default(180)
}).strict();
const unwrap = r => {
  need(r !== null && r !== undefined && !['failure', 'failed', 'error'].includes(String(r.status).toLowerCase()) && !r.errorCode && !r.errorType, 'Unavailable or failed broker response');
  return r?.data ?? r;
};
const need = (condition, message) => { if (!condition) throw new Error(message); };
const number = (v, name) => { need((typeof v === 'number' || typeof v === 'string') && String(v).trim() !== '' && Number.isFinite(Number(v)), `Missing/invalid ${name}`); return Number(v); };
const array = (r, name) => { const a = unwrap(r); need(Array.isArray(a), `Unavailable ${name}`); return a; };
export function ist(now) { return new Date(now + 19800000).toISOString(); }
export function checkSession(action, now, duration = 0) {
  const local = new Date(now + 19800000);
  const mins = local.getUTCHours() * 60 + local.getUTCMinutes() + local.getUTCSeconds() / 60;
  need(![0, 6].includes(local.getUTCDay()) && mins >= 555 && mins < 930, 'Outside regular exchange session; no AMO');
  // Reserve five minutes before the personal 15:00 flat deadline. Exits remain possible after it.
  if (action === 'ENTRY') need(mins + duration / 60 < 895, 'Entry window closed: finish before 14:55 IST; flat by 15:00');
}
export function roundTick(value, tick, up) {
  return Number(((up ? Math.ceil(value / tick - 1e-8) : Math.floor(value / tick + 1e-8)) * tick).toFixed(8));
}
export function quoteTime(value) {
  const m = /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}:\d{2}:\d{2})$/.exec(String(value));
  if (m) return Date.parse(`${m[3]}-${m[2]}-${m[1]}T${m[4]}+05:30`);
  // Broker ISO timestamps without a zone are in IST, not machine-local time.
  const s = String(value ?? '').replace(' ', 'T');
  return Date.parse(/Z$|[+-]\d\d:\d\d$/.test(s) ? s : `${s}+05:30`);
}
export function priceFor(leg, quote, input, attempt, now, remaining = leg.quantity) {
  const bid = number(quote?.depth?.buy?.[0]?.price, 'bid');
  const ask = number(quote?.depth?.sell?.[0]?.price, 'ask');
  need(bid > 0 && ask >= bid, 'Invalid/crossed option book');
  const age = now - quoteTime(quote.last_trade_time);
  need(Number.isFinite(age) && age >= -2000 && age <= input.maxQuoteAgeSeconds * 1000, 'Stale or missing quote trade timestamp');
  need((ask - bid) / ((bid + ask) / 2) * 10000 <= input.maxSpreadBps, 'Option spread exceeds approved limit');
  const buy = leg.side === 'BUY';
  const depth = quote.depth[buy ? 'sell' : 'buy'];
  need(depth.reduce((s, d) => s + (Number(d.price) > 0 ? Number(d.quantity) || 0 : 0), 0) >= remaining, 'Insufficient displayed executable-side depth');
  const offset = (input.improveTicks + attempt * input.stepTicks) * leg.tick;
  let p = buy ? Math.min(bid + offset, ask, leg.limit) : Math.max(ask - offset, bid, leg.limit);
  p = roundTick(p, leg.tick, !buy);
  const lo = number(quote.lower_circuit_limit, 'lower circuit');
  const hi = number(quote.upper_circuit_limit, 'upper circuit');
  need(p > 0 && p >= lo && p <= hi, 'Limit outside exchange price band');
  need(buy ? p <= leg.limit : p >= leg.limit, 'Price exceeds approved leg limit');
  return p;
}

export async function resolveLegs(master, input) {
  need(input.lower < input.center && input.center < input.upper, 'Require lower < center < upper');
  const symbol = canonicalIndexSymbol(input.symbol);
  const exchange = symbol === 'SENSEX' ? 'BSE' : 'NSE';
  const rows = await master.getRows({ force: true });
  const specs = [['putWing', input.lower, 'PE', 'BUY'], ['putBody', input.center, 'PE', 'SELL'], ['callWing', input.upper, 'CE', 'BUY'], ['callBody', input.center, 'CE', 'SELL']];
  const legs = specs.map(([role, strike, type, side]) => {
    const matches = rows.filter(r => r.EXCH_ID === exchange && r.SEGMENT === 'D' && r.INSTRUMENT === 'OPTIDX' && r.UNDERLYING_SYMBOL === symbol && r.SM_EXPIRY_DATE?.slice(0, 10) === input.expiry && Number(r.STRIKE_PRICE) === strike && r.OPTION_TYPE === type);
    need(matches.length === 1, `Contract not uniquely resolved: ${role}`);
    const r = matches[0];
    const lot = number(r.LOT_SIZE, 'lot size');
    // Dhan detailed instrument master expresses TICK_SIZE in paise (5 => Rs 0.05).
    const tick = number(r.TICK_SIZE, 'tick size') / 100;
    const freeze = number(r.SM_FREEZE_QTY, 'freeze quantity');
    const quantity = lot * input.lots;
    need(Number.isInteger(lot) && lot > 0 && tick > 0 && Number.isInteger(quantity) && quantity <= freeze, 'Invalid lot/tick or quantity above freeze limit; splitting not supported');
    need(r.BUY_SELL_INDICATOR === 'A', 'Contract not enabled for both directions');
    need(/^\d+$/.test(r.SECURITY_ID), 'Invalid security ID');
    return { role, strike, type, side: input.action === 'EXIT' ? (side === 'BUY' ? 'SELL' : 'BUY') : side,
      securityId: r.SECURITY_ID, exchangeSegment: `${exchange}_FNO`, lot, tick, quantity, limit: input.limits[role] };
  });
  need(legs.every(l => l.lot === legs[0].lot) && new Set(legs.map(l => l.securityId)).size === 4, 'Inconsistent contract lot sizes/IDs');
  return input.action === 'EXIT' ? legs.reverse() : legs;
}

// Operational write-ahead state, NOT the user's financial/P&L ledger.
export class ExecutionStore {
  constructor(dir) {
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    this.dir = dir; this.path = join(dir, 'state.json');
    try { this.data = JSON.parse(readFileSync(this.path, 'utf8')); }
    catch (e) { if (e.code !== 'ENOENT') throw e; this.data = { version: 1, jobs: {} }; }
    need(this.data.version === 1 && this.data.jobs && typeof this.data.jobs === 'object', 'Invalid executor state');
  }
  save() {
    const temp = `${this.path}.tmp`;
    writeFileSync(temp, JSON.stringify(this.data, null, 2), { mode: 0o600 });
    const fd = openSync(temp, 'r'); try { fsyncSync(fd); } finally { closeSync(fd); }
    renameSync(temp, this.path);
    const dirfd = openSync(this.dir, 'r'); try { fsyncSync(dirfd); } finally { closeSync(dirfd); }
  }
}

export class ButterflyExecutor {
  constructor({ broker, master, store, enabled = false, readiness = async () => { throw new Error('Live readiness not configured'); }, now = Date.now, sleep = ms => new Promise(r => setTimeout(r, ms)) }) {
    Object.assign(this, { broker, master, store, enabled, readiness, now, sleep });
    this.worker = null; this.busy = false;
    for (const job of Object.values(store.data.jobs)) {
      if (job.status === 'RUNNING') { job.status = 'RECOVERY_REQUIRED'; job.reason = 'Process restarted; reconcile broker orders before proceeding'; }
    }
    store.save();
  }
  job(id) { const j = this.store.data.jobs[id]; need(j, 'Unknown plan ID'); return j; }
  status(id) { return structuredClone(id ? this.job(id) : Object.values(this.store.data.jobs).map(j => ({ id: j.id, action: j.input.action, status: j.status, reason: j.reason, createdAt: j.createdAt }))); }
  save(job, event, details = {}) {
    job.updatedAt = new Date(this.now()).toISOString();
    job.events.push({ at: job.updatedAt, event, ...details });
    this.store.save();
  }
  async exclusive(fn) {
    need(!this.busy && !this.worker, 'Another executor operation is active'); this.busy = true;
    try { return await fn(); } finally { this.busy = false; }
  }
  async account(legs, ownOrderIds = []) {
    const positions = array(await this.broker.getPositions(), 'positions');
    const orders = array(await this.broker.getOrders(), 'orders');
    const own = new Set(ownOrderIds);
    // Serialize account order activity. Other clients/manual trading must stay idle during a job.
    need(!orders.some(o => !TERMINAL.has(o.orderStatus) && !own.has(String(o.orderId))), 'Outstanding external/unknown order; executor blocked');
    const quantities = {};
    for (const leg of legs) {
      const matching = positions.filter(p => String(p.securityId) === leg.securityId && p.exchangeSegment === leg.exchangeSegment);
      need(matching.every(p => number(p.netQty, 'net position') === 0 || p.productType === 'INTRADAY'), 'Selected contract also has a non-intraday position');
      const current = matching.filter(p => p.productType === 'INTRADAY');
      need(current.length <= 1, 'Ambiguous duplicate position');
      quantities[leg.role] = current.length ? number(current[0].netQty, 'net position') : 0;
      need(Number.isInteger(quantities[leg.role]), 'Non-integer position quantity');
    }
    return quantities;
  }
  hedge(q) {
    need(q.putWing >= 0 && q.callWing >= 0 && q.putBody <= 0 && q.callBody <= 0, 'Unexpected position direction');
    need(q.putWing >= -q.putBody && q.callWing >= -q.callBody, 'Hedge deficit: body exceeds corresponding owned wing');
  }
  async quotes(legs) {
    if (this.lastQuoteAt !== undefined) {
      const wait = 1100 - (this.now() - this.lastQuoteAt);
      if (wait > 0) await this.sleep(wait);
    }
    const start = this.now(); this.lastQuoteAt = start;
    const data = unwrap(await this.broker.getQuote(legs));
    need(this.now() - start <= 5000, 'Quote request too slow');
    return Object.fromEntries(legs.map(l => { const q = data?.[l.exchangeSegment]?.[l.securityId]; need(q, `Missing quote: ${l.role}`); return [l.role, q]; }));
  }
  async preview(raw) {
    return this.exclusive(async () => {
      const input = planSchema.parse(raw);
      checkSession(input.action, this.now(), input.action === 'ENTRY' ? input.maxDurationSeconds : 0);
      need(input.expiry >= ist(this.now()).slice(0, 10), 'Expired option contract');
      this.assertNoUncertainJobs();
      const legs = await resolveLegs(this.master, input);
      const baseline = await this.account(legs);
      this.hedge(baseline);
      if (input.action === 'ENTRY') need(Object.values(baseline).every(q => q === 0), 'Entry requires selected contracts to be flat; no shared wing inventory');
      else {
        need(Object.values(baseline).some(q => q !== 0), 'No selected intraday exposure to close');
        for (const leg of legs) {
          need(Math.abs(baseline[leg.role]) <= leg.quantity, 'Position exceeds requested lots; cannot isolate this exit');
          leg.quantity = Math.abs(baseline[leg.role]);
        }
      }
      const quotes = await this.quotes(legs.filter(l => l.quantity));
      const indicative = legs.filter(l => l.quantity).map(l => ({ role: l.role, side: l.side, quantity: l.quantity, initialLimit: priceFor(l, quotes[l.role], input, 0, this.now()), worstLimit: l.limit }));
      const id = randomUUID();
      const job = { id, input, legs, baseline, status: 'PREVIEW', createdAt: new Date(this.now()).toISOString(), expiresAt: this.now() + 60000, orders: [], events: [], indicative, stopRequested: false };
      job.confirmation = createHash('sha256').update(JSON.stringify({ id, input, legs, baseline })).digest('hex').slice(0, 24);
      this.store.data.jobs[id] = job;
      this.save(job, 'PREVIEW_CREATED');
      return this.status(id);
    });
  }
  assertNoUncertainJobs(except) {
    need(!Object.values(this.store.data.jobs).some(j => j.id !== except && ['RUNNING', 'RECOVERY_REQUIRED'].includes(j.status)), 'Unresolved execution exists; reconcile it first');
  }
  expected(job) {
    const q = { ...job.baseline };
    for (const o of job.orders) q[o.role] += (o.side === 'BUY' ? 1 : -1) * o.filled;
    return q;
  }
  async verify(job) {
    const actual = await this.account(job.legs);
    const expected = this.expected(job);
    need(ROLES.every(r => actual[r] === expected[r]), 'Broker positions differ from verified fills; stop and reconcile');
    this.hedge(actual);
    return actual;
  }
  async execute(id, confirmation) {
    const prior = this.job(id);
    need(prior.confirmation === confirmation, 'Confirmation must match the exact preview');
    if (prior.status !== 'PREVIEW') return this.status(id);
    return this.exclusive(async () => {
      const job = this.job(id);
      need(job.confirmation === confirmation, 'Confirmation must match the exact preview');
      // Repeated execute calls return the original run, never start a second one.
      if (job.status !== 'PREVIEW') return this.status(id);
      need(this.enabled, 'Live execution is disabled; configure static egress IP and authenticated client first');
      need(this.now() <= job.expiresAt, 'Preview expired; create a fresh plan');
      this.assertNoUncertainJobs(id);
      checkSession(job.input.action, this.now(), job.input.action === 'ENTRY' ? job.input.maxDurationSeconds : 0);
      await this.readiness();
      await this.verify(job);
      job.status = 'RUNNING'; job.deadline = this.now() + job.input.maxDurationSeconds * 1000;
      this.save(job, 'EXECUTION_STARTED');
      this.worker = this.run(job).finally(() => { this.worker = null; });
      return this.status(id);
    });
  }
  checkRun(job) {
    need(!job.stopRequested, 'User requested stop');
    need(this.now() < job.deadline, 'Execution deadline reached');
    checkSession(job.input.action, this.now());
  }
  async readOrder(job, order) {
    const raw = unwrap(order.orderId ? await this.broker.getOrder(order.orderId) : await this.broker.getOrderByCorrelation(order.correlationId));
    const leg = job.legs.find(l => l.role === order.role);
    need(raw && String(raw.correlationId) === order.correlationId && String(raw.securityId) === leg.securityId && raw.exchangeSegment === leg.exchangeSegment && raw.productType === 'INTRADAY' && raw.transactionType === order.side && raw.orderType === 'LIMIT' && String(raw.dhanClientId) === String(this.broker.clientId), 'Broker order identity mismatch');
    need(STATUSES.has(raw.orderStatus), 'Unknown broker order status');
    need(String(raw.orderId || '').length > 0 && (!order.orderId || String(raw.orderId) === order.orderId), 'Broker order ID mismatch');
    order.identityVerified = true;
    const filled = number(raw.filledQty, 'filled quantity');
    need(Number(raw.quantity) === order.quantity && Number.isInteger(filled) && filled >= order.filled && filled <= order.quantity, 'Inconsistent filled quantity');
    need(number(raw.remainingQuantity, 'remaining quantity') === order.quantity - filled, 'Inconsistent remaining quantity');
    need(raw.orderStatus !== 'TRADED' || filled === order.quantity, 'TRADED without complete fills');
    need(Math.abs(number(raw.price, 'order price') - order.price) < 1e-7, 'Order price changed externally');
    // Persist order-book truth before trade reconciliation, so a read failure cannot cause a duplicate order.
    order.orderId = String(raw.orderId); order.filled = filled; order.status = raw.orderStatus; order.reconciled = false;
    this.save(job, 'ORDER_OBSERVED', { orderId: order.orderId, status: order.status, filled });
    if (filled > 0) {
      const trades = array(await this.broker.getOrderTrades(order.orderId), 'order trades');
      const ids = new Set(); let qty = 0; let value = 0;
      for (const t of trades) {
        need(String(t.orderId) === order.orderId && String(t.securityId) === leg.securityId && t.exchangeSegment === leg.exchangeSegment && t.transactionType === order.side && t.productType === 'INTRADAY', 'Trade identity mismatch');
        const tradeId = String(t.exchangeTradeId ?? ''); need(tradeId && !ids.has(tradeId), 'Duplicate/missing trade ID'); ids.add(tradeId);
        const n = number(t.tradedQuantity, 'trade quantity'), p = number(t.tradedPrice, 'trade price');
        need(Number.isInteger(n) && n > 0 && p > 0 && (order.side === 'BUY' ? p <= order.price + 1e-7 : p >= order.price - 1e-7), 'Trade violates limit or quantity');
        qty += n; value += n * p;
      }
      need(qty === filled, 'Trades have not reconciled with order fills');
      order.trades = trades.map(t => ({ exchangeTradeId: t.exchangeTradeId, quantity: Number(t.tradedQuantity), price: Number(t.tradedPrice), exchangeTime: t.exchangeTime }));
      order.averagePrice = value / qty;
    }
    order.reconciled = true; this.save(job, 'FILLS_RECONCILED', { orderId: order.orderId });
    return order;
  }
  async settle(job, order) {
    // Best effort cancellation on every exceptional path; never assume a cancel response means cancelled.
    try { await this.readOrder(job, order); } catch (e) { if (!order.orderId || !order.identityVerified) throw e; }
    if (!TERMINAL.has(order.status)) {
      this.save(job, 'CANCEL_INTENT', { orderId: order.orderId });
      try { await this.broker.cancelOrder(order.orderId); } catch { /* verify even after a timeout */ }
      for (let n = 0; n < 5; n++) {
        await this.sleep(1000);
        try { await this.readOrder(job, order); } catch { continue; }
        if (TERMINAL.has(order.status) && order.reconciled) return;
      }
    } else if (order.reconciled) return;
    throw new Error('Order/fills remain uncertain; reconcile with Dhan before any further execution');
  }
  async margin(leg, quantity, price) {
    const funds = unwrap(await this.broker.getFunds());
    const available = number(funds?.availabelBalance ?? funds?.availableBalance, 'available funds');
    const margin = unwrap(await this.broker.getMargin({ exchangeSegment: leg.exchangeSegment, transactionType: leg.side, securityId: leg.securityId, productType: 'INTRADAY', quantity, price }));
    const required = number(margin?.totalMargin, 'required margin');
    const brokerAvailable = number(margin?.availableBalance, 'margin available');
    need(required >= 0 && Math.min(available, brokerAvailable) >= required, 'Insufficient broker-confirmed available margin');
    // Broker's own RMS is final; this conservative check does not assume sale proceeds release immediately.
    if (leg.side === 'BUY') need(Math.min(available, brokerAvailable) >= quantity * price, 'Insufficient available premium for buy');
  }
  async run(job) {
    try {
      for (const leg of job.legs) {
        if (!leg.quantity) continue;
        let filled = 0;
        for (let attempt = 0; attempt <= job.input.maxReprices && filled < leg.quantity; attempt++) {
          this.checkRun(job);
          const q = await this.verify(job);
          if (job.input.action === 'ENTRY' && leg.side === 'SELL') need(q[leg.role === 'putBody' ? 'putWing' : 'callWing'] >= leg.quantity, 'Wing not fully owned');
          if (job.input.action === 'EXIT' && leg.side === 'SELL') need(q[leg.role === 'putWing' ? 'putBody' : 'callBody'] === 0, 'Corresponding short is not fully closed');
          const quantity = leg.quantity - filled;
          const quotes = await this.quotes([leg]);
          const price = priceFor(leg, quotes[leg.role], job.input, attempt, this.now(), quantity);
          await this.margin(leg, quantity, price);
          // Recheck state after network waits, immediately before mutation.
          await this.verify(job); this.checkRun(job);
          need(this.now() - quoteTime(quotes[leg.role].last_trade_time) <= job.input.maxQuoteAgeSeconds * 1000, 'Quote expired during preflight');
          const correlationId = `bf${randomUUID().replaceAll('-', '').slice(0, 28)}`;
          const order = { correlationId, role: leg.role, side: leg.side, quantity, price, filled: 0, status: 'INTENT', reconciled: false };
          job.orders.push(order); this.save(job, 'PLACE_INTENT', { correlationId, role: leg.role, quantity, price });
          // Never retry POST after an ambiguous response. Recovery is by correlation ID only.
          const response = unwrap(await this.broker.placeLimitOrder({ correlationId, exchangeSegment: leg.exchangeSegment, transactionType: leg.side, securityId: leg.securityId, quantity, price }));
          need(response?.orderId, 'Placement response missing order ID');
          order.orderId = String(response.orderId); this.save(job, 'PLACEMENT_ACK', { orderId: order.orderId });
          const waitUntil = Math.min(job.deadline, this.now() + job.input.waitSeconds * 1000);
          do {
            await this.readOrder(job, order);
            if (TERMINAL.has(order.status)) break;
            this.checkRun(job);
            await this.sleep(Math.min(2000, Math.max(1, waitUntil - this.now())));
          } while (this.now() < waitUntil);
          await this.settle(job, order);
          filled = job.orders.filter(o => o.role === leg.role).reduce((s, o) => s + o.filled, 0);
          await this.verify(job);
          need(order.status !== 'REJECTED' && order.status !== 'EXPIRED', `Broker ${order.status.toLowerCase()} order; no next leg`);
        }
        need(filled === leg.quantity, `${leg.role} incomplete; repricing budget exhausted. Filled inventory retained; no next leg`);
      }
      await this.verify(job);
      job.status = 'COMPLETED'; this.save(job, 'EXECUTION_COMPLETED');
    } catch (error) {
      job.reason = error.message;
      let uncertain = false;
      for (const order of job.orders) {
        if (!TERMINAL.has(order.status) || !order.reconciled) {
          try { await this.settle(job, order); } catch { uncertain = true; }
        }
      }
      if (!uncertain) { try { await this.verify(job); } catch { uncertain = true; } }
      job.status = uncertain ? 'RECOVERY_REQUIRED' : 'PAUSED';
      this.save(job, job.status, { reason: job.reason });
    }
  }
  stop(id) {
    const job = this.job(id);
    if (job.status === 'RUNNING') { job.stopRequested = true; this.save(job, 'STOP_REQUESTED'); }
    return this.status(id);
  }
  async reconcile(id) {
    return this.exclusive(async () => {
      const job = this.job(id);
      need(job.status !== 'RUNNING', 'Stop running job before reconciliation');
      // Read only: a live pending order is reported, not automatically cancelled/resubmitted after restart.
      for (const order of job.orders) await this.readOrder(job, order);
      need(job.orders.every(o => TERMINAL.has(o.status) && o.reconciled), 'Live or ambiguous order remains; resolve in Dhan, then reconcile again');
      await this.verify(job);
      if (job.status === 'RECOVERY_REQUIRED') { job.status = 'PAUSED'; this.save(job, 'RECOVERY_RECONCILED'); }
      return this.status(id);
    });
  }
}
