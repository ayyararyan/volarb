import test from 'node:test';
import assert from 'node:assert/strict';
import { BrokerOperation, BrokerOperationKind } from '../../execution-engine/ports/broker-port.mjs';
import { VirtualClock } from '../src/virtual-clock.mjs';
import { ComponentHarness, CompositionHarness, createExecutionTestbed, runMassScenarios, runScenario } from '../src/harness.mjs';
import { checkInvariants, noBlindRetryAfterAmbiguity } from '../src/invariants.mjs';

const instrument={provider:'simulated',providerInstrumentId:'NIFTY-X',exchangeSegment:'SIM'};

test('virtual clock executes deterministic time then insertion order without wall-clock sleeps',async()=>{
  const clock=new VirtualClock(1000),seen=[];
  clock.schedule(20,()=>seen.push('c'));
  clock.schedule(10,()=>seen.push('a'));
  clock.schedule(10,()=>seen.push('b'));
  await clock.advance(20);
  assert.deepEqual(seen,['a','b','c']);
  assert.equal(clock.now(),1020);
});

test('component harness mounts one box with deterministic injected dependencies',async()=>{
  const harness=new ComponentHarness({
    componentFactory:({ledger,clock})=>({
      evaluate(input){
        ledger.append({actionId:'box-test',kind:'BOX_EVALUATION',input});
        return {at:clock.now(),eligible:input.margin<=input.available};
      }
    })
  });
  const out=await harness.invoke('evaluate',{margin:80,available:100});
  assert.equal(out.eligible,true);
  assert.equal(harness.testbed.ledger.entries().length,1);
});

test('simulated broker reproduces partial-fill/cancel race without overfill',async()=>{
  const scenario={
    name:'partial-fill-cancel-race',
    broker:{scripts:{byCorrelation:{'corr-race':{
      fills:[{afterMs:10,quantity:30,price:100},{afterMs:40,quantity:50,price:100}],
      cancel:{ackDelayMs:10,fillsBeforeConfirm:[{afterMs:5,quantity:10,price:100}]}
    }}}}
  };
  const out=await runScenario({scenario,driver:async t=>{
    t.ledger.append({actionId:'place-1',kind:'PLACE'});
    const placed=await t.broker.call({kind:BrokerOperationKind.COMMAND,operation:BrokerOperation.PLACE_ORDER,payload:{order:{
      actionId:'place-1',correlationId:'corr-race',providerInstrumentRef:instrument,side:'BUY',quantity:100,orderType:'LIMIT',price:100
    }}});
    await t.clock.advance(25);
    t.ledger.append({actionId:'cancel-1',kind:'CANCEL'});
    await t.broker.call({kind:BrokerOperationKind.COMMAND,operation:BrokerOperation.CANCEL_ORDER,payload:{orderId:placed.data.brokerOrderRef,actionId:'cancel-1'}});
  }});
  const fills=out.trace.filter(x=>x.type==='broker.fill');
  assert.equal(fills.reduce((n,x)=>n+x.payload.quantity,0),40);
  const order=(await out.testbed.broker.call({kind:BrokerOperationKind.QUERY,operation:BrokerOperation.GET_ORDERS})).data[0];
  assert.equal(order.status,'CANCELLED');
  assert.equal(order.filledQuantity,40);
});

test('acknowledgement loss is reproducible and reconciliation clears blind-retry invariant',async()=>{
  const scenario={name:'ack-loss',broker:{scripts:{byCorrelation:{'corr-amb':{ackLost:true}}}}};
  const out=await runScenario({scenario,driver:async t=>{
    t.ledger.append({actionId:'place-amb',kind:'PLACE'});
    await assert.rejects(t.broker.call({kind:BrokerOperationKind.COMMAND,operation:BrokerOperation.PLACE_ORDER,payload:{order:{
      actionId:'place-amb',correlationId:'corr-amb',providerInstrumentRef:instrument,side:'BUY',quantity:10,orderType:'LIMIT',price:100
    }}}),e=>e.outcome==='UNKNOWN');
    const found=await t.broker.call({kind:BrokerOperationKind.QUERY,operation:BrokerOperation.GET_ORDER_BY_CORRELATION,payload:{correlationId:'corr-amb'}});
    assert.equal(found.data.brokerCorrelationRef,'corr-amb');
  }});
  assert.equal(out.trace.filter(x=>x.type==='broker.command.ambiguous').length,1);
  assert.doesNotThrow(()=>noBlindRetryAfterAmbiguity(out.trace));
});

