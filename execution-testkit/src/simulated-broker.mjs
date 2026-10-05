import { BrokerOperation, BrokerOperationKind, assertBrokerRequest, brokerOperationKind } from '../../compat/javascript/execution-contracts/broker-port.mjs';
import {
  ProviderCommandOutcome, ProviderError, ProviderErrorCategory, ProviderErrorCode
} from '../../compat/javascript/execution-contracts/provider-error.mjs';
import { instrumentKey } from './simulated-market.mjs';

const clone=x=>x===undefined?undefined:structuredClone(x);
const array=x=>Array.isArray(x)?x:[];
const working=new Set(['PENDING','PARTIALLY_FILLED']);

function simError({operation,kind,category=ProviderErrorCategory.UNKNOWN,code=ProviderErrorCode.UNKNOWN,message='Simulated broker failure',outcome,reason,observedAt}){
  return new ProviderError({
    category,code,message,operation,kind,observedAt,
    outcome:outcome??(kind===BrokerOperationKind.COMMAND?ProviderCommandOutcome.UNKNOWN:ProviderCommandOutcome.NOT_APPLICABLE),
    provider:{key:'simulated',reason:reason??'INJECTED'}
  });
}
function orderRef(order){
  const ref=order?.providerInstrumentRef??order?.instrument?.providerInstrumentRef??order?.instrument;
  if(!ref) throw new TypeError('Simulated order requires providerInstrumentRef/instrument');
  return clone(ref);
}

export class SimulatedBroker {
  constructor({
    clock,trace,market,faults=null,funds={},positions=[],orders=[],trades=[],
    scripts={},marginCalculator=null
  }={}){
    if(!clock) throw new TypeError('SimulatedBroker requires VirtualClock');
    this.clock=clock;this.trace=trace;this.market=market;this.faults=faults;
    this.funds={availableBalance:1_000_000,...clone(funds)};
    this.positions=array(positions).map(clone);
    this.orders=array(orders).map(clone);
    this.trades=array(trades).map(clone);
    this.scripts=scripts;this.marginCalculator=marginCalculator;
    this.orderSeq=this.orders.length;this.tradeSeq=this.trades.length;
    this.orderListeners=new Set();
  }

