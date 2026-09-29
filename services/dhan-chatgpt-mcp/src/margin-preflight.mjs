import * as z from 'zod/v4';
import { createHash } from 'node:crypto';

const positive = z.number().finite().positive();
export const marginLegSchema = z.object({
  exchangeSegment: z.enum(['NSE_FNO', 'BSE_FNO']),
  transactionType: z.enum(['BUY', 'SELL']),
  quantity: z.number().int().positive(),
  productType: z.literal('INTRADAY'),
  securityId: z.string().regex(/^\d+$/),
  price: positive,
  triggerPrice: z.literal(0).default(0)
}).strict();
export const basketMarginSchema = z.object({
  legs: z.array(marginLegSchema).min(1).max(25)
}).strict();
export const butterflyMarginSchema = z.object({
  symbol: z.enum(['NIFTY', 'BANKNIFTY', 'SENSEX']),
  expiry: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  lower: positive, center: positive, upper: positive,
  lots: z.number().int().positive().max(100),
  entrySequence: z.enum(['WINGS_FIRST', 'PAIRED_HEDGES']).default('WINGS_FIRST')
    .describe('Bind preflight to the actual entry order. PAIRED_HEDGES matches the separate iron-butterfly executor.'),
  reserveRupees: z.number().finite().nonnegative().optional()
    .describe('Explicit user-approved free-cash reserve. Omission prevents PASS; zero must be explicitly approved.'),
  reservePercent: z.number().finite().min(0).max(100).optional()
    .describe('Explicit user-approved percentage of available funds to retain. If both reserves supplied, larger wins.')
}).strict();
const need = (condition, message) => { if (!condition) throw new Error(message); };
export function numeric(v, label) {
  need((typeof v === 'number' || typeof v === 'string') && String(v).trim() !== '' && Number.isFinite(Number(v)), `Missing/invalid ${label}`);
  return Number(v);
}
export function unwrap(raw) {
  need(raw && !['failure', 'failed', 'error'].includes(String(raw.status).toLowerCase()) && !raw.errorCode && !raw.errorType, 'Dhan returned an error payload');
  return raw.data ?? raw;
}
export function normalizeMargin(raw) {
  const r = unwrap(raw);
  const total = numeric(r.totalMargin ?? r.total_margin, 'basket total margin');
  need(total >= 0, 'Negative basket margin is not supported');
  return { totalMarginRupees: total, indicative: true };
}
export async function basketMargin(broker, input) {
  const { legs } = basketMarginSchema.parse(input);
  const result = normalizeMargin(await broker.getBasketMargin(legs));
  return { ...result, asof: new Date().toISOString(), includePosition: true, includeOrder: true,
    affordabilityStatus: 'UNVERIFIED', reason: 'Basket total alone does not establish sequence affordability.' };
}

function fingerprint(rows) {
  const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map(k => [k, stable(value[k])])) : value;
  return createHash('sha256').update(JSON.stringify(rows.map(stable).sort((a,b) => JSON.stringify(a).localeCompare(JSON.stringify(b))))).digest('hex');
}
async function account(broker) {
  const [fr, pr, or] = await Promise.all([broker.getFunds(), broker.getPositions(), broker.getOrders()]);
  const f = unwrap(fr), p = unwrap(pr), o = unwrap(or);
  need(Array.isArray(p) && Array.isArray(o), 'Positions/orders unavailable');
  const available = numeric(f.availabelBalance ?? f.availableBalance, 'available trading balance');
  // Compare position quantities/identity, not fluctuating mark-to-market prices.
  const exposure = p.map(v => ({ securityId: v.securityId, exchangeSegment: v.exchangeSegment,
    productType: v.productType, netQty: numeric(v.netQty, 'position quantity') }));
  const orders = o.map(v => ({ orderId: v.orderId, orderStatus: v.orderStatus, securityId: v.securityId,
    quantity: v.quantity, filledQty: v.filledQty, remainingQuantity: v.remainingQuantity, price: v.price }));
  const terminal = new Set(['TRADED', 'CANCELLED', 'REJECTED', 'EXPIRED']);
  return { available, fingerprint: fingerprint([...exposure, ...orders]),
    openPositions: exposure.filter(v => v.netQty !== 0).length,
    pendingOrders: o.filter(v => !terminal.has(v.orderStatus)).length };
}