test('invariant checker detects blind duplicate placement after ambiguous outcome',async()=>{
  const t=createExecutionTestbed({brokerScripts:{byCorrelation:{'corr-bad':{ackLost:true}}}});
  t.ledger.append({actionId:'a1'});
  await assert.rejects(t.broker.call({kind:'COMMAND',operation:'PLACE_ORDER',payload:{order:{actionId:'a1',correlationId:'corr-bad',providerInstrumentRef:instrument,side:'BUY',quantity:1}}}));
  t.broker.scripts.byCorrelation['corr-bad']={};
  t.ledger.append({actionId:'a2'});
  await t.broker.call({kind:'COMMAND',operation:'PLACE_ORDER',payload:{order:{actionId:'a2',correlationId:'corr-bad',providerInstrumentRef:instrument,side:'BUY',quantity:1}}});
  assert.throws(()=>checkInvariants(t.trace.all()),/NO_BLIND_RETRY_AFTER_AMBIGUITY/);
});

test('mass scenarios are seed-addressable and reproducible',async()=>{
  const summaries=await runMassScenarios({
    count:25,startSeed:100,
    scenarioFactory:async seed=>({name:`seed-${seed}`,broker:{scripts:{byCorrelation:{[`corr-${seed}`]:{fills:[{afterMs:seed%5,quantity:(seed%7)+1,price:100}]}}}}}),
    driver:async(t,scenario)=>{
      const seed=scenario.seed,qty=(seed%7)+1,actionId=`a-${seed}`;
      t.ledger.append({actionId});
      await t.broker.call({kind:'COMMAND',operation:'PLACE_ORDER',payload:{order:{actionId,correlationId:`corr-${seed}`,providerInstrumentRef:instrument,side:'BUY',quantity:qty}}});
    }
  });
  assert.equal(summaries.length,25);
  assert.deepEqual(summaries.map(x=>x.seed),Array.from({length:25},(_,i)=>100+i));
  assert.ok(summaries.every(x=>x.ok));
});


test('composition harness mounts selected boxes jointly on the same deterministic dependencies',async()=>{
  const harness=new CompositionHarness({
    componentFactories:{
      slicer:()=>({slice:x=>({...x,slices:[{sliceId:'s1',quantity:x.quantity}]})}),
      executor:({components,ledger})=>({
        execute(x){
          const sliced=components.slicer.slice(x);
          ledger.append({actionId:'joint-1',sliceId:sliced.slices[0].sliceId});
          return {worked:sliced.slices[0].quantity};
        }
      })
    }
  });
  const out=await harness.invoke('executor','execute',{quantity:65});
  assert.deepEqual(out,{worked:65});
  assert.equal(harness.testbed.ledger.entries()[0].sliceId,'s1');
});

test('mass harness runs one thousand seed-addressable scenarios without wall-clock waits',async()=>{
  const summaries=await runMassScenarios({
    count:1000,startSeed:1,
    scenarioFactory:async(seed,rng)=>({name:`mass-${seed}`,generatedValue:rng.int(1,1000)}),
    driver:async(t,scenario)=>{t.trace.record('generated.value',{value:scenario.generatedValue});}
  });
  assert.equal(summaries.length,1000);
  assert.equal(summaries[0].seed,1);
  assert.equal(summaries.at(-1).seed,1000);
});
