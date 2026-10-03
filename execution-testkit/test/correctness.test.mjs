import test from 'node:test';
import assert from 'node:assert/strict';
import { createExecutionTestbed } from '../src/harness.mjs';
import { checkInvariants } from '../src/invariants.mjs';

const instrument={provider:'simulated',providerInstrumentId:'OFFLINE-X',exchangeSegment:'SIM'};
const place=(t,correlationId,actionId='place',extra={})=>t.broker.call({
  kind:'COMMAND',operation:'PLACE_ORDER',payload:{order:{
    correlationId,actionId,providerInstrumentRef:instrument,side:'BUY',quantity:100,
    orderType:'LIMIT',price:100,...extra
  }}
});
const orders=async t=>(await t.broker.call({kind:'QUERY',operation:'GET_ORDERS'})).data;

test('unequal fill prices produce weighted order facts and individual trade prices',async()=>{
  const t=createExecutionTestbed({brokerScripts:{default:{fills:[
    {afterMs:1,quantity:25,price:100},{afterMs:2,quantity:75,price:120}
  ]}}});
  t.ledger.append({actionId:'place'});
  await place(t,'weighted');
  await t.clock.runUntilIdle();
  assert.equal((await orders(t))[0].averageFillPrice,115);
  assert.deepEqual((await t.broker.call({kind:'QUERY',operation:'GET_TRADES'})).data.map(x=>x.price),[100,120]);
  assert.doesNotThrow(()=>checkInvariants(t.trace.all()));
});

test('broker-neutral modifications update normalized facts and subsequent fills',async()=>{
  const t=createExecutionTestbed({brokerScripts:{default:{fills:[
    {afterMs:1,quantity:30,price:100},{afterMs:2,quantity:50}
  ]}}});
  t.ledger.append({actionId:'place'});
  const placed=await place(t,'modify');
  await t.clock.advance(1);
  t.ledger.append({actionId:'modify'});
  const modified=await t.broker.call({kind:'COMMAND',operation:'MODIFY_ORDER',payload:{
    orderId:placed.data.brokerOrderRef,actionId:'modify',changes:{quantity:50,price:80}
  }});
  assert.equal(modified.data.requestedQuantity,50);
  assert.equal(modified.data.remainingQuantity,20);
  assert.equal(modified.data.limitPrice,80);
  assert.equal(Object.hasOwn(modified.data,'quantity'),false);
  assert.equal(Object.hasOwn(modified.data,'price'),false);
  await t.clock.runUntilIdle();
  const completed=(await orders(t))[0];
  assert.equal(completed.filledQuantity,50);
  assert.equal(completed.status,'FILLED');
  assert.equal(completed.averageFillPrice,92);
  assert.deepEqual((await t.broker.call({kind:'QUERY',operation:'GET_TRADES'})).data.map(x=>x.price),[100,80]);
  assert.doesNotThrow(()=>checkInvariants(t.trace.all()));
});

test('invalid modifications preserve already filled quantity and terminal order state',async()=>{
  const t=createExecutionTestbed({brokerScripts:{default:{fills:[{afterMs:1,quantity:30,price:100}]}}});
  const placed=await place(t,'invalid-modify');
  await t.clock.advance(1);
  const modify=changes=>t.broker.call({kind:'COMMAND',operation:'MODIFY_ORDER',payload:{orderId:placed.data.brokerOrderRef,changes}});
  const before=(await orders(t))[0];
  await assert.rejects(modify({quantity:20,price:80}),e=>e.code==='PROVIDER.INVALID_REQUEST'&&e.outcome==='KNOWN_NOT_APPLIED');
  assert.deepEqual((await orders(t))[0],before);
  await t.broker.call({kind:'COMMAND',operation:'CANCEL_ORDER',payload:{orderId:placed.data.brokerOrderRef}});
  await assert.rejects(modify({quantity:100}),e=>e.code==='PROVIDER.INVALID_REQUEST');
  assert.equal((await orders(t))[0].status,'CANCELLED');
});

test('write-ahead invariant accepts later outcome records but rejects unidentified or late writes',async()=>{
  const good=createExecutionTestbed();
  good.ledger.append({actionId:'place',status:'INTENDED'});
  await place(good,'logged');
  good.ledger.append({actionId:'place',status:'APPLIED'});
  assert.doesNotThrow(()=>checkInvariants(good.trace.all()));

  const unidentified=createExecutionTestbed();
  await place(unidentified,'unidentified',null);
  assert.throws(()=>checkInvariants(unidentified.trace.all()),/LEDGER_BEFORE_MUTATION/);

  const late=createExecutionTestbed();
  await place(late,'late');
  late.ledger.append({actionId:'place'});
  assert.throws(()=>checkInvariants(late.trace.all()),/LEDGER_BEFORE_MUTATION/);
});

test('injected after-apply ambiguity requires reconciliation before another placement',async()=>{
  for(const reconcile of [false,true]){
    const t=createExecutionTestbed({faultRules:[{operation:'PLACE_ORDER',phase:'after_apply',once:true}]});
    t.ledger.append({actionId:'first'});
    await assert.rejects(place(t,'ambiguous','first'),e=>e.outcome==='UNKNOWN');
    assert.equal(t.trace.ofType('broker.command.ambiguous').length,1);
    if(reconcile) await t.broker.call({kind:'QUERY',operation:'GET_ORDER_BY_CORRELATION',payload:{correlationId:'ambiguous'}});
    t.ledger.append({actionId:'second'});
    await place(t,'ambiguous','second');
    if(reconcile) assert.doesNotThrow(()=>checkInvariants(t.trace.all()));
    else assert.throws(()=>checkInvariants(t.trace.all()),/NO_BLIND_RETRY_AFTER_AMBIGUITY/);
  }
});

test('scheduled broker acknowledgement delays never rewind the shared virtual clock',async()=>{
  const t=createExecutionTestbed({brokerScripts:{default:{ackDelayMs:20,fills:[{afterMs:5,quantity:100,price:100}]}}});
  t.clock.schedule(10,async()=>{
    t.ledger.append({actionId:'place'});
    const placed=await place(t,'delayed');
    assert.equal(placed.observedAt,new Date(30).toISOString());
  });
  await t.clock.advance(10);
  assert.equal(t.clock.now(),30);
  await t.clock.advance(1);
  assert.equal(t.clock.now(),31);
  const times=t.trace.all().map(e=>e.timeMs);
  assert.deepEqual(times,[...times].sort((a,b)=>a-b));
  assert.doesNotThrow(()=>checkInvariants(t.trace.all()));
});

test('synthetic errors use virtual time and the shared operation-kind vocabulary',async()=>{
  const capture=async()=>{
    const t=createExecutionTestbed({startMs:1234,faultRules:[{operation:'RESOLVE_INSTRUMENT',phase:'before_call'}]});
    try{await t.broker.call({kind:'QUERY',operation:'RESOLVE_INSTRUMENT',payload:{instrument}});}
    catch(error){return error.toJSON();}
    assert.fail('expected injected query error');
  };
  const first=await capture();
  assert.equal(first.observedAt,new Date(1234).toISOString());
  assert.equal(first.kind,'QUERY');
  assert.equal(first.outcome,'NOT_APPLICABLE');
  assert.deepEqual(await capture(),first);
  const rejected=createExecutionTestbed({startMs:5678,brokerScripts:{default:{reject:{}}}});
  await assert.rejects(place(rejected,'rejected'),e=>e.observedAt===new Date(5678).toISOString()&&e.outcome==='KNOWN_NOT_APPLIED');
});
