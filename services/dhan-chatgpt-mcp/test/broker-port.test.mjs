import test from 'node:test';
import assert from 'node:assert/strict';
import { createDhanRuntime } from '../src/dhan-runtime.mjs';
import { DhanBrokerOperation } from '../src/dhan-broker-port.mjs';

const Q='QUERY', C='COMMAND';
const env=(x={})=>({
  DHAN_CLIENT_ID:'123', DHAN_ACCESS_TOKEN:'token',
  DHAN_PROVIDER_COMMANDS_ENABLED:'true',
  DHAN_PROVIDER_EGRESS_IP:'203.0.113.10',
  DHAN_PROVIDER_STATIC_IP_CONFIRMED:'true',
  DHAN_PROVIDER_READINESS_TTL_MS:'30000', ...x
});
const jsonResponse=(data,status=200)=>({
  ok:status>=200&&status<300,status,statusText:status===200?'OK':'ERR',
  text:async()=>JSON.stringify(data),json:async()=>data
});

test('unconfigured Dhan exposes readiness but all real queries use global NOT_CONFIGURED',async()=>{
  const runtime=createDhanRuntime({env:{}});
  const ready=await runtime.port.call({kind:Q,operation:DhanBrokerOperation.GET_READINESS});
  assert.equal(ready.data.configured,false);
  await assert.rejects(runtime.port.call({kind:Q,operation:DhanBrokerOperation.GET_POSITIONS}),e=>{
    assert.equal(e.category,'CONFIGURATION');
    assert.equal(e.code,'PROVIDER.NOT_CONFIGURED');
    assert.equal(e.provider.reason,'BROKER_NOT_CONFIGURED');
    return true;
  });
});

test('missing static IP blocks mutation before any transport call',async()=>{
  let calls=0;
  const runtime=createDhanRuntime({
    env:env({DHAN_PROVIDER_EGRESS_IP:'',DHAN_PROVIDER_STATIC_IP_CONFIRMED:'false'}),
    fetchFn:async()=>{calls++;return jsonResponse({});}
  });
  await assert.rejects(runtime.port.call({
    kind:C,operation:DhanBrokerOperation.PLACE_ORDER,
    payload:{order:{correlationId:'static-ip-test',providerInstrumentRef:{provider:'dhan',providerInstrumentId:'1',exchangeSegment:'NSE_FNO'},side:'BUY',productType:'INTRADAY',orderType:'MARKET',validity:'DAY',quantity:65}}
  }),e=>{
    assert.equal(e.code,'PROVIDER.MUTATION_NOT_READY');
    assert.equal(e.provider.reason,'STATIC_IP_NOT_CONFIGURED');
    assert.equal(e.outcome,'KNOWN_NOT_APPLIED');
    return true;
  });
  assert.equal(calls,0);
});

test('command readiness is checked once then cached off the hot path',async()=>{
  let profile=0,ips=0,placed=0;
  const runtime=createDhanRuntime({
    env:env(),
    egressIpResolver:async()=> '203.0.113.10',
    fetchFn:async(url,options={})=>{
      if(url.endsWith('/profile')){profile++;return jsonResponse({dhanClientId:'123'});}
      if(url.endsWith('/ip/getIP')){ips++;return jsonResponse({primaryIP:'203.0.113.10'});}
      if(url.endsWith('/orders')&&options.method==='POST'){placed++;return jsonResponse({orderId:String(placed),orderStatus:'PENDING'});}
      throw new Error('unexpected '+url);
    }
  });
  for(let i=0;i<2;i++){
    const out=await runtime.port.call({
      kind:C,operation:DhanBrokerOperation.PLACE_ORDER,
      payload:{order:{correlationId:'core-correlation-'+i,providerInstrumentRef:{provider:'dhan',providerInstrumentId:'1',exchangeSegment:'NSE_FNO'},side:'BUY',productType:'INTRADAY',orderType:'MARKET',validity:'DAY',quantity:65,disclosedQuantity:0,price:0,triggerPrice:0,afterMarketOrder:false}}
    });
    assert.equal(out.data.status,'PENDING');
  }
  assert.equal(profile,1);assert.equal(ips,1);assert.equal(placed,2);
});

