import test from 'node:test';
import assert from 'node:assert/strict';
import { DhanClient } from '../src/dhan-client.mjs';
import { checkButterflyMargin, normalizeMargin, basketMargin } from '../src/margin-preflight.mjs';
const time = Date.parse('2026-09-29T05:00:00Z');
const input = { symbol: 'NIFTY', expiry: '2026-10-06', lower: 24000, center: 25000, upper: 26000, lots: 1, reserveRupees: 1000 };
const specs = [[24000,'PE'],[26000,'CE'],[25000,'PE'],[25000,'CE']];
function fixture({funds=100000, totals=[100,200,50000,20000], pending=false, stale=false, change=false, malformed=false}={}) {
 let reads=0;
 const calls=[];
 const master={getRows:async()=>specs.map(([strike,type],i)=>({EXCH_ID:'NSE',SEGMENT:'D',INSTRUMENT:'OPTIDX',UNDERLYING_SYMBOL:'NIFTY',SM_EXPIRY_DATE:'2026-10-06',STRIKE_PRICE:String(strike),OPTION_TYPE:type,LOT_SIZE:'65',SM_FREEZE_QTY:'1800',BUY_SELL_INDICATOR:'A',SECURITY_ID:String(i+1)}))};
 const broker={
  getFunds:async()=>({availabelBalance:funds-(change?reads++:0)}), getPositions:async()=>[],
  getOrders:async()=>pending?[{orderStatus:'PENDING',orderId:'x'}]:[],
  getQuote:async()=>({data:{NSE_FNO:Object.fromEntries(specs.map((_,i)=>[String(i+1),{last_trade_time:stale?'2026-09-28T10:30:00+05:30':'2026-09-29T10:30:00+05:30',depth:{buy:[{price:1,quantity:1000}],sell:[{price:2,quantity:1000}]}}]))}}),
  getBasketMargin:async legs=>{calls.push(legs);return malformed?{totalMargin:null}:{totalMargin:totals[legs.length-1]};},
  placeLimitOrder:()=>{throw new Error('MUTATION FORBIDDEN');}, cancelOrder:()=>{throw new Error('MUTATION FORBIDDEN');}
 };
 return {broker,master,calls};
}
const run=(f,args=input)=>checkButterflyMargin(f.broker,f.master,args,{now:()=>time});
test('paired-hedge preflight binds every prefix to actual executor order',async()=>{
 const f=fixture(); const r=await run(f,{...input,entrySequence:'PAIRED_HEDGES'});
 assert.equal(r.status,'PASS');
 assert.equal(r.entrySequence,'PAIRED_HEDGES');
 assert.deepEqual(r.sequence,['putWing','putBody','callWing','callBody']);
 assert.deepEqual(f.calls.map(c=>c.map(l=>l.securityId)),[['1'],['1','3'],['1','3','2'],['1','3','2','4']]);
 assert.deepEqual(f.calls[3].map(l=>l.transactionType),['BUY','SELL','BUY','SELL']);
 assert.equal(r.reserveRupees,1000);
});
test('unsupported entry sequence fails closed instead of defaulting',async()=>{
 assert.equal((await run(fixture(),{...input,entrySequence:'BODY_FIRST'})).status,'UNVERIFIED');
});
test('official SDK wire contract hits calculator only',async()=>{
 const d=new DhanClient({clientId:'fixture',accessToken:'fixture'});let call;
 d.request=async(...args)=>{call=args;return {};};await d.getBasketMargin([{securityId:'1'}]);
 assert.deepEqual(call,['/margincalculator/multi',{method:'POST',body:{dhanClientId:'fixture',includePosition:true,includeOrder:true,scripList:[{securityId:'1'}]}}]);
});
test('normalizes observed camelCase and documented snake_case; rejects malformed/error totals',()=>{
 assert.equal(normalizeMargin({totalMargin:123}).totalMarginRupees,123);
 assert.equal(normalizeMargin({data:{total_margin:'124'}}).totalMarginRupees,124);
 for(const v of [null,'',true,'NaN',-1]) assert.throws(()=>normalizeMargin({totalMargin:v}));
 assert.throws(()=>normalizeMargin({status:'failure',data:{totalMargin:1}}));
});
test('peak prefix, not final hedge margin, determines affordability',async()=>{
 const f=fixture({funds:30000});const r=await run(f);
 assert.equal(r.status,'FAIL');assert.equal(r.peakRequiredRupees,50000);assert.equal(r.finalRequiredRupees,20000);
 assert.deepEqual(f.calls.map(c=>c.length),[1,2,3,4]);
 assert.deepEqual(f.calls[3].map(l=>l.transactionType),['BUY','BUY','SELL','SELL']);
 assert.equal(f.calls[3][0].quantity,65);assert.equal(f.calls[3][0].price,2);assert.equal(f.calls[3][3].price,1);
});
test('sufficient funds pass with explicit reserve; no premium double counting',async()=>{
 const r=await run(fixture());assert.equal(r.status,'PASS');assert.equal(r.headroomAfterReserveRupees,49000);
});
test('reserve omission, pending orders, stale quotes, account change and malformed API fail closed',async()=>{
 for(const opts of [{pending:true},{stale:true},{change:true},{malformed:true},{totals:[0,0,0,0]}]) assert.equal((await run(fixture(opts))).status,'UNVERIFIED');
 const args={...input};delete args.reserveRupees;assert.equal((await run(fixture(),args)).status,'UNVERIFIED');
});
test('percentage reserve uses available funds, larger of both reserves wins',async()=>{
 const r=await run(fixture(),{...input,reservePercent:60});assert.equal(r.reserveRupees,60000);assert.equal(r.status,'FAIL');
});
test('raw basket result cannot approve affordability',async()=>{
 const r=await basketMargin(fixture().broker,{legs:[{exchangeSegment:'NSE_FNO',securityId:'1',transactionType:'BUY',quantity:65,productType:'INTRADAY',price:2}]});
 assert.equal(r.affordabilityStatus,'UNVERIFIED');
});
test('after deadline, insufficient depth, wrong geometry, bad lot and broker failure do not pass',async()=>{
 let f=fixture();assert.equal((await checkButterflyMargin(f.broker,f.master,input,{now:()=>Date.parse('2026-09-29T10:00:00Z')})).status,'UNVERIFIED');
 f=fixture();f.broker.getQuote=async()=>({});assert.equal((await run(f)).status,'UNVERIFIED');
 assert.equal((await run(fixture(),{...input,lower:26000})).status,'UNVERIFIED');
 assert.equal((await run(fixture(),{...input,lots:100})).status,'UNVERIFIED');
 f=fixture();f.broker.getPositions=async()=>{throw new Error('unavailable');};assert.equal((await run(f)).status,'UNVERIFIED');
});
