import test from 'node:test';
import assert from 'node:assert/strict';
import { DhanClient } from '../src/dhan-client.mjs';
import { DhanProvider } from '../src/dhan-provider.mjs';
import { InstrumentMaster } from '../src/instrument-master.mjs';

test('generic order placement preserves caller-selected broker mechanics', async () => {
  const client = new DhanClient({ clientId: '123', accessToken: 'token' });
  let sent;
  client.request = async (path, args) => { sent = { path, ...args }; return { orderId: 'o1' }; };

  await client.placeOrder({
    correlationId: 'abc',
    transactionType: 'SELL',
    exchangeSegment: 'NSE_FNO',
    productType: 'MARGIN',
    orderType: 'MARKET',
    validity: 'IOC',
    securityId: '42',
    quantity: 65,
    price: 0,
    triggerPrice: 0,
    afterMarketOrder: false
  });

  assert.equal(sent.path, '/orders');
  assert.equal(sent.method, 'POST');
  assert.equal(sent.body.dhanClientId, '123');
  assert.equal(sent.body.transactionType, 'SELL');
  assert.equal(sent.body.productType, 'MARGIN');
  assert.equal(sent.body.orderType, 'MARKET');
  assert.equal(sent.body.validity, 'IOC');
  assert.equal(sent.body.securityId, '42');
  assert.equal(sent.body.quantity, 65);
});

test('generic order modification transmits only requested mechanics plus Dhan identity', async () => {
  const client = new DhanClient({ clientId: '123', accessToken: 'token' });
  let sent;
  client.request = async (path, args) => { sent = { path, ...args }; return { orderId: 'o1' }; };

  await client.modifyOrder('o1', {
    orderType: 'LIMIT',
    quantity: 65,
    price: 101.25,
    validity: 'DAY'
  });

  assert.equal(sent.path, '/orders/o1');
  assert.equal(sent.method, 'PUT');
  assert.deepEqual(sent.body, {
    orderType: 'LIMIT',
    quantity: 65,
    price: 101.25,
    validity: 'DAY',
    dhanClientId: '123',
    orderId: 'o1'
  });
});

test('instrument master resolves exact option identity and exposes Dhan mechanics', async () => {
  const csv = [
    'EXCH_ID,SEGMENT,INSTRUMENT,UNDERLYING_SYMBOL,SM_EXPIRY_DATE,STRIKE_PRICE,OPTION_TYPE,LOT_SIZE,TICK_SIZE,SM_FREEZE_QTY,BUY_SELL_INDICATOR,SECURITY_ID,SEM_TRADING_SYMBOL',
    'NSE,D,OPTIDX,NIFTY,2026-10-08,25000,CE,65,5,1800,A,12345,NIFTY-08OCT2026-25000-CE'
  ].join('\n');
  const master = new InstrumentMaster({
    fetchFn: async () => ({ ok: true, text: async () => csv }),
    ttlMs: 999999
  });

  const instrument = await master.resolveInstrument({
    underlying: 'NIFTY',
    expiry: '2026-10-08',
    strike: 25000,
    optionType: 'CE',
    exchange: 'NSE'
  });

  assert.equal(instrument.securityId, '12345');
  assert.equal(instrument.exchangeSegment, 'NSE_FNO');
  assert.equal(instrument.lotSize, 65);
  assert.equal(instrument.tickSizeRupees, 0.05);
  assert.equal(instrument.freezeQuantity, 1800);
});

test('DhanProvider is a thin strategy-agnostic command/query facade', async () => {
  const calls = [];
  const client = {
    placeOrder: async x => { calls.push(['place', x]); return { orderId: '1' }; },
    modifyOrder: async (id, x) => { calls.push(['modify', id, x]); return {}; },
    cancelOrder: async id => { calls.push(['cancel', id]); return {}; },
    getPositions: async () => [{ securityId: '1', netQty: 65 }],
    getOrders: async () => [],
    getTrades: async () => [],
    getOrder: async () => ({}),
    getOrderByCorrelation: async () => ({}),
    getOrderTrades: async () => [],
    getHoldings: async () => [],
    getFunds: async () => ({}),
    getMargin: async () => ({}),
    getBasketMargin: async () => ({}),
    getLtp: async () => ({}),
    getQuote: async () => ({}),
    getOptionExpiries: async () => [],
    getOptionChain: async () => ({}),
    getProfile: async () => ({}),
    getWhitelistedIps: async () => ({})
  };
  const instrumentMaster = { resolveInstrument: async x => ({ ...x, securityId: '1' }) };
  const provider = new DhanProvider({ client, instrumentMaster });

  await provider.placeOrder({ securityId: '1', orderType: 'LIMIT' });
  await provider.modifyOrder('1', { price: 10 });
  await provider.cancelOrder('1');
  assert.deepEqual(await provider.getPositions(), [{ securityId: '1', netQty: 65 }]);
  assert.deepEqual(calls.map(x => x[0]), ['place', 'modify', 'cancel']);
});
