import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, chmodSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ButterflyExecutor, ExecutionStore, priceFor, resolveLegs, planSchema, checkSession } from '../src/butterfly-executor.mjs';
import { bearerAuthorized, loadExecutionToken, makeReadiness, acquireExecutionLock } from '../src/execution-mcp.mjs';
import { DhanClient } from '../src/dhan-client.mjs';

const START = Date.parse('2026-09-29T10:00:00+05:30');
const input = { action: 'ENTRY', symbol: 'NIFTY', expiry: '2026-10-01', lower: 25000, center: 25500, upper: 26000, lots: 1, limits: { putWing: 20, putBody: 10, callWing: 20, callBody: 10 }, waitSeconds: 3, maxReprices: 2 };
const roles = ['putWing','putBody','callWing','callBody'];
const rows = roles.map((role, i) => ({ EXCH_ID:'NSE', SEGMENT:'D', INSTRUMENT:'OPTIDX', UNDERLYING_SYMBOL:'NIFTY', SM_EXPIRY_DATE:input.expiry, STRIKE_PRICE:[25000,25500,26000,25500][i], OPTION_TYPE:i < 2 ? 'PE':'CE', LOT_SIZE:65, TICK_SIZE:5, SM_FREEZE_QTY:1800, BUY_SELL_INDICATOR:'A', SECURITY_ID:String(i + 1) }));
const timestamp = now => new Date(now + 19800000).toISOString().slice(0,19).replace('T',' ');
function fixture({ modes = [], initial = [0,0,0,0], enabled = true } = {}) {
  let time = START;
  const calls = [], orders = new Map(), inventory = [...initial];
  const broker = {
    clientId:'123',
    async getPositions() { return inventory.map((netQty,i) => ({ securityId:String(i+1),exchangeSegment:'NSE_FNO',productType:'INTRADAY',netQty })); },
    async getOrders() { return [...orders.values()]; },
    async getQuote(legs) { return {data:{NSE_FNO:Object.fromEntries(legs.map(l => [l.securityId,{depth:{buy:[{price:15.4,quantity:650}],sell:[{price:15.6,quantity:650}]},last_price:15.5,last_trade_time:timestamp(time),lower_circuit_limit:0.05,upper_circuit_limit:1000}]))}}; },
    async getFunds() { return {availabelBalance:1e6}; },
    async getMargin(order) { calls.push({kind:'margin',...order});return {totalMargin:2000,availableBalance:1e6}; },
    async placeLimitOrder(request) {
      const index = calls.filter(c => c.kind === 'place').length;
      calls.push({kind:'place',...request});
      const mode = modes[index] || 'fill';
      const id = String(index+1);
      const filledQty = mode === 'partial' ? 20 : ['pending','reject','unknown'].includes(mode) ? 0 : request.quantity;
      const orderStatus = mode === 'reject' ? 'REJECTED' : filledQty === request.quantity ? 'TRADED' : filledQty ? 'PART_TRADED':'PENDING';
      const o = {...request,orderId:id,orderType:'LIMIT',productType:'INTRADAY',dhanClientId:'123',filledQty,orderStatus,remainingQuantity:request.quantity-filledQty};
      if (mode !== 'unknown') orders.set(id,o);
      inventory[Number(request.securityId)-1] += (request.transactionType === 'BUY' ? 1:-1)*filledQty;
      if (mode === 'timeout' || mode === 'unknown') throw new Error('simulated timeout');
      return {orderId:id,orderStatus};
    },
    async getOrder(id) { return structuredClone(orders.get(id)); },
    async getOrderByCorrelation(id) { const o = [...orders.values()].find(o=>o.correlationId===id); if (!o) throw new Error('not found');return structuredClone(o); },
    async getOrderTrades(id) { const o=orders.get(id);return o.filledQty ? [{...o,exchangeTradeId:`trade-${id}`,tradedQuantity:o.filledQty,tradedPrice:o.price,exchangeTime:timestamp(time)}]:[]; },
    async cancelOrder(id) { calls.push({kind:'cancel',id});const o=orders.get(id);o.orderStatus='CANCELLED';return {orderId:id,orderStatus:'CANCELLED'}; }
  };
  const dir=mkdtempSync(join(tmpdir(),'dhan-executor-test-'));
  const opts={broker,master:{getRows:async()=>rows},store:new ExecutionStore(dir),enabled,readiness:async()=>({ready:true}),now:()=>time,sleep:async ms=>{time+=ms;}};
  const executor=new ButterflyExecutor(opts);
  return {executor,broker,calls,orders,inventory,opts,dir,advance:ms=>{time+=ms;}};
}
async function run(f, params=input) {const p=await f.executor.preview(params);await f.executor.execute(p.id,p.confirmation);await f.executor.worker;return f.executor.status(p.id);}
const placements = f => f.calls.filter(c=>c.kind==='place');

