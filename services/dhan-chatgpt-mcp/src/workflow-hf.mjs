// Bounded five-minute read-only sampler. No scheduler or executor.
import { randomUUID } from 'node:crypto';
import { FORMAT, SYMBOLS } from './workflow-data.mjs';
const need = (ok, message) => { if (!ok) throw new Error(message); };
const field = (r, keys) => keys.map(k => r[k]).find(v => v !== undefined && v !== '');
const expiry = r => String(field(r, ['SM_EXPIRY_DATE', 'SEM_EXPIRY_DATE', 'EXPIRY_DATE']) ?? '').slice(0,10);
export function resolveFutures(rows, day) {
  return SYMBOLS.map(symbol => {
    const exchange = symbol === 'SENSEX' ? 'BSE' : 'NSE';
    const matches = rows.filter(r =>
      field(r, ['UNDERLYING_SYMBOL', 'SEM_UNDERLYING_SYMBOL']) === symbol &&
      String(field(r, ['INSTRUMENT_TYPE', 'SEM_EXCH_INSTRUMENT_TYPE', 'INSTRUMENT'])).toUpperCase().includes('FUT') &&
      field(r, ['EXCH_ID', 'SEM_EXM_EXCH_ID']) === exchange &&
      /^\d{4}-\d{2}-\d{2}$/.test(expiry(r)) && Number.isFinite(Date.parse(expiry(r))) && expiry(r) >= day
    ).sort((a,b) => String(field(a,['SM_EXPIRY_DATE','SEM_EXPIRY_DATE','EXPIRY_DATE'])).localeCompare(String(field(b,['SM_EXPIRY_DATE','SEM_EXPIRY_DATE','EXPIRY_DATE']))));
    need(matches.length > 0, 'FUTURE_UNRESOLVED_'+symbol);
    const r = matches[0], securityId = String(field(r, ['SECURITY_ID', 'SEM_SMST_SECURITY_ID']));
    need(/^\d+$/.test(securityId), 'FUTURE_ID_INVALID');
    return { symbol, exchangeSegment: exchange+'_FNO', securityId,
      expiry: String(field(r,['SM_EXPIRY_DATE','SEM_EXPIRY_DATE','EXPIRY_DATE'])).slice(0,10) };
  });
}
function quoteTime(value) {
  // Dhan's offset-less exchange timestamps are Indian exchange local time.
  if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d/.test(value)) return NaN;
  const s = value.replace(' ', 'T');
  return Date.parse(/(Z|[+-]\d\d:\d\d)$/.test(s) ? s : s+'+05:30');
}
export async function collectHF({ broker, instruments, now = Date.now, wait = ms => new Promise(r=>setTimeout(r,ms)) }) {
  need(instruments.length === 3 && new Set(instruments.map(x=>x.symbol)).size === 3 && instruments.every(x=>SYMBOLS.includes(x.symbol)), 'ALL_THREE_FUTURES_REQUIRED');
  const start = now(), quotes = Object.fromEntries(SYMBOLS.map(s=>[s,[]])), failures = [];
  for (let i=0; i<=150; i++) {
    const target = start+i*2000;
    if (now()<target) await wait(target-now());
    if (now()-start>315000) break;
    const began = now();
    try {
      const raw = await broker.getQuote(instruments);
      need(raw?.status === 'success', 'HF_BROKER_RESPONSE_INVALID');
      const received = now();
      need(received-began<=5000, 'HF_REQUEST_TOO_SLOW');
      for (const instrument of instruments) {
        const q = raw.data?.[instrument.exchangeSegment]?.[instrument.securityId];
        if (!q) continue;
        const trade = quoteTime(q.last_trade_time);
        const bid = Number(q.depth?.buy?.[0]?.price), ask = Number(q.depth?.sell?.[0]?.price);
        if (!(Number.isFinite(trade) && received-trade>=0 && received-trade<=30000 && bid>0 && ask>=bid)) continue;
        if (!(Number(q.depth.buy[0].quantity)>0 && Number(q.depth.sell[0].quantity)>0)) continue;
        quotes[instrument.symbol].push({timestamp:new Date(received).toISOString(), bid, ask,
          exchange_time:new Date(trade).toISOString(), requested_at:new Date(began).toISOString()});
      }
    } catch (error) {
      failures.push({sample:i, code:'HF_SAMPLE_UNAVAILABLE'});
      if (error?.status === 401 || error?.status === 403 || failures.length>=5) break;
    }
  }
  return {format:FORMAT, mode:'READ_ONLY', provenance:'OBSERVED', scope:'HF', collection_id:randomUUID(),
    started_at:new Date(start).toISOString(), completed_at:new Date(now()).toISOString(),
    instruments, hf_quotes:quotes, failures, trading_ready:false,
    capabilities:{orders:false,scheduling:false,financial_ledger:false},
    clock_limitation:'REST receipt clock; last trade is a freshness proxy, not a separate book clock'};
}
