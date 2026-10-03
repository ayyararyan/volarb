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


test('all documented Dhan trading error codes map into the global provider convention', async () => {
  const cases = {
    'DH-901': 'AUTHENTICATION',
    'DH-902': 'AUTHORIZATION',
    'DH-903': 'ACCOUNT_STATE',
    'DH-904': 'RATE_LIMIT',
    'DH-905': 'INVALID_REQUEST',
    'DH-906': 'ORDER_REJECTED',
    'DH-907': 'DATA_UNAVAILABLE',
    'DH-908': 'PROVIDER_INTERNAL',
    'DH-909': 'NETWORK',
    'DH-910': 'UNKNOWN'
  };

  for (const [nativeCode, expected] of Object.entries(cases)) {
    const provider = new DhanProvider({
      client: {
        getFunds: async () => {
          const error = new Error('native');
          error.name = 'DhanApiError';
          error.status = 400;
          error.payload = { errorType: 'test', errorCode: nativeCode, errorMessage: 'native message' };
          error.path = '/fundlimit';
          throw error;
        }
      },
      instrumentMaster: {}
    });
    await assert.rejects(provider.getFunds(), (error) => {
      assert.equal(error.name, 'ProviderError');
      assert.equal(error.category, expected);
      assert.equal(error.provider.key, 'dhan');
      assert.equal(error.provider.nativeCode, nativeCode);
      assert.equal(error.kind, 'QUERY');
      assert.equal(error.outcome, 'NOT_APPLICABLE');
      return true;
    });
  }
});

test('all documented Dhan data error codes map and no native error escapes', async () => {
  const cases = {
    '800': 'PROVIDER_INTERNAL',
    '804': 'INVALID_REQUEST',
    '805': 'RATE_LIMIT',
    '806': 'AUTHORIZATION',
    '807': 'AUTHENTICATION',
    '808': 'AUTHENTICATION',
    '809': 'AUTHENTICATION',
    '810': 'AUTHENTICATION',
    '811': 'INVALID_REQUEST',
    '812': 'INVALID_REQUEST',
    '813': 'INVALID_REQUEST',
    '814': 'INVALID_REQUEST'
  };

  for (const [nativeCode, expected] of Object.entries(cases)) {
    const provider = new DhanProvider({
      client: {
        getQuote: async () => {
          const error = new Error('native');
          error.name = 'DhanApiError';
          error.payload = { errorCode: nativeCode, errorMessage: 'data native message' };
          throw error;
        }
      },
      instrumentMaster: {}
    });
    await assert.rejects(provider.getQuote([]), (error) => {
      assert.equal(error.name, 'ProviderError');
      assert.equal(error.category, expected);
      assert.equal(error.provider.nativeCode, nativeCode);
      return true;
    });
  }
});

test('unknown Dhan errors map to UNKNOWN rather than leaking raw exceptions', async () => {
  const provider = new DhanProvider({
    client: { getFunds: async () => { throw new Error('new undocumented Dhan failure'); } },
    instrumentMaster: {}
  });
  await assert.rejects(provider.getFunds(), (error) => {
    assert.equal(error.name, 'ProviderError');
    assert.equal(error.category, 'UNKNOWN');
    assert.equal(error.code, 'PROVIDER.UNKNOWN');
    assert.match(error.message, /undocumented/);
    return true;
  });
});

test('mutation timeout becomes broker-neutral TIMEOUT with unknown command outcome', async () => {
  const provider = new DhanProvider({
    client: {
      placeOrder: async () => {
        const error = new Error('timeout');
        error.name = 'DhanApiError';
        error.transportKind = 'TIMEOUT';
        error.path = '/orders';
        throw error;
      }
    },
    instrumentMaster: {}
  });
  await assert.rejects(provider.placeOrder({ securityId: '1' }), (error) => {
    assert.equal(error.category, 'TIMEOUT');
    assert.equal(error.kind, 'COMMAND');
    assert.equal(error.outcome, 'UNKNOWN');
    assert.equal(error.operation, 'place_order');
    return true;
  });
});

test('definitive rejected order response becomes ORDER_REJECTED with known-not-applied outcome', async () => {
  const provider = new DhanProvider({
    client: {
      placeOrder: async () => ({
        orderId: 'o1',
        orderStatus: 'REJECTED',
        omsErrorCode: 'RMS123',
        omsErrorDescription: 'RMS rejected'
      })
    },
    instrumentMaster: {}
  });
  await assert.rejects(provider.placeOrder({ securityId: '1' }), (error) => {
    assert.equal(error.category, 'ORDER_REJECTED');
    assert.equal(error.code, 'PROVIDER.ORDER_REJECTED');
    assert.equal(error.outcome, 'KNOWN_NOT_APPLIED');
    assert.equal(error.provider.omsCode, 'RMS123');
    return true;
  });
});

test('provider error serialization exposes global fields plus Dhan provenance', async () => {
  const provider = new DhanProvider({
    client: {
      getFunds: async () => {
        const error = new Error('rate');
        error.name = 'DhanApiError';
        error.status = 429;
        error.payload = { errorCode: 'DH-904', errorMessage: 'Too many requests' };
        error.path = '/fundlimit';
        throw error;
      }
    },
    instrumentMaster: {}
  });
  await assert.rejects(provider.getFunds(), (error) => {
    const json = error.toJSON();
    assert.equal(json.contractVersion, '1.0');
    assert.equal(json.category, 'RATE_LIMIT');
    assert.equal(json.code, 'PROVIDER.RATE_LIMITED');
    assert.equal(json.provider.nativeCode, 'DH-904');
    assert.equal(json.provider.path, '/fundlimit');
    return true;
  });
});
