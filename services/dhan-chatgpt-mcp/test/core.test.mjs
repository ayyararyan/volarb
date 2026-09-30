import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalIndexSymbol, parseCsv, InstrumentMaster } from '../src/instrument-master.mjs';
import { analyzeOptionSurface, inferIronButterfly, normalizeDhanChain, normalizeExpiryDate } from '../src/surface-analytics.mjs';

test('canonical aliases resolve', () => {
  assert.equal(canonicalIndexSymbol('NIFTY 50'), 'NIFTY');
  assert.equal(canonicalIndexSymbol('Nifty Bank'), 'BANKNIFTY');
  assert.equal(canonicalIndexSymbol('BSE Sensex'), 'SENSEX');
});

test('CSV parser handles quoted commas', () => {
  const rows = parseCsv('A,B,C\n1,"two, too",3\n');
  assert.deepEqual(rows, [{ A: '1', B: 'two, too', C: '3' }]);
});

test('instrument master resolves underlying id from derivative rows', async () => {
  const csv = [
    'UNDERLYING_SECURITY_ID,UNDERLYING_SYMBOL,LOT_SIZE,INSTRUMENT_TYPE,SYMBOL_NAME',
    '13,NIFTY,65,OPTIDX,NIFTY OPTION',
    '13,NIFTY,65,OPTIDX,NIFTY OPTION',
    '25,BANKNIFTY,30,OPTIDX,BANK OPTION'
  ].join('\n');
  const fetchFn = async () => ({ ok: true, text: async () => csv });
  const master = new InstrumentMaster({ fetchFn, ttlMs: 999999 });
  const r = await master.resolveIndex('NIFTY');
  assert.equal(r.underlyingScrip, 13);
  assert.equal(r.lotSize, 65);
  assert.equal(r.underlyingSeg, 'IDX_I');
});

function side({ ltp, bid, ask, iv, delta, oi = 1000, volume = 5000 }) {
  return {
    last_price: ltp,
    top_bid_price: bid,
    top_ask_price: ask,
    implied_volatility: iv,
    oi,
    previous_oi: Math.max(0, oi - 100),
    volume,
    previous_volume: Math.max(0, volume - 500),
    security_id: 1,
    average_price: ltp,
    top_bid_quantity: 10,
    top_ask_quantity: 10,
    greeks: { delta, theta: -1, gamma: 0.01, vega: 2 }
  };
}

const rawChain = {
  data: {
    last_price: 100,
    oc: {
      '80.000000': { ce: side({ ltp: 20.2, bid: 20.1, ask: 20.3, iv: 20, delta: 0.95 }), pe: side({ ltp: 0.2, bid: 0.1, ask: 0.3, iv: 24, delta: -0.05 }) },
      '90.000000': { ce: side({ ltp: 10.8, bid: 10.7, ask: 10.9, iv: 19, delta: 0.82 }), pe: side({ ltp: 0.8, bid: 0.7, ask: 0.9, iv: 22, delta: -0.18 }) },
      '95.000000': { ce: side({ ltp: 6.3, bid: 6.2, ask: 6.4, iv: 18.5, delta: 0.68 }), pe: side({ ltp: 1.3, bid: 1.2, ask: 1.4, iv: 21, delta: -0.32 }) },
      '100.000000': { ce: side({ ltp: 3.5, bid: 3.4, ask: 3.6, iv: 18, delta: 0.50 }), pe: side({ ltp: 3.5, bid: 3.4, ask: 3.6, iv: 19, delta: -0.50 }) },
      '105.000000': { ce: side({ ltp: 1.7, bid: 1.6, ask: 1.8, iv: 18.5, delta: 0.32 }), pe: side({ ltp: 6.7, bid: 6.6, ask: 6.8, iv: 19.5, delta: -0.68 }) },
      '110.000000': { ce: side({ ltp: 0.8, bid: 0.7, ask: 0.9, iv: 19, delta: 0.18 }), pe: side({ ltp: 10.8, bid: 10.7, ask: 10.9, iv: 20, delta: -0.82 }) },
      '120.000000': { ce: side({ ltp: 0.2, bid: 0.1, ask: 0.3, iv: 21, delta: 0.05 }), pe: side({ ltp: 20.2, bid: 20.1, ask: 20.3, iv: 22, delta: -0.95 }) }
    }
  },
  status: 'success'
};