  _script(correlationId){return this.scripts?.byCorrelation?.[correlationId]??this.scripts?.default??{};}
  _error(details){return simError({...details,observedAt:new Date(this.clock.now()).toISOString()});}
  _fault(operation,phase,context={}){
    const rule=this.faults?.match({operation,phase,context});
    if(!rule) return;
    const error=this._error({
      operation,kind:rule.kind??brokerOperationKind(operation),
      category:rule.category??ProviderErrorCategory.NETWORK,
      code:rule.code??ProviderErrorCode.NETWORK_FAILURE,
      message:rule.message??`Injected ${phase} fault for ${operation}`,
      outcome:rule.outcome,reason:rule.reason??'FAULT_INJECTOR'
    });
    if(phase==='after_apply'&&error.kind===BrokerOperationKind.COMMAND&&error.outcome===ProviderCommandOutcome.UNKNOWN){
      this.trace?.record('broker.command.ambiguous',{operation,...context});
    }
    throw error;
  }
  _emitOrder(order){
    const data=clone(order);
    this.trace?.record('broker.order.update',data);
    for(const listener of this.orderListeners) listener(data);
  }
  _positionFor(ref){
    const k=instrumentKey(ref);
    let p=this.positions.find(x=>instrumentKey(x.instrument)===k);
    if(!p){p={instrument:clone(ref),netQuantity:0};this.positions.push(p);}
    return p;
  }
  _applyFill(order,fill){
    if(!working.has(order.status)) return;
    const remaining=order.requestedQuantity-order.filledQuantity;
    const qty=Math.min(remaining,Math.max(0,Number(fill.quantity??remaining)));
    if(!qty) return;
    const previousFilled=order.filledQuantity;
    const fillPrice=Number(fill.price??order.limitPrice??this.market?.snapshot([order.instrument])?.[0]?.lastPrice??0);
    order.filledQuantity+=qty;
    order.remainingQuantity=order.requestedQuantity-order.filledQuantity;
    order.averageFillPrice=((order.averageFillPrice??0)*previousFilled+fillPrice*qty)/order.filledQuantity;
    order.status=order.remainingQuantity===0?'FILLED':'PARTIALLY_FILLED';
    const trade={
      exchangeTradeRef:`sim-trade-${++this.tradeSeq}`,
      brokerOrderRef:order.brokerOrderRef,
      brokerCorrelationRef:order.brokerCorrelationRef,
      instrument:clone(order.instrument),side:order.side,quantity:qty,price:fillPrice,
      providerTimestamps:{exchange:new Date(this.clock.now()).toISOString()}
    };
    this.trades.push(trade);
    const pos=this._positionFor(order.instrument);
    pos.netQuantity+=order.side==='BUY'?qty:-qty;
    this.trace?.record('broker.fill',{orderRef:order.brokerOrderRef,correlationId:order.brokerCorrelationRef,quantity:qty,requestedQuantity:order.requestedQuantity,price:trade.price,actionId:order.actionId??null});
    this._emitOrder(order);
  }
  _scheduleFills(order,script){
    for(const fill of array(script.fills)){
      this.clock.schedule(Number(fill.afterMs??0),()=>this._applyFill(order,fill),{label:`fill:${order.brokerOrderRef}`});
    }
  }
  async _place(payload){
    const order=payload?.order??{};
    const correlationId=String(order.correlationId??'');
    if(!correlationId) throw new TypeError('Simulated placement requires correlationId');
    const script=this._script(correlationId);
    this._fault(BrokerOperation.PLACE_ORDER,'before_apply',{correlationId});
    if(script.reject){
      throw this._error({
        operation:BrokerOperation.PLACE_ORDER,kind:BrokerOperationKind.COMMAND,
        category:ProviderErrorCategory.ORDER_REJECTED,code:ProviderErrorCode.ORDER_REJECTED,
        message:script.reject.message??'Simulated order rejection',
        outcome:ProviderCommandOutcome.KNOWN_NOT_APPLIED,reason:script.reject.reason??'SIMULATED_REJECTION'
      });
    }
    const requestedQuantity=Number(order.quantity);
    if(!Number.isInteger(requestedQuantity)||requestedQuantity<=0) throw new TypeError('Simulated order quantity must be positive integer');
    const row={
      brokerOrderRef:`sim-order-${++this.orderSeq}`,
      brokerCorrelationRef:correlationId,
      instrument:orderRef(order),
      side:String(order.side).toUpperCase(),
      productType:order.productType??null,orderType:order.orderType??null,validity:order.validity??null,
      requestedQuantity,filledQuantity:0,remainingQuantity:requestedQuantity,
      limitPrice:Number(order.price??0),triggerPrice:Number(order.triggerPrice??0),
      averageFillPrice:null,status:'PENDING',actionId:order.actionId??null,
      intentId:order.intentId??null,intentVersion:order.intentVersion??null
    };
    this.orders.push(row);
    this.trace?.record('broker.command.applied',{operation:BrokerOperation.PLACE_ORDER,orderRef:row.brokerOrderRef,correlationId,actionId:row.actionId,intentId:row.intentId,intentVersion:row.intentVersion,requestedQuantity});
    this._emitOrder(row);this._scheduleFills(row,script);
    if(Number(script.ackDelayMs)>0) await this.clock.advance(Number(script.ackDelayMs));
    if(script.ackLost){
      this.trace?.record('broker.command.ambiguous',{operation:BrokerOperation.PLACE_ORDER,orderRef:row.brokerOrderRef,correlationId,actionId:row.actionId});
      throw this._error({operation:BrokerOperation.PLACE_ORDER,kind:BrokerOperationKind.COMMAND,category:ProviderErrorCategory.NETWORK,code:ProviderErrorCode.NETWORK_FAILURE,message:'Simulated acknowledgement loss after apply',outcome:ProviderCommandOutcome.UNKNOWN,reason:'ACK_LOST_AFTER_APPLY'});
    }
    this._fault(BrokerOperation.PLACE_ORDER,'after_apply',{correlationId,orderRef:row.brokerOrderRef,actionId:row.actionId});
    return clone(row);
  }
  async _cancel(payload){
    const order=this.orders.find(x=>x.brokerOrderRef===payload?.orderId);
    if(!order) throw this._error({operation:BrokerOperation.CANCEL_ORDER,kind:BrokerOperationKind.COMMAND,category:ProviderErrorCategory.RESOURCE_NOT_FOUND,code:ProviderErrorCode.RESOURCE_NOT_FOUND,message:'Simulated order not found',outcome:ProviderCommandOutcome.KNOWN_NOT_APPLIED,reason:'ORDER_NOT_FOUND'});
    const script=this._script(order.brokerCorrelationRef)?.cancel??{};
    this._fault(BrokerOperation.CANCEL_ORDER,'before_apply',{correlationId:order.brokerCorrelationRef,orderRef:order.brokerOrderRef});
    for(const fill of array(script.fillsBeforeConfirm)) this.clock.schedule(Number(fill.afterMs??0),()=>this._applyFill(order,fill),{label:`cancel-race-fill:${order.brokerOrderRef}`});
    if(Number(script.ackDelayMs)>0) await this.clock.advance(Number(script.ackDelayMs));
    if(working.has(order.status)){order.status='CANCELLED';order.remainingQuantity=order.requestedQuantity-order.filledQuantity;}
    this.trace?.record('broker.command.applied',{operation:BrokerOperation.CANCEL_ORDER,orderRef:order.brokerOrderRef,correlationId:order.brokerCorrelationRef,actionId:payload?.actionId??null});
    this._emitOrder(order);
    if(script.ackLost){
      this.trace?.record('broker.command.ambiguous',{operation:BrokerOperation.CANCEL_ORDER,orderRef:order.brokerOrderRef,correlationId:order.brokerCorrelationRef,actionId:payload?.actionId??null});
      throw this._error({operation:BrokerOperation.CANCEL_ORDER,kind:BrokerOperationKind.COMMAND,category:ProviderErrorCategory.NETWORK,code:ProviderErrorCode.NETWORK_FAILURE,message:'Simulated cancel acknowledgement loss',outcome:ProviderCommandOutcome.UNKNOWN,reason:'CANCEL_ACK_LOST'});
    }
    return clone(order);
  }
  async _modify(payload){
    const order=this.orders.find(x=>x.brokerOrderRef===payload?.orderId);
    if(!order) throw this._error({operation:BrokerOperation.MODIFY_ORDER,kind:BrokerOperationKind.COMMAND,category:ProviderErrorCategory.RESOURCE_NOT_FOUND,code:ProviderErrorCode.RESOURCE_NOT_FOUND,message:'Simulated order not found',outcome:ProviderCommandOutcome.KNOWN_NOT_APPLIED,reason:'ORDER_NOT_FOUND'});
    const invalid=message=>this._error({operation:BrokerOperation.MODIFY_ORDER,kind:BrokerOperationKind.COMMAND,category:ProviderErrorCategory.INVALID_REQUEST,code:ProviderErrorCode.INVALID_REQUEST,message,outcome:ProviderCommandOutcome.KNOWN_NOT_APPLIED,reason:'INVALID_MODIFICATION'});
    if(!working.has(order.status)) throw invalid('Simulated modification requires a working order');
    const changes=payload?.changes??{},patch={};
    const fields={quantity:'requestedQuantity',price:'limitPrice',triggerPrice:'triggerPrice',disclosedQuantity:'disclosedQuantity',orderType:'orderType',validity:'validity'};
    for(const [requestField,factField] of Object.entries(fields)){
      if(changes[requestField]===undefined) continue;
      const value=['orderType','validity'].includes(requestField)?String(changes[requestField]).toUpperCase():Number(changes[requestField]);
      if(typeof value==='number'&&(!Number.isFinite(value)||value<0)) throw invalid(`Invalid modified ${requestField}`);
      patch[factField]=value;
    }
    if(!Object.keys(patch).length) throw invalid('No supported modification fields supplied');
    if(patch.requestedQuantity!==undefined&&(!Number.isInteger(patch.requestedQuantity)||patch.requestedQuantity<=0||patch.requestedQuantity<order.filledQuantity)) throw invalid('Modified quantity must be a positive integer no smaller than filled quantity');
    Object.assign(order,patch);
    order.remainingQuantity=order.requestedQuantity-order.filledQuantity;
    order.status=order.remainingQuantity===0?'FILLED':order.filledQuantity>0?'PARTIALLY_FILLED':'PENDING';
    this.trace?.record('broker.command.applied',{operation:BrokerOperation.MODIFY_ORDER,orderRef:order.brokerOrderRef,correlationId:order.brokerCorrelationRef,actionId:payload?.actionId??null});
    this._emitOrder(order);return clone(order);
  }
  _margin(payload){
    if(this.marginCalculator) return clone(this.marginCalculator(clone(payload),this));
    const q=Number(payload?.order?.quantity??array(payload?.orders)[0]?.quantity??0);
    return {totalMargin:q*100,availableBalance:this.funds.availableBalance,insufficientBalance:Math.max(0,q*100-this.funds.availableBalance)};
  }
  async call({kind,operation,payload={}}){
    assertBrokerRequest({kind,operation});
    this.trace?.record('broker.call',{kind,operation,payload});
    this._fault(operation,'before_call',{correlationId:payload?.order?.correlationId});
    let data;
    switch(operation){
      case BrokerOperation.GET_CAPABILITIES:data={provider:'simulated',operations:{query:Object.values(BrokerOperation).filter(x=>x.startsWith('GET_')||x==='RESOLVE_INSTRUMENT'),command:[BrokerOperation.PLACE_ORDER,BrokerOperation.MODIFY_ORDER,BrokerOperation.CANCEL_ORDER],stream:[BrokerOperation.STREAM_MARKET,BrokerOperation.STREAM_ORDER_UPDATES]}};break;
      case BrokerOperation.GET_READINESS:data={provider:'simulated',configured:true,queryReady:true,commandReady:true};break;
      case BrokerOperation.RESOLVE_INSTRUMENT:{const x=payload.instrument??payload;data={providerInstrumentRef:{provider:'simulated',providerInstrumentId:String(x.id??x.symbol??x.tradingSymbol),exchangeSegment:x.exchangeSegment??'SIM'}};break;}
      case BrokerOperation.GET_ACCOUNT_SNAPSHOT:data={positions:clone(this.positions),funds:clone(this.funds),orders:clone(this.orders)};break;
      case BrokerOperation.GET_POSITIONS:data=clone(this.positions);break;
      case BrokerOperation.GET_FUNDS:data=clone(this.funds);break;
      case BrokerOperation.GET_ORDERS:data=clone(this.orders);break;
      case BrokerOperation.GET_ORDER:data=clone(this.orders.find(x=>x.brokerOrderRef===payload.orderId)??null);break;
      case BrokerOperation.GET_ORDER_BY_CORRELATION:data=clone(this.orders.find(x=>x.brokerCorrelationRef===payload.correlationId)??null);this.trace?.record('recovery.reconciled',{correlationId:payload.correlationId,found:Boolean(data)});break;
      case BrokerOperation.GET_TRADES:data=clone(this.trades);break;
      case BrokerOperation.GET_ORDER_TRADES:data=clone(this.trades.filter(x=>x.brokerOrderRef===payload.orderId));break;
      case BrokerOperation.GET_HISTORICAL_TRADES:data=clone(this.trades);break;
      case BrokerOperation.GET_MARGIN:
      case BrokerOperation.GET_BASKET_MARGIN:data=this._margin(payload);break;
      case BrokerOperation.GET_LTP:
      case BrokerOperation.GET_QUOTE:data=this.market?.snapshot(payload.instruments)??[];break;
      case BrokerOperation.PLACE_ORDER:data=await this._place(payload);break;
      case BrokerOperation.MODIFY_ORDER:data=await this._modify(payload);break;
      case BrokerOperation.CANCEL_ORDER:data=await this._cancel(payload);break;
      default:throw new TypeError(`Unsupported simulated operation ${operation}`);
    }
    return {contractVersion:'1.0',provider:'simulated',kind,operation,observedAt:new Date(this.clock.now()).toISOString(),providerOverheadMicros:0,data};
  }
  async openStream({operation,onEvent,onState}){
    if(operation===BrokerOperation.STREAM_ORDER_UPDATES){
      const listener=data=>onEvent?.({contractVersion:'1.0',provider:'simulated',kind:BrokerOperationKind.STREAM,operation,observedAt:new Date(this.clock.now()).toISOString(),data:clone(data)});
      this.orderListeners.add(listener);onState?.({state:'OPEN',stream:'ORDER_UPDATES'});
      return {close:()=>{this.orderListeners.delete(listener);onState?.({state:'CLOSED',stream:'ORDER_UPDATES'});}};
    }
    if(operation===BrokerOperation.STREAM_MARKET){
      const off=this.market?.subscribe(data=>onEvent?.({contractVersion:'1.0',provider:'simulated',kind:BrokerOperationKind.STREAM,operation,observedAt:new Date(this.clock.now()).toISOString(),data:clone(data)}));
      onState?.({state:'OPEN',stream:'MARKET'});
      return {close:()=>{off?.();onState?.({state:'CLOSED',stream:'MARKET'});}};
    }
    throw new TypeError(`Unsupported simulated stream ${operation}`);
  }
}