test('account snapshot is concurrent and margin shortfall stays a fact, not a provider decision',async()=>{
  const runtime=createDhanRuntime({
    env:env({DHAN_PROVIDER_COMMANDS_ENABLED:'false'}),
    fetchFn:async(url)=>{
      if(url.endsWith('/positions'))return jsonResponse([{securityId:'11',exchangeSegment:'NSE_FNO',productType:'INTRADAY',positionType:'LONG',netQty:65,buyQty:65,sellQty:0,buyAvg:10}]);
      if(url.endsWith('/fundlimit'))return jsonResponse({availabelBalance:1000,utilizedAmount:500});
      if(url.endsWith('/orders'))return jsonResponse([]);
      if(url.endsWith('/margincalculator'))return jsonResponse({totalMargin:2800,availableBalance:1000,insufficientBalance:1800});
      throw new Error('unexpected '+url);
    }
  });
  const snapshot=await runtime.port.call({kind:Q,operation:DhanBrokerOperation.GET_ACCOUNT_SNAPSHOT});
  assert.equal(snapshot.data.positions[0].netQuantity,65);
  assert.equal(snapshot.data.funds.availableBalance,1000);
  const margin=await runtime.port.call({
    kind:Q,operation:DhanBrokerOperation.GET_MARGIN,
    payload:{order:{providerInstrumentRef:{provider:'dhan',providerInstrumentId:'11',exchangeSegment:'NSE_FNO'},side:'SELL',quantity:65,productType:'INTRADAY',price:10,triggerPrice:0}}
  });
  assert.equal(margin.data.totalMargin,2800);
  assert.equal(margin.data.insufficientBalance,1800);
});

test('recovery surface supports historical trade backfill',async()=>{
  let seen='';
  const runtime=createDhanRuntime({
    env:env({DHAN_PROVIDER_COMMANDS_ENABLED:'false'}),
    fetchFn:async(url)=>{seen=url;return jsonResponse([{orderId:'o1',exchangeOrderId:'e1',exchangeTradeId:'t1',securityId:'11',exchangeSegment:'NSE_FNO',transactionType:'BUY',tradedQuantity:65,tradedPrice:10}]);}
  });
  const out=await runtime.port.call({
    kind:Q,operation:DhanBrokerOperation.GET_HISTORICAL_TRADES,
    payload:{fromDate:'2026-10-01',toDate:'2026-10-03',page:0}
  });
  assert.match(seen,/\/trades\/2026-10-01\/2026-10-03\/0$/);
  assert.equal(out.data[0].exchangeTradeRef,'t1');
});

test('operation-kind mismatch is rejected by the connector before broker work',async()=>{
  const runtime=createDhanRuntime({env:env({DHAN_PROVIDER_COMMANDS_ENABLED:'false'})});
  await assert.rejects(runtime.port.call({kind:C,operation:DhanBrokerOperation.GET_FUNDS}),e=>{
    assert.equal(e.category,'INVALID_REQUEST');
    assert.equal(e.outcome,'KNOWN_NOT_APPLIED');
    return true;
  });
});


test('broker-neutral order request is translated to Dhan mechanics with deterministic 30-char correlation',async()=>{
  let sent;
  const runtime=createDhanRuntime({
    env:env(),
    egressIpResolver:async()=> '203.0.113.10',
    fetchFn:async(url,options={})=>{
      if(url.endsWith('/profile'))return jsonResponse({dhanClientId:'123'});
      if(url.endsWith('/ip/getIP'))return jsonResponse({primaryIP:'203.0.113.10'});
      if(url.endsWith('/orders')&&options.method==='POST'){sent=JSON.parse(options.body);return jsonResponse({orderId:'o1',orderStatus:'PENDING'});}
      throw new Error('unexpected '+url);
    }
  });
  const request={correlationId:'intent/very-long-core-correlation-id/that-does-not-fit-dhan',providerInstrumentRef:{provider:'dhan',providerInstrumentId:'42',exchangeSegment:'NSE_FNO'},side:'SELL',productType:'INTRADAY',orderType:'LIMIT',validity:'DAY',quantity:65,price:12.5};
  const first=await runtime.port.call({kind:C,operation:DhanBrokerOperation.PLACE_ORDER,payload:{order:request}});
  assert.equal(sent.securityId,'42');
  assert.equal(sent.exchangeSegment,'NSE_FNO');
  assert.equal(sent.transactionType,'SELL');
  assert.equal(sent.correlationId.length,30);
  assert.match(sent.correlationId,/^v[0-9a-f]{29}$/);
  assert.equal(first.data.coreCorrelationId,request.correlationId);
  assert.equal(first.data.providerCorrelationRef,sent.correlationId);
  assert.equal(runtime.translator.correlationProjector.project(request.correlationId),sent.correlationId);
});

test('correlation lookup projects the same core identity used on placement',async()=>{
  let path='';
  const runtime=createDhanRuntime({
    env:env({DHAN_PROVIDER_COMMANDS_ENABLED:'false'}),
    fetchFn:async(url)=>{path=url;return jsonResponse({orderId:'o1',correlationId:path.split('/').at(-1),securityId:'42',exchangeSegment:'NSE_FNO',orderStatus:'PENDING'});}
  });
  const core='runtime-correlation-12345678901234567890';
  const expected=runtime.translator.correlationProjector.project(core);
  const out=await runtime.port.call({kind:Q,operation:DhanBrokerOperation.GET_ORDER_BY_CORRELATION,payload:{correlationId:core}});
  assert.ok(path.endsWith('/orders/external/'+expected));
  assert.equal(out.data.coreCorrelationId,core);
  assert.equal(out.data.providerCorrelationRef,expected);
});