test('Dhan chain normalization and surface analytics work', () => {
  const snap = normalizeDhanChain(rawChain, { symbol: 'NIFTY', expiry: '2026-10-01' });
  assert.equal(snap.chain.length, 7);
  assert.equal(snap.underlying_value, 100);
  assert.equal(snap.chain[3].call.iv, 0.18);

  const analysis = analyzeOptionSurface(snap, {
    expiry: '2026-10-01',
    asof: new Date('2026-09-21T00:00:00Z'),
    butterfly: { lower: 90, center: 100, upper: 110, debit: 4 }
  });
  assert.ok(analysis.atm.strike >= 95 && analysis.atm.strike <= 105);
  assert.ok(analysis.atm.iv > 0);
  assert.ok(analysis.risk_neutral_distribution);
  assert.ok(analysis.butterfly_mapping.p_outside_wings >= 0);
  assert.ok(analysis.butterfly_mapping.p_outside_wings <= 1);
});

test('current iron butterfly is reconstructed from positions', () => {
  const positions = [
    { tradingSymbol: 'NIFTY-Sep2026-22650-PE', netQty: 65, drvExpiryDate: '2026-09-22', drvOptionType: 'PUT', drvStrikePrice: 22650, buyAvg: 4.4, sellAvg: 0 },
    { tradingSymbol: 'NIFTY-Sep2026-23350-PE', netQty: -65, drvExpiryDate: '2026-09-22', drvOptionType: 'PUT', drvStrikePrice: 23350, buyAvg: 0, sellAvg: 118.7 },
    { tradingSymbol: 'NIFTY-Sep2026-23350-CE', netQty: -65, drvExpiryDate: '2026-09-22', drvOptionType: 'CALL', drvStrikePrice: 23350, buyAvg: 0, sellAvg: 123.65 },
    { tradingSymbol: 'NIFTY-Sep2026-24050-CE', netQty: 65, drvExpiryDate: '2026-09-22', drvOptionType: 'CALL', drvStrikePrice: 24050, buyAvg: 1.85, sellAvg: 0 }
  ];
  const fly = inferIronButterfly(positions, 'NIFTY');
  assert.equal(fly.recognized, true);
  assert.equal(fly.center, 23350);
  assert.equal(fly.left_width, 700);
  assert.equal(fly.right_width, 700);
  assert.ok(Math.abs(fly.entry_credit_points - 236.1) < 1e-9);
  assert.ok(Math.abs(fly.equivalent_long_fly_debit_points - 463.9) < 1e-9);
});

test('timestamped Dhan expiry is normalized to YYYY-MM-DD for the chain API', () => {
  assert.equal(normalizeExpiryDate('2026-10-06 14:30:00'), '2026-10-06');
  assert.equal(normalizeExpiryDate('2026-10-06'), '2026-10-06');
  const positions = [
    { tradingSymbol: 'NIFTY-Oct2026-22150-PE', netQty: 65, drvExpiryDate: '2026-10-06 14:30:00', drvOptionType: 'PUT', drvStrikePrice: 22150, buyAvg: 17.15, sellAvg: 0 },
    { tradingSymbol: 'NIFTY-Oct2026-22700-PE', netQty: -65, drvExpiryDate: '2026-10-06 14:30:00', drvOptionType: 'PUT', drvStrikePrice: 22700, buyAvg: 0, sellAvg: 130.6 },
    { tradingSymbol: 'NIFTY-Oct2026-22700-CE', netQty: -65, drvExpiryDate: '2026-10-06 14:30:00', drvOptionType: 'CALL', drvStrikePrice: 22700, buyAvg: 0, sellAvg: 180.3 },
    { tradingSymbol: 'NIFTY-Oct2026-23250-CE', netQty: 65, drvExpiryDate: '2026-10-06 14:30:00', drvOptionType: 'CALL', drvStrikePrice: 23250, buyAvg: 15.65, sellAvg: 0 }
  ];
  const fly = inferIronButterfly(positions, 'NIFTY');
  assert.equal(fly.recognized, true);
  assert.equal(fly.expiry, '2026-10-06');
  assert.equal(fly.center, 22700);
  assert.ok(Math.abs(fly.entry_credit_points - 278.1) < 1e-9);
});
