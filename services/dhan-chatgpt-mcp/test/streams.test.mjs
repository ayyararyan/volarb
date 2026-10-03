import test from 'node:test';
import assert from 'node:assert/strict';
import { createDhanRuntime } from '../src/dhan-runtime.mjs';
import { DhanBrokerOperation } from '../src/dhan-broker-port.mjs';
import { parseDhanMarketFeedBuffer } from '../src/dhan-streams.mjs';

class FakeWebSocket {
  static instances=[];
  constructor(url){
    this.url=url;this.sent=[];this.listeners={};
    FakeWebSocket.instances.push(this);
    queueMicrotask(()=>this.emit('open',{}));
  }
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  emit(name,event){for(const fn of this.listeners[name]??[])fn(event);}
  send(value){this.sent.push(value);}
  close(){this.emit('close',{code:1000,reason:'test'});}
}
const env=()=>({
  DHAN_CLIENT_ID:'123',
  DHAN_ACCESS_TOKEN:'secret-token',
  DHAN_PROVIDER_COMMANDS_ENABLED:'false'
});
const nextTurn=()=>new Promise(resolve=>setImmediate(resolve));

test('market feed binary ticker parser follows Dhan little-endian v2 packet',()=>{
  const packet=Buffer.alloc(16);
  packet.writeUInt8(2,0);
  packet.writeInt16LE(16,1);
  packet.writeUInt8(2,3);
  packet.writeInt32LE(49081,4);
  packet.writeFloatLE(368.15,8);
  packet.writeInt32LE(1791028800,12);
  const [event]=parseDhanMarketFeedBuffer(packet);
  assert.equal(event.type,'TICKER');
  assert.equal(event.instrument.exchangeSegment,'NSE_FNO');
  assert.equal(event.instrument.providerInstrumentId,'49081');
  assert.ok(Math.abs(event.lastPrice-368.15)<0.001);
  assert.equal(event.lastTradeEpoch,1791028800);
});

test('broker port live market stream subscribes directly in batches and emits normalized envelope',async()=>{
  FakeWebSocket.instances=[];
  const runtime=createDhanRuntime({env:env(),WebSocketImpl:FakeWebSocket});
  const events=[];
  const handle=await runtime.port.openStream({
    operation:DhanBrokerOperation.STREAM_MARKET,
    payload:{mode:'TICKER',instruments:[{exchangeSegment:'NSE_FNO',securityId:'49081'}]},
    onEvent:e=>events.push(e)
  });
  const ws=FakeWebSocket.instances.at(-1);
  assert.match(ws.url,/^wss:\/\/api-feed\.dhan\.co\?version=2&token=/);
  const request=JSON.parse(ws.sent[0]);
  assert.equal(request.RequestCode,15);
  assert.equal(request.InstrumentCount,1);
  assert.deepEqual(request.InstrumentList,[{ExchangeSegment:'NSE_FNO',SecurityId:'49081'}]);

  const packet=Buffer.alloc(16);
  packet.writeUInt8(2,0);packet.writeInt16LE(16,1);packet.writeUInt8(2,3);packet.writeInt32LE(49081,4);
  packet.writeFloatLE(100.5,8);packet.writeInt32LE(1791028800,12);
  ws.emit('message',{data:packet});
  await nextTurn();
  assert.equal(events.length,1);
  assert.equal(events[0].kind,'STREAM');
  assert.equal(events[0].operation,'STREAM_MARKET');
  assert.equal(events[0].data.lastPrice,100.5);
  handle.close();
});

test('order update stream authenticates once and normalizes account-wide order event',async()=>{
  FakeWebSocket.instances=[];
  const runtime=createDhanRuntime({env:env(),WebSocketImpl:FakeWebSocket});
  const events=[];
  const handle=await runtime.port.openStream({
    operation:DhanBrokerOperation.STREAM_ORDER_UPDATES,
    onEvent:e=>events.push(e)
  });
  const ws=FakeWebSocket.instances.at(-1);
  assert.equal(ws.url,'wss://api-order-update.dhan.co');
  const auth=JSON.parse(ws.sent[0]);
  assert.deepEqual(auth,{LoginReq:{MsgCode:42,ClientId:'123',Token:'secret-token'},UserType:'SELF'});

  ws.emit('message',{data:JSON.stringify({
    Type:'order_alert',
    Data:{
      Exchange:'NSE',Segment:'D',Source:'P',SecurityId:'49081',ClientId:'123',
      ExchOrderNo:'e1',OrderNo:'o1',Product:'I',TxnType:'B',OrderType:'LMT',
      Validity:'DAY',RemainingQuantity:45,Quantity:65,TradedQty:20,Price:10,
      TriggerPrice:0,AvgTradedPrice:9.95,OrderDateTime:'2026-10-03 10:00:00',
      ExchOrderTime:'2026-10-03 10:00:00',LastUpdatedTime:'2026-10-03 10:00:01',
      ReasonDescription:'CONFIRMED',Status:'PENDING',CorrelationId:'abc',LotSize:65,TickSize:0.05
    }
  })});
  await nextTurn();
  assert.equal(events.length,1);
  const order=events[0].data;
  assert.equal(order.brokerOrderRef,'o1');
  assert.equal(order.brokerCorrelationRef,'abc');
  assert.equal(order.instrument.exchangeSegment,'NSE_FNO');
  assert.equal(order.side,'BUY');
  assert.equal(order.productType,'INTRADAY');
  assert.equal(order.orderType,'LIMIT');
  assert.equal(order.filledQuantity,20);
  assert.equal(order.remainingQuantity,45);
  handle.close();
});

test('capability document advertises live stream support only after stream wiring',async()=>{
  const runtime=createDhanRuntime({env:env(),WebSocketImpl:FakeWebSocket});
  const out=await runtime.port.call({kind:'QUERY',operation:DhanBrokerOperation.GET_CAPABILITIES});
  assert.deepEqual(out.data.operations.stream,['STREAM_MARKET','STREAM_ORDER_UPDATES']);
  assert.equal(out.data.streamStatus,'LIVE_MARKET_AND_ORDER_UPDATES');
});