async function resolveButterfly(master, input) {
  need(input.lower < input.center && input.center < input.upper, 'Require lower < center < upper');
  const rows = await master.getRows({ force: true });
  const exchange = input.symbol === 'SENSEX' ? 'BSE' : 'NSE';
  // Each short must follow its own fully filled protective wing in either path.
  // This calculator models prefixes, not execution or partial-fill assurance.
  const specs = input.entrySequence === 'PAIRED_HEDGES'
    ? [['putWing', input.lower, 'PE', 'BUY'], ['putBody', input.center, 'PE', 'SELL'],
       ['callWing', input.upper, 'CE', 'BUY'], ['callBody', input.center, 'CE', 'SELL']]
    : [['putWing', input.lower, 'PE', 'BUY'], ['callWing', input.upper, 'CE', 'BUY'],
       ['putBody', input.center, 'PE', 'SELL'], ['callBody', input.center, 'CE', 'SELL']];
  const legs = specs.map(([role, strike, type, side]) => {
    const matches = rows.filter(r => r.EXCH_ID === exchange && r.SEGMENT === 'D' && r.INSTRUMENT === 'OPTIDX'
      && r.UNDERLYING_SYMBOL === input.symbol && r.SM_EXPIRY_DATE?.slice(0,10) === input.expiry
      && Number(r.STRIKE_PRICE) === strike && r.OPTION_TYPE === type);
    need(matches.length === 1, `Contract not uniquely resolved: ${role}`);
    const r = matches[0], lot = numeric(r.LOT_SIZE, 'lot size');
    const quantity = lot * input.lots;
    need(Number.isInteger(lot) && lot > 0 && Number.isSafeInteger(quantity), 'Invalid lot size/quantity');
    need(quantity <= numeric(r.SM_FREEZE_QTY, 'freeze quantity'), 'Quantity above freeze limit; slicing needs a separate sequence check');
    need(r.BUY_SELL_INDICATOR === 'A' && /^\d+$/.test(r.SECURITY_ID), 'Contract not enabled or invalid ID');
    return { role, strike, optionType: type, lotSize: lot, exchangeSegment: `${exchange}_FNO`,
      transactionType: side, quantity, productType: 'INTRADAY', securityId: r.SECURITY_ID, triggerPrice: 0 };
  });
  need(legs.every(l => l.lotSize === legs[0].lotSize) && new Set(legs.map(l => l.securityId)).size === 4, 'Inconsistent contracts');
  return legs;
}
function quoteTime(value) {
  const m = /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}:\d{2}:\d{2})$/.exec(String(value));
  if (m) return Date.parse(`${m[3]}-${m[2]}-${m[1]}T${m[4]}+05:30`);
  const s = String(value ?? '').replace(' ', 'T');
  return Date.parse(/Z$|[+-]\d\d:\d\d$/.test(s) ? s : `${s}+05:30`);
}
function wireLeg({ exchangeSegment, transactionType, quantity, productType, securityId, price, triggerPrice }) {
  return marginLegSchema.parse({ exchangeSegment, transactionType, quantity, productType, securityId, price, triggerPrice });
}

