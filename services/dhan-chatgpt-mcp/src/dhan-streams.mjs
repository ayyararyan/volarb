import {
  ProviderCommandOutcome,
  ProviderError,
  ProviderErrorCategory,
  ProviderErrorCode,
  ProviderOperationKind
} from './provider-error.mjs';
import { normalizeDhanOrderUpdate } from './dhan-normalizer.mjs';

const SEGMENT_ENUM = Object.freeze({
  IDX_I:0, NSE_EQ:1, NSE_FNO:2, NSE_CURRENCY:3,
  BSE_EQ:4, MCX_COMM:5, BSE_CURRENCY:7, BSE_FNO:8
});
const SEGMENT_NAME = Object.freeze(Object.fromEntries(Object.entries(SEGMENT_ENUM).map(([k,v])=>[v,k])));
const MODE_CODE = Object.freeze({ TICKER:15, QUOTE:17, FULL:21 });
const UNSUBSCRIBE_CODE = Object.freeze({ TICKER:16, QUOTE:18, FULL:22 });

function streamError(message, code = ProviderErrorCode.NETWORK_FAILURE, category = ProviderErrorCategory.NETWORK, reason = 'WEBSOCKET') {
  return new ProviderError({
    category, code, message,
    operation:'provider_stream',
    kind:ProviderOperationKind.STREAM,
    outcome:ProviderCommandOutcome.NOT_APPLICABLE,
    provider:{key:'dhan',reason}
  });
}
function listen(ws,event,fn){
  if(typeof ws.addEventListener==='function') ws.addEventListener(event,fn);
  else if(typeof ws.on==='function') ws.on(event,fn);
  else ws['on'+event]=fn;
}
async function bytesOf(data){
  if(Buffer.isBuffer(data)) return data;
  if(data instanceof ArrayBuffer) return Buffer.from(data);
  if(ArrayBuffer.isView(data)) return Buffer.from(data.buffer,data.byteOffset,data.byteLength);
  if(data?.arrayBuffer) return Buffer.from(await data.arrayBuffer());
  throw streamError('Dhan market feed returned unsupported binary payload',ProviderErrorCode.PROTOCOL_FAILURE,ProviderErrorCategory.PROTOCOL,'UNSUPPORTED_BINARY_PAYLOAD');
}
function readDepth(buffer,offset){
  const levels=[];
  for(let i=0;i<5;i++){
    const p=offset+i*20;
    levels.push({
      bidQuantity:buffer.readInt32LE(p),
      askQuantity:buffer.readInt32LE(p+4),
      bidOrders:buffer.readInt16LE(p+8),
      askOrders:buffer.readInt16LE(p+10),
      bidPrice:buffer.readFloatLE(p+12),
      askPrice:buffer.readFloatLE(p+16)
    });
  }
  return levels;
}
function parsePacket(packet){
  if(packet.length<8) throw streamError('Dhan market packet shorter than header',ProviderErrorCode.PROTOCOL_FAILURE,ProviderErrorCategory.PROTOCOL,'SHORT_PACKET');
  const code=packet.readUInt8(0);
  const exchangeEnum=packet.readUInt8(3);
  const securityId=String(packet.readInt32LE(4));
  const base={feedCode:code,instrument:{provider:'dhan',providerInstrumentId:securityId,exchangeSegment:SEGMENT_NAME[exchangeEnum]??String(exchangeEnum)}};
  if(code===2 && packet.length>=16) return {...base,type:'TICKER',lastPrice:packet.readFloatLE(8),lastTradeEpoch:packet.readInt32LE(12)};
  if(code===4 && packet.length>=50) return {...base,type:'QUOTE',lastPrice:packet.readFloatLE(8),lastTradedQuantity:packet.readInt16LE(12),lastTradeEpoch:packet.readInt32LE(14),averageTradePrice:packet.readFloatLE(18),volume:packet.readInt32LE(22),totalSellQuantity:packet.readInt32LE(26),totalBuyQuantity:packet.readInt32LE(30),open:packet.readFloatLE(34),close:packet.readFloatLE(38),high:packet.readFloatLE(42),low:packet.readFloatLE(46)};
  if(code===5 && packet.length>=12) return {...base,type:'OPEN_INTEREST',openInterest:packet.readInt32LE(8)};
  if(code===6 && packet.length>=16) return {...base,type:'PREVIOUS_CLOSE',previousClose:packet.readFloatLE(8),previousOpenInterest:packet.readInt32LE(12)};
  if(code===8 && packet.length>=162) return {...base,type:'FULL',lastPrice:packet.readFloatLE(8),lastTradedQuantity:packet.readInt16LE(12),lastTradeEpoch:packet.readInt32LE(14),averageTradePrice:packet.readFloatLE(18),volume:packet.readInt32LE(22),totalSellQuantity:packet.readInt32LE(26),totalBuyQuantity:packet.readInt32LE(30),openInterest:packet.readInt32LE(34),highestOpenInterest:packet.readInt32LE(38),lowestOpenInterest:packet.readInt32LE(42),open:packet.readFloatLE(46),close:packet.readFloatLE(50),high:packet.readFloatLE(54),low:packet.readFloatLE(58),depth:readDepth(packet,62)};
  if(code===50 && packet.length>=10) return {...base,type:'DISCONNECT',reasonCode:packet.readInt16LE(8)};
  return {...base,type:'UNHANDLED'};
}
export function parseDhanMarketFeedBuffer(input){
  const buffer=Buffer.isBuffer(input)?input:Buffer.from(input);
  const events=[];
  let offset=0;
  while(offset<buffer.length){
    if(buffer.length-offset<8) throw streamError('Dhan market feed ended mid-header',ProviderErrorCode.PROTOCOL_FAILURE,ProviderErrorCategory.PROTOCOL,'TRUNCATED_PACKET');
    let length=buffer.readInt16LE(offset+1);
    if(length<=0 || length>buffer.length-offset) length=buffer.length-offset;
    events.push(parsePacket(buffer.subarray(offset,offset+length)));
    offset+=length;
  }
  return events;
}
function chunk(items,size){const out=[];for(let i=0;i<items.length;i+=size)out.push(items.slice(i,i+size));return out;}
function validateInstruments(instruments){
  if(!Array.isArray(instruments)||instruments.length<1||instruments.length>5000) throw streamError('Dhan market stream requires 1-5000 instruments',ProviderErrorCode.INVALID_REQUEST,ProviderErrorCategory.INVALID_REQUEST,'INVALID_INSTRUMENT_COUNT');
  for(const x of instruments){
    if(!(String(x?.exchangeSegment) in SEGMENT_ENUM) || !/^\d+$/.test(String(x?.securityId??''))) throw streamError('Invalid Dhan stream instrument reference',ProviderErrorCode.INVALID_REQUEST,ProviderErrorCategory.INVALID_REQUEST,'INVALID_INSTRUMENT');
  }
}
async function parseText(data){
  if(typeof data==='string') return data;
  if(Buffer.isBuffer(data)) return data.toString('utf8');
  if(data instanceof ArrayBuffer) return Buffer.from(data).toString('utf8');
  if(data?.text) return data.text();
  return String(data);
}