test('entry completes only in wing/body sequence; prices are passive and tick aligned',async()=>{
 const f=fixture();const j=await run(f);
 assert.equal(j.status,'COMPLETED');
 assert.deepEqual(placements(f).map(p=>[p.securityId,p.transactionType]),[['1','BUY'],['2','SELL'],['3','BUY'],['4','SELL']]);
 assert.deepEqual(placements(f).map(p=>p.price),[15.45,15.55,15.45,15.55]);
 assert.deepEqual(f.inventory,[65,-65,65,-65]);
 assert.equal(j.orders.every(o=>o.reconciled),true);
});
test('exit reverses sequence and closes bodies before selling protective wings',async()=>{
 const f=fixture({initial:[65,-65,65,-65]});const j=await run(f,{...input,action:'EXIT',limits:{putWing:10,putBody:20,callWing:10,callBody:20}});
 assert.equal(j.status,'COMPLETED');
 assert.deepEqual(placements(f).map(p=>[p.securityId,p.transactionType]),[['4','BUY'],['3','SELL'],['2','BUY'],['1','SELL']]);
 assert.deepEqual(f.inventory,[0,0,0,0]);
});
test('partial wing fills: cancel-confirm then replace remaining units; body waits',async()=>{
 const f=fixture({modes:['partial']});const j=await run(f);
 assert.equal(j.status,'COMPLETED');
 assert.deepEqual(placements(f).slice(0,3).map(p=>[p.securityId,p.quantity]),[['1',65],['1',45],['2',65]]);
 assert.ok(f.calls.findIndex(c=>c.kind==='cancel')<f.calls.findIndex(c=>c.kind==='place'&&c.quantity===45));
});
test('unfilled wing exhausts reprices without any short sale',async()=>{
 const f=fixture({modes:['pending','pending','pending']});const j=await run(f);
 assert.equal(j.status,'PAUSED');assert.equal(placements(f).length,3);
 assert.equal(placements(f).every(p=>p.securityId==='1'&&p.transactionType==='BUY'),true);
 assert.equal([...f.orders.values()].every(o=>o.orderStatus==='CANCELLED'),true);
});
test('partial short remains fully hedged when later attempts do not fill',async()=>{
 const f=fixture({modes:['fill','partial','pending','pending']});const j=await run(f);
 assert.equal(j.status,'PAUSED');assert.deepEqual(f.inventory,[65,-20,0,0]);
 assert.equal(placements(f).some(p=>p.securityId==='3'),false);
});
test('failed call buy retains put spread and prevents call short',async()=>{
 const f=fixture({modes:['fill','fill','reject']});const j=await run(f);
 assert.equal(j.status,'PAUSED');assert.deepEqual(f.inventory,[65,-65,0,0]);
 assert.equal(placements(f).length,3);
});
test('exit short partial fill never releases its wing',async()=>{
 const f=fixture({initial:[65,-65,65,-65],modes:['partial','pending','pending']});
 const j=await run(f,{...input,action:'EXIT',limits:{putWing:10,putBody:20,callWing:10,callBody:20}});
 assert.equal(j.status,'PAUSED');assert.deepEqual(f.inventory,[65,-65,65,-45]);
 assert.equal(placements(f).every(p=>p.securityId==='4'),true);
});
test('exit cleans up incomplete entry inventory in reverse order',async()=>{
 const f=fixture({initial:[65,-20,0,0]});const j=await run(f,{...input,action:'EXIT',limits:{putWing:10,putBody:20,callWing:10,callBody:20}});
 assert.equal(j.status,'COMPLETED');assert.deepEqual(placements(f).map(p=>p.quantity),[20,65]);
});
test('timeout with accepted fill reconciles by correlation; never duplicates POST',async()=>{
 const f=fixture({modes:['timeout']});const j=await run(f);
 assert.equal(j.status,'PAUSED');assert.equal(placements(f).length,1);assert.deepEqual(f.inventory,[65,0,0,0]);
 assert.equal(j.orders[0].filled,65);
});
test('unknown placement blocks all further plans; missing order is not proof of non-submission',async()=>{
 const f=fixture({modes:['unknown']});const j=await run(f);
 assert.equal(j.status,'RECOVERY_REQUIRED');assert.equal(placements(f).length,1);
 await assert.rejects(f.executor.preview(input),/Unresolved/);
});
test('ambiguous cancellation blocks replacement and dependent short',async()=>{
 const f=fixture({modes:['pending']});f.broker.cancelOrder=async()=>{throw new Error('network');};
 const j=await run(f);assert.equal(j.status,'RECOVERY_REQUIRED');assert.equal(placements(f).length,1);
});
test('fill during cancellation is reconciled before any replacement',async()=>{
 const f=fixture({modes:['pending']});f.broker.cancelOrder=async id=>{const o=f.orders.get(id);o.filledQty=o.quantity;o.remainingQuantity=0;o.orderStatus='TRADED';f.inventory[Number(o.securityId)-1]+=o.quantity;};
 const j=await run(f);assert.equal(j.status,'COMPLETED');assert.equal(placements(f).length,4);
});
test('duplicate execute requests return same job without second order flow',async()=>{
 const f=fixture();const p=await f.executor.preview(input);
 await f.executor.execute(p.id,p.confirmation);await f.executor.execute(p.id,p.confirmation);await f.executor.worker;
 await f.executor.execute(p.id,p.confirmation);assert.equal(placements(f).length,4);
});
test('disabled live mode, wrong confirmation and expired previews cannot place',async()=>{
 const f=fixture({enabled:false});const p=await f.executor.preview(input);
 await assert.rejects(f.executor.execute(p.id,p.confirmation),/disabled/);
 await assert.rejects(f.executor.execute(p.id,'bad'),/Confirmation/);
 f.executor.enabled=true;f.advance(61000);await assert.rejects(f.executor.execute(p.id,p.confirmation),/expired/);
 assert.equal(placements(f).length,0);
});
test('funds failure prevents first order',async()=>{
 const f=fixture();f.broker.getFunds=async()=>({availabelBalance:1});
 const j=await run(f);assert.equal(j.status,'PAUSED');assert.equal(placements(f).length,0);
});
test('fresh funds checked after each fill: put premium is not assumed available',async()=>{
 const f=fixture();f.broker.getFunds=async()=>({availabelBalance:placements(f).length>=2 ? 0:1e6});
 const j=await run(f);assert.equal(j.status,'PAUSED');assert.deepEqual(f.inventory,[65,-65,0,0]);assert.equal(placements(f).length,2);
});
test('position drift between preview and execution blocks',async()=>{
 const f=fixture();const p=await f.executor.preview(input);f.inventory[0]=65;
 await assert.rejects(f.executor.execute(p.id,p.confirmation),/positions differ/);assert.equal(placements(f).length,0);
});
test('external outstanding order blocks preview',async()=>{
 const f=fixture();f.broker.getOrders=async()=>[{orderId:'external',orderStatus:'PENDING'}];
 await assert.rejects(f.executor.preview(input),/Outstanding/);
});
test('hedge deficit and pre-existing selected positions block entry',async()=>{
 await assert.rejects(fixture({initial:[0,-65,0,0]}).executor.preview(input),/Hedge deficit/);
 await assert.rejects(fixture({initial:[65,0,0,0]}).executor.preview(input),/flat/);
});
test('stop cancels own pending order, leaves fills, and starts no next leg',async()=>{
 const f=fixture({modes:['pending']});const p=await f.executor.preview(input);
 const orig=f.broker.getOrder;f.broker.getOrder=async id=>{f.executor.stop(p.id);return orig(id);};
 await f.executor.execute(p.id,p.confirmation);await f.executor.worker;
 assert.equal(f.executor.status(p.id).status,'PAUSED');assert.equal(placements(f).length,1);
 assert.equal([...f.orders.values()][0].orderStatus,'CANCELLED');
});
test('restart converts RUNNING to recovery; no automatic execution',async()=>{
 const f=fixture();const p=await f.executor.preview(input);f.executor.job(p.id).status='RUNNING';f.opts.store.save();
 const e=new ButterflyExecutor({...f.opts,store:new ExecutionStore(f.dir)});
 assert.equal(e.status(p.id).status,'RECOVERY_REQUIRED');assert.equal(placements(f).length,0);
 assert.equal((await e.reconcile(p.id)).status,'PAUSED');
});
test('ledger durability: pending placement intent exists on disk before POST',async()=>{
 const f=fixture();const original=f.broker.placeLimitOrder;
 f.broker.placeLimitOrder=async p=>{const state=JSON.parse(readFileSync(join(f.dir,'state.json'),'utf8'));assert.ok(Object.values(state.jobs).some(j=>j.orders.some(o=>o.correlationId===p.correlationId&&o.status==='INTENT')));return original(p);};
 await run(f);
});
test('trade-book mismatch stops progression even with TRADED order status',async()=>{
 const f=fixture();f.broker.getOrderTrades=async()=>[];const j=await run(f);
 assert.equal(j.status,'RECOVERY_REQUIRED');assert.equal(placements(f).length,1);
});
test('reject malformed lots, geometry, freeze, duplicate contracts, and missing instrument metadata',async()=>{
 const f=fixture();await assert.rejects(f.executor.preview({...input,lots:0}));
 await assert.rejects(f.executor.preview({...input,lower:26000}),/lower/);
 await assert.rejects(f.executor.preview({...input,lots:100}),/freeze/);
 await assert.rejects(resolveLegs({getRows:async()=>[...rows,rows[0]]},planSchema.parse(input)),/uniquely/);
 await assert.rejects(resolveLegs({getRows:async()=>rows.map(r=>({...r,TICK_SIZE:undefined}))},planSchema.parse(input)),/tick/);
});
test('market/session and early entry cutoff; emergency exits still allowed after 15:00',()=>{
 assert.throws(()=>checkSession('ENTRY',Date.parse('2026-09-29T14:54:00+05:30'),180),/Entry window/);
 assert.throws(()=>checkSession('ENTRY',Date.parse('2026-09-29T15:00:00+05:30')),/Entry window/);
 assert.doesNotThrow(()=>checkSession('EXIT',Date.parse('2026-09-29T15:01:00+05:30')));
 assert.throws(()=>checkSession('EXIT',Date.parse('2026-09-29T15:30:00+05:30')),/Outside/);
 assert.throws(()=>checkSession('ENTRY',Date.parse('2026-10-03T10:00:00+05:30')),/Outside/);
});
test('quote freshness, spread, depth, circuit bands, price caps and paise ticks',async()=>{
 const f=fixture();const i=planSchema.parse(input);const [l]=await resolveLegs(f.opts.master,i);assert.equal(l.tick,0.05);
 const q=(await f.executor.quotes([l])).putWing;
 assert.equal(priceFor(l,q,i,10,START),15.6);
 assert.equal(priceFor({...l,limit:15.42},q,i,10,START),15.4);
 assert.throws(()=>priceFor(l,{...q,last_trade_time:'01/01/1980 00:00:00'},i,0,START),/Stale/);
 assert.throws(()=>priceFor(l,{...q,upper_circuit_limit:10},i,0,START),/band/);
 assert.throws(()=>priceFor(l,{...q,depth:{buy:[{price:1,quantity:650}],sell:[{price:100,quantity:650}]}},i,0,START),/spread/);
 assert.throws(()=>priceFor(l,{...q,depth:{...q.depth,sell:[{price:15.6,quantity:1}]}},i,0,START),/depth/);
});
test('authenticated endpoint rejects absent/wrong tokens; private token file required',()=>{
 const token='a'.repeat(64);assert.equal(bearerAuthorized(undefined,token),false);assert.equal(bearerAuthorized('Bearer wrong',token),false);assert.equal(bearerAuthorized(`Bearer ${token}`,token),true);
 const f=join(mkdtempSync(join(tmpdir(),'dhan-token-test-')),'token');writeFileSync(f,token,{mode:0o600});assert.equal(loadExecutionToken(f),token);
 chmodSync(f,0o644);assert.throws(()=>loadExecutionToken(f),/private/);
});
test('live readiness checks current static outbound IP, whitelist, and account identity',async()=>{
 const options={enabled:true,token:'a'.repeat(64),expectedIp:'203.0.113.1',staticIpConfirmed:true,fetchFn:async()=>({ok:true,json:async()=>({ip:'203.0.113.1'})}),broker:{clientId:'123',getWhitelistedIps:async()=>({primaryIP:'203.0.113.1'}),getProfile:async()=>({dhanClientId:'123'})}};
 assert.equal((await makeReadiness(options)()).ready,true);
 await assert.rejects(makeReadiness({...options,staticIpConfirmed:false})(),/static/);
 await assert.rejects(makeReadiness({...options,expectedIp:'203.0.113.2'})(),/differs/);
 await assert.rejects(makeReadiness({...options,broker:{...options.broker,getWhitelistedIps:async()=>({})}})(),/whitelist/);
 await assert.rejects(makeReadiness({...options,broker:{...options.broker,getProfile:async()=>({dhanClientId:'999'})}})(),/identity/);
});
test('two processes cannot own the same executor state',()=>{
 const dir=mkdtempSync(join(tmpdir(),'dhan-lock-test-'));const release=acquireExecutionLock(dir);
 assert.throws(()=>acquireExecutionLock(dir),/Another/);release();const again=acquireExecutionLock(dir);again();
});
test('Dhan adapter forces LIMIT, INTRADAY, DAY, no AMO regardless of caller',async()=>{
 const c=new DhanClient({clientId:'123',accessToken:'test'});let sent;
 c.request=async(path,args)=>{sent={path,...args};return {};};
 await c.placeLimitOrder({securityId:'1',orderType:'MARKET',productType:'MARGIN',afterMarketOrder:true});
 assert.equal(sent.body.orderType,'LIMIT');assert.equal(sent.body.productType,'INTRADAY');assert.equal(sent.body.afterMarketOrder,false);assert.equal(sent.body.validity,'DAY');
});
test('failed broker envelope and boolean numeric fields fail closed',async()=>{
 const f=fixture();f.broker.getPositions=async()=>({status:'failure',data:[]});await assert.rejects(f.executor.preview(input),/failed broker/);
 const g=fixture();g.broker.getFunds=async()=>({availabelBalance:true});const j=await run(g);assert.equal(j.status,'PAUSED');assert.equal(placements(g).length,0);
});

test('mismatched broker order identity cannot cancel a foreign order',async()=>{
 const f=fixture({modes:['pending']});const read=f.broker.getOrder;
 f.broker.getOrder=async id=>({...await read(id),correlationId:'foreign'});
 const j=await run(f);assert.equal(j.status,'RECOVERY_REQUIRED');assert.equal(placements(f).length,1);
 assert.equal(f.calls.some(c=>c.kind==='cancel'),false);
});
