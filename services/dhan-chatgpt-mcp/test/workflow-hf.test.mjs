import test from 'node:test';
import assert from 'node:assert/strict';
import { collectHF, resolveFutures } from '../src/workflow-hf.mjs';
const symbols=['NIFTY','BANKNIFTY','SENSEX'];
const rows=symbols.map((s,i)=>({UNDERLYING_SYMBOL:s,INSTRUMENT_TYPE:'FUTIDX',EXCH_ID:s==='SENSEX'?'BSE':'NSE',
  SM_EXPIRY_DATE:'2026-10-27',SECURITY_ID:String(i+1)}));
const instruments=resolveFutures(rows,'2026-09-29');
test('resolve each exact future, reject expired and wrong exchanges',()=>{
  assert.equal(instruments.length,3);
  assert.throws(()=>resolveFutures(rows,'2026-11-01'));
  assert.throws(()=>resolveFutures(rows.map(r=>({...r,SM_EXPIRY_DATE:undefined})),'2026-09-29'));
  assert.throws(()=>resolveFutures(rows.map(r=>({...r,EXCH_ID:'X'})),'2026-09-29'));
});
test('bounded sampler batches three contracts at two-second cadence',async()=>{
  let clock=Date.parse('2026-09-29T04:30:00Z'),calls=0;
  const broker={getQuote:async requests=>{
    calls++;assert.equal(requests.length,3);
    const data={};for(const i of instruments){data[i.exchangeSegment]??={};data[i.exchangeSegment][i.securityId]={
      last_trade_time:new Date(clock).toISOString(),depth:{buy:[{price:100,quantity:10}],sell:[{price:101,quantity:10}]}};}
    return {status:'success',data};
  }};
  const out=await collectHF({broker,instruments,now:()=>clock,wait:async ms=>{clock+=ms;}});
  assert.equal(calls,151);assert.equal(out.hf_quotes.NIFTY.length,151);
  assert.equal(Date.parse(out.completed_at)-Date.parse(out.started_at),300000);
  assert.equal(out.capabilities.orders,false);
});
test('stale book proxy and absent exchange time never become fresh quotes',async()=>{
  let clock=Date.parse('2026-09-29T04:30:00Z');
  const stale={last_trade_time:'2026-09-28 10:00:00',depth:{buy:[{price:100,quantity:10}],sell:[{price:101,quantity:10}]}};
  const broker={getQuote:async()=>({status:'success',data:{NSE_FNO:{'1':stale}}})};
  const out=await collectHF({instruments,now:()=>clock,wait:async ms=>{clock+=ms;},broker});
  assert.equal(out.hf_quotes.NIFTY.length,0);
});
test('authentication rejection stops sampling without generation loop',async()=>{
  let calls=0;
  const out=await collectHF({instruments,broker:{getQuote:async()=>{calls++;throw Object.assign(new Error(),{status:401});}}});
  assert.equal(calls,1);assert.equal(out.failures.length,1);
});