export class DhanStreamManager {
  constructor({config,readiness,resolveToken,WebSocketImpl=globalThis.WebSocket}){
    this.config=config;this.readiness=readiness;this.resolveToken=resolveToken;this.WebSocketImpl=WebSocketImpl;
  }
  async _token(operation){
    this.readiness.assertQueryConfigured(operation);
    try{return await this.resolveToken();}
    catch(error){throw streamError('Dhan stream authentication token unavailable',ProviderErrorCode.AUTHENTICATION_FAILED,ProviderErrorCategory.AUTHENTICATION,'TOKEN_UNAVAILABLE');}
  }
  _socket(url){
    if(typeof this.WebSocketImpl!=='function') throw streamError('WebSocket implementation is unavailable',ProviderErrorCode.UNSUPPORTED,ProviderErrorCategory.UNSUPPORTED,'WEBSOCKET_UNAVAILABLE');
    return new this.WebSocketImpl(url);
  }
  async openMarket({mode='FULL',instruments,onEvent,onError,onState}){
    const operation='STREAM_MARKET';
    const m=String(mode).toUpperCase();
    if(!MODE_CODE[m]) throw streamError('Dhan market stream mode must be TICKER, QUOTE or FULL',ProviderErrorCode.INVALID_REQUEST,ProviderErrorCategory.INVALID_REQUEST,'INVALID_STREAM_MODE');
    validateInstruments(instruments);
    const token=await this._token(operation);
    const url=`${this.config.marketFeedWsUrl}?version=2&token=${encodeURIComponent(token)}&clientId=${encodeURIComponent(this.config.clientId)}&authType=2`;
    const ws=this._socket(url);
    return new Promise((resolve,reject)=>{
      let opened=false;
      listen(ws,'open',()=>{
        opened=true;
        for(const group of chunk(instruments,100)) ws.send(JSON.stringify({RequestCode:MODE_CODE[m],InstrumentCount:group.length,InstrumentList:group.map(x=>({ExchangeSegment:x.exchangeSegment,SecurityId:String(x.securityId)}))}));
        onState?.({state:'OPEN',stream:'MARKET',mode:m});
        resolve({
          close(){try{ws.send(JSON.stringify({RequestCode:12}));}finally{ws.close();}},
          unsubscribe(list=instruments){for(const group of chunk(list,100)) ws.send(JSON.stringify({RequestCode:UNSUBSCRIBE_CODE[m],InstrumentCount:group.length,InstrumentList:group.map(x=>({ExchangeSegment:x.exchangeSegment,SecurityId:String(x.securityId)}))}));}
        });
      });
      listen(ws,'message',async event=>{
        try{for(const item of parseDhanMarketFeedBuffer(await bytesOf(event?.data??event))) onEvent?.(item);}
        catch(error){onError?.(error instanceof ProviderError?error:streamError(error.message,ProviderErrorCode.PROTOCOL_FAILURE,ProviderErrorCategory.PROTOCOL,'PARSE_FAILURE'));}
      });
      listen(ws,'error',()=>{const error=streamError('Dhan market WebSocket error');if(!opened)reject(error);else onError?.(error);});
      listen(ws,'close',event=>onState?.({state:'CLOSED',stream:'MARKET',code:event?.code??null,reason:event?.reason??null}));
    });
  }
  async openOrders({onEvent,onError,onState}){
    const operation='STREAM_ORDER_UPDATES';
    const token=await this._token(operation);
    const ws=this._socket(this.config.orderUpdateWsUrl);
    return new Promise((resolve,reject)=>{
      let opened=false;
      listen(ws,'open',()=>{
        opened=true;
        ws.send(JSON.stringify({LoginReq:{MsgCode:42,ClientId:this.config.clientId,Token:token},UserType:'SELF'}));
        onState?.({state:'OPEN',stream:'ORDER_UPDATES'});
        resolve({close(){ws.close();}});
      });
      listen(ws,'message',async event=>{
        try{
          const payload=JSON.parse(await parseText(event?.data??event));
          if(payload?.Type==='order_alert'&&payload?.Data) onEvent?.(normalizeDhanOrderUpdate(payload.Data));
          else onEvent?.({type:payload?.Type??'UNHANDLED',raw:payload});
        }catch(error){onError?.(error instanceof ProviderError?error:streamError('Invalid Dhan order-update payload',ProviderErrorCode.PROTOCOL_FAILURE,ProviderErrorCategory.PROTOCOL,'ORDER_UPDATE_PARSE_FAILURE'));}
      });
      listen(ws,'error',()=>{const error=streamError('Dhan order-update WebSocket error');if(!opened)reject(error);else onError?.(error);});
      listen(ws,'close',event=>onState?.({state:'CLOSED',stream:'ORDER_UPDATES',code:event?.code??null,reason:event?.reason??null}));
    });
  }
}
