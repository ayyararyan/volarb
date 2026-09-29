import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, stat, chmod, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DhanApiError } from '../src/dhan-client.mjs';
import { ReadOnlyDhanClient, readonlyFacade, collectWorkflowData, saveWorkflowEvidence, sha256 } from '../src/workflow-data.mjs';

function fixture(options={}) {
  let time=Date.parse('2026-09-29T05:00:00Z'), pr=0, fr=0;
  const calls=[];
  const position={securityId:'123',exchangeSegment:'NSE_FNO',productType:'INTRADAY',netQty:10};
  const broker={clientId:'fixture',
    getProfile:async()=>{calls.push('profile');return {dhanClientId:options.wrongAccount?'wrong':'fixture',accessToken:'never-persist-this',name:'private-name'};},
    getPositions:async()=>{calls.push('positions');pr++;if(options.unavailable)throw new DhanApiError('SECRET-TEXT',{status:401,payload:{token:'SECRET'}});
      return options.badPosition?[{...position,netQty:true}]:options.exposure||options.change&&pr===2?[position]:[];},
    getOrders:async()=>{calls.push('orders');return options.pending||options.unknown?[{orderId:'1',securityId:'123',exchangeSegment:'NSE_FNO',orderStatus:options.unknown?'MYSTERY':'PENDING'}]:[];},
    getFunds:async()=>{calls.push('funds');fr++;return {availabelBalance:options.badFunds?null:50000-(options.fundsChange?fr:0)};},
    getTrades:async()=>{calls.push('trades');if(options.slow)time+=31000;return [];},
    getOptionExpiries:async r=>{calls.push('expiries');return ['2026-09-24','2026-10-06','2026-10-01'];},
    getOptionChain:async r=>{calls.push('chain');if(options.chainFailure&&r.underlyingScrip===25)throw new Error('sensitive message');
      return {data:{last_price:25000,oc:{'25000':{ce:{security_id:1,last_price:10},pe:{security_id:2,last_price:10}}}}};},
    getQuote:async()=>({}), placeLimitOrder:()=>{throw new Error('MUTATION FORBIDDEN');},cancelOrder:()=>{throw new Error('MUTATION FORBIDDEN');}
  };
  const master={resolveIndex:async symbol=>({symbol,underlyingScrip:{NIFTY:13,BANKNIFTY:25,SENSEX:1}[symbol],underlyingSeg:symbol==='SENSEX'?'BSE_FNO':'IDX_I',matchedRows:1})};
  return {broker,master,calls,now:()=>time,wait:async ms=>{time+=ms;}};
}