export async function checkButterflyMargin(broker, master, args, { now = Date.now } = {}) {
  const started = now();
  const output = { status: 'UNVERIFIED', asof: new Date(started).toISOString(), indicative: true,
    scope: 'ENTRY_ONLY', blockers: [], stages: [],
    methodology: 'Maximum of Dhan account-inclusive basket totals across wings-first prefixes, compared conservatively with free funds. No subtraction of utilised margin, no additional premium charge on top of broker totals.' };
  try {
    const input = butterflyMarginSchema.parse(args);
    output.entrySequence = input.entrySequence;
    output.methodology = `Maximum of Dhan account-inclusive basket totals across ${input.entrySequence} prefixes, compared conservatively with free funds. No subtraction of utilised margin, no additional premium charge on top of broker totals.`;
    output.candidate = Object.fromEntries(['symbol', 'expiry', 'lower', 'center', 'upper', 'lots'].map(k => [k, input[k]]));
    const before = await account(broker);
    output.availableFundsRupees = before.available;
    if (before.pendingOrders) output.blockers.push('Outstanding/unknown-status orders: reconcile before entry; unfilled hedges cannot fund entry.');
    const legs = await resolveButterfly(master, input);
    const quotes = unwrap(await broker.getQuote(legs));
    const local = new Date(started + 19800000);
    const minutes = local.getUTCHours() * 60 + local.getUTCMinutes();
    if ([0,6].includes(local.getUTCDay()) || minutes < 555 || minutes >= 900)
      output.blockers.push('Outside permitted entry window (09:15–15:00 IST weekdays); indicative diagnostic only.');
    if (input.expiry < local.toISOString().slice(0,10)) output.blockers.push('Expired contracts.');
    for (const leg of legs) {
      const q = quotes?.[leg.exchangeSegment]?.[leg.securityId];
      const bid = numeric(q?.depth?.buy?.[0]?.price, 'bid'), ask = numeric(q?.depth?.sell?.[0]?.price, 'ask');
      need(bid > 0 && ask >= bid, 'Missing/crossed executable book');
      const buy = leg.transactionType === 'BUY', best = q.depth[buy ? 'sell' : 'buy'][0];
      need(numeric(best.quantity, 'top-of-book quantity') >= leg.quantity, 'Insufficient top-of-book size for requested lots');
      leg.price = buy ? ask : bid;
      const quoteMs = quoteTime(q.last_trade_time);
      leg.quoteAsOf = Number.isFinite(quoteMs) ? new Date(quoteMs).toISOString() : null;
      const age = now() - quoteMs;
      if (!Number.isFinite(age) || age < -2000 || age > 30000) output.blockers.push(`Stale/unavailable quote timestamp: ${leg.role}`);
    }
    output.legs = legs;
    output.sequence = legs.map(l => l.role);
    for (let i = 1; i <= legs.length; i++) {
      const m = normalizeMargin(await broker.getBasketMargin(legs.slice(0,i).map(wireLeg)));
      output.stages.push({ throughLeg: legs[i-1].role, ...m });
    }
    const after = await account(broker);
    output.availableFundsRupees = Math.min(before.available, after.available);
    if (before.fingerprint !== after.fingerprint || before.available !== after.available)
      output.blockers.push('Account changed during preflight; refresh the entire check.');
    if (now() - started > 30000) output.blockers.push('Preflight exceeded 30 seconds; snapshot no longer coherent.');
    output.peakRequiredRupees = Math.max(...output.stages.map(s => s.totalMarginRupees));
    if (output.peakRequiredRupees <= 0) output.blockers.push('Zero margin for nonempty option basket; broker evidence unusable.');
    output.finalRequiredRupees = output.stages.at(-1).totalMarginRupees;
    output.existingPositionCount = after.openPositions;
    output.rawHeadroomRupees = output.availableFundsRupees - output.peakRequiredRupees;
    if (input.reserveRupees === undefined && input.reservePercent === undefined) {
      output.blockers.push('Free-cash reserve policy not supplied; do not invent user capital/risk limits.');
    } else {
      output.reserveRupees = Math.max(input.reserveRupees ?? 0, Math.max(0,output.availableFundsRupees) * (input.reservePercent ?? 0) / 100);
      output.headroomAfterReserveRupees = output.rawHeadroomRupees - output.reserveRupees;
    }
    output.validUntil = new Date(started + 30000).toISOString();
    output.status = output.blockers.length ? 'UNVERIFIED'
      : output.headroomAfterReserveRupees < 0 ? 'FAIL' : 'PASS';
    output.reason = output.status === 'PASS' ? 'Indicative entry affordability only; recheck if prices, size, sequence, funds or positions change.'
      : output.status === 'FAIL' ? 'Insufficient available funds for sequence plus approved reserve.' : 'Missing/stale/ambiguous evidence; not approved.';
    return output;
  } catch (error) {
    // Do not surface broker payloads, credentials or identifiers from API error text.
    output.blockers.push(error?.name === 'DhanApiError' ? `Dhan margin/account service unavailable (HTTP ${error.status ?? 'unknown'}).` : error.message);
    return output;
  }
}