test('read-only transport rejects all order mutations before auth/network',async()=>{
  let calls=0,auth=0;
  const c=new ReadOnlyDhanClient({clientId:'fixture',tokenProvider:async()=>{auth++;return 'fixture';},fetchFn:async()=>{calls++;return {ok:true,json:async()=>[]};}});
  for(const fn of [()=>c.placeLimitOrder({}),()=>c.cancelOrder('1'),()=>c.request('/orders',{method:'PUT'}),()=>c.request('/orders/1'),()=>c.request('/ip/setIP',{method:'POST'}),()=>c.getBasketMargin([])])
    await assert.rejects(fn,/READ_ONLY_ROUTE_REJECTED/);
  assert.equal(calls,0);assert.equal(auth,0);
  await c.getOrders();assert.equal(calls,1);
});
test('read-only transport fixes origin, blocks redirects and limits exposed methods',async()=>{
  assert.throws(()=>new ReadOnlyDhanClient({clientId:'x',accessToken:'x',baseUrl:'https://other.invalid'}),/FIXED_DHAN_ORIGIN/);
  let request;
  const c=new ReadOnlyDhanClient({clientId:'x',accessToken:'x',fetchFn:async(...args)=>{request=args;return {ok:true,json:async()=>[]};}});
  await c.getOrders();assert.equal(request[0],'https://api.dhan.co/v2/orders');assert.equal(request[1].redirect,'error');
  const facade=readonlyFacade(c);assert.equal(facade.placeLimitOrder,undefined);assert.equal(facade.cancelOrder,undefined);assert.equal(facade.request,undefined);assert.equal(facade.accessToken,undefined);
});
test('identity plus two coherent account reads establish account evidence, never trading readiness',async()=>{
  const f=fixture(),r=await collectWorkflowData(f);
  assert.equal(r.status,'READ_ONLY_CAPTURED');assert.equal(r.account.verified,true);assert.equal(r.account.verified_flat,true);
  assert.equal(r.trading_ready,false);assert.equal(r.account.ownership,'UNASSIGNED');
  assert.equal(f.calls.filter(x=>x==='positions').length,2);assert.equal(f.calls.includes('chain'),false);
  assert.equal(JSON.stringify(r).includes('never-persist-this'),false);assert.equal(JSON.stringify(r).includes('private-name'),false);
});
test('real exposure and pending orders are not relabelled flat or synthetic',async()=>{
  for(const options of [{exposure:true},{pending:true}]){
    const r=await collectWorkflowData(fixture(options));assert.equal(r.account.verified,true);assert.equal(r.account.verified_flat,false);
    assert.equal(r.provenance,'OBSERVED');assert.equal(r.mode,'READ_ONLY');assert.equal(r.synthetic,undefined);
  }
});
test('identity failure stops acquisition, access failure never becomes flat',async()=>{
  const f=fixture({wrongAccount:true}),r=await collectWorkflowData(f);assert.deepEqual(f.calls,['profile']);assert.equal(r.account.verified,false);assert.equal(r.account.verified_flat,null);
  const unavailable=await collectWorkflowData(fixture({unavailable:true}));assert.equal(unavailable.account.verified,false);
  assert.equal(JSON.stringify(unavailable).includes('SECRET'),false);assert.equal(unavailable.account.verified_flat,null);
});
test('changed positions/funds, unknown orders, slow evidence and malformed numerics fail closed',async()=>{
  for(const opts of [{change:true},{fundsChange:true},{unknown:true},{slow:true},{badPosition:true},{badFunds:true}]){
    const r=await collectWorkflowData(fixture(opts));assert.equal(r.account.verified,false,JSON.stringify(opts));assert.equal(r.account.verified_flat,null);
  }
});
test('market capture uses listed expiries and all indices, with receipt clocks explicitly unverified',async()=>{
  const f=fixture(),r=await collectWorkflowData({...f,scope:'MARKET'});
  assert.equal(r.account.verified,true);assert.equal(f.calls.filter(x=>x==='chain').length,3);
  for(const symbol of ['NIFTY','BANKNIFTY','SENSEX']){
    assert.equal(r.markets[symbol].expiry,'2026-10-01');assert.equal(r.markets[symbol].exchange_quote_clock_verified,false);
    assert.equal(r.markets[symbol].normalized_snapshot.chain.length,1);
  }
  assert.equal(r.trading_ready,false);assert.ok(r.missing_layers.includes('HF_RV'));
});
test('one unavailable chain stays partial and does not erase good account evidence',async()=>{
  const r=await collectWorkflowData({...fixture({chainFailure:true}),scope:'MARKET'});
  assert.equal(r.status,'PARTIAL_MARKET_DATA');assert.equal(r.account.verified,true);
  assert.equal(r.markets.BANKNIFTY.status,'UNAVAILABLE');assert.equal(JSON.stringify(r).includes('sensitive message'),false);
});
test('unsupported scopes and too-aggressive market request spacing reject',async()=>{
  await assert.rejects(()=>collectWorkflowData({...fixture(),scope:'LIVE'}),/INVALID_SCOPE/);
  await assert.rejects(()=>collectWorkflowData({...fixture(),scope:'MARKET',chainSpacingMs:0}),/MASTER_AND_RATE/);
});
test('immutable private evidence is hash-bound and refuses overwrite or unsafe directories',async()=>{
  const root=await mkdtemp(join(tmpdir(),'workflow-evidence-'));
  try{
    const r=await collectWorkflowData(fixture());const receipt=await saveWorkflowEvidence(r,root);
    const manifest=JSON.parse(await readFile(receipt.manifest_file,'utf8'));
    assert.equal(sha256(await readFile(manifest.evidence_file,'utf8')),manifest.sha256);
    assert.equal((await stat(manifest.evidence_file)).mode&0o777,0o600);
    await assert.rejects(()=>saveWorkflowEvidence(r,root),{code:'EEXIST'});
    await chmod(root,0o755);await assert.rejects(()=>saveWorkflowEvidence(r,root),/PRIVATE_ROOT_PERMISSIONS/);
    await chmod(root,0o700);
    const alias=root+'-alias';await symlink(root,alias);
    try{await assert.rejects(()=>saveWorkflowEvidence(r,alias),/PRIVATE_ROOT_PERMISSIONS/);}finally{await rm(alias);}
  }finally{await rm(root,{recursive:true,force:true});}
});

test('position scope brackets exact held-leg quotes with account reconciliation',async()=>{
  const f=fixture({exposure:true});let requested;
  f.broker.getQuote=async instruments=>{requested=instruments;return {status:'success',data:{NSE_FNO:{'123':{
    last_trade_time:'2026-09-29 10:30:00',depth:{buy:[{price:10,quantity:10}],sell:[{price:11,quantity:10}]},accessToken:'must-not-persist'}}}};};
  const r=await collectWorkflowData({...f,scope:'POSITION'});
  assert.deepEqual(requested,[{exchangeSegment:'NSE_FNO',securityId:'123'}]);
  assert.equal(r.endpoints.position_quotes.status,'OK');assert.equal(r.account.verified,true);
  assert.equal(r.endpoints.position_quotes.data[0].bid,10);
  assert.equal(JSON.stringify(r).includes('must-not-persist'),false);
});
test('position quote failure is unavailable evidence, never an implicit executable mark',async()=>{
  const f=fixture({exposure:true});f.broker.getQuote=async()=>({status:'success',data:{}});
  const r=await collectWorkflowData({...f,scope:'POSITION'});
  assert.equal(r.account.verified,true);assert.equal(r.endpoints.position_quotes.status,'UNAVAILABLE');
});
