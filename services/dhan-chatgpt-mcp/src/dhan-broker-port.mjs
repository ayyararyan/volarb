import {
  ProviderCommandOutcome, ProviderError, ProviderErrorCategory,
  ProviderErrorCode, ProviderOperationKind
} from './provider-error.mjs';
import {
  BROKER_FACT_CONTRACT_VERSION, normalizeDhanFunds, normalizeDhanInstrument,
  normalizeDhanLtp, normalizeDhanMargin, normalizeDhanMutationAck,
  normalizeDhanOrder, normalizeDhanPosition, normalizeDhanQuote,
  normalizeDhanTrade, unwrapDhan
} from './dhan-normalizer.mjs';
import { DhanTranslator } from './dhan-translator.mjs';

export const DhanBrokerOperation = Object.freeze({
  GET_CAPABILITIES:'GET_CAPABILITIES', GET_READINESS:'GET_READINESS',
  RESOLVE_INSTRUMENT:'RESOLVE_INSTRUMENT', GET_ACCOUNT_SNAPSHOT:'GET_ACCOUNT_SNAPSHOT',
  GET_POSITIONS:'GET_POSITIONS', GET_FUNDS:'GET_FUNDS', GET_ORDERS:'GET_ORDERS',
  GET_ORDER:'GET_ORDER', GET_ORDER_BY_CORRELATION:'GET_ORDER_BY_CORRELATION',
  GET_TRADES:'GET_TRADES', GET_ORDER_TRADES:'GET_ORDER_TRADES',
  GET_HISTORICAL_TRADES:'GET_HISTORICAL_TRADES', GET_MARGIN:'GET_MARGIN',
  GET_BASKET_MARGIN:'GET_BASKET_MARGIN', GET_LTP:'GET_LTP', GET_QUOTE:'GET_QUOTE',
  PLACE_ORDER:'PLACE_ORDER', MODIFY_ORDER:'MODIFY_ORDER', CANCEL_ORDER:'CANCEL_ORDER',
  STREAM_MARKET:'STREAM_MARKET', STREAM_ORDER_UPDATES:'STREAM_ORDER_UPDATES'
});
const QUERY=ProviderOperationKind.QUERY, COMMAND=ProviderOperationKind.COMMAND;
const invalidRequest=(message,operation,kind=QUERY)=>new ProviderError({
  category:ProviderErrorCategory.INVALID_REQUEST, code:ProviderErrorCode.INVALID_REQUEST,
  message, operation, kind,
  outcome:kind===COMMAND?ProviderCommandOutcome.KNOWN_NOT_APPLIED:ProviderCommandOutcome.NOT_APPLICABLE,
  provider:{key:'dhan',reason:'BROKER_PORT_CONTRACT'}
});
const asArray=(value)=>{const u=unwrapDhan(value);return Array.isArray(u)?u:[];};
function capabilities(config){return{
  provider:'dhan', queryConfigured:config.queryConfigured, commandsEnabled:config.commandsEnabled,
  operations:{
    query:['GET_READINESS','RESOLVE_INSTRUMENT','GET_ACCOUNT_SNAPSHOT','GET_POSITIONS','GET_FUNDS','GET_ORDERS','GET_ORDER','GET_ORDER_BY_CORRELATION','GET_TRADES','GET_ORDER_TRADES','GET_HISTORICAL_TRADES','GET_MARGIN','GET_BASKET_MARGIN','GET_LTP','GET_QUOTE'],
    command:['PLACE_ORDER','MODIFY_ORDER','CANCEL_ORDER'], stream:['STREAM_MARKET','STREAM_ORDER_UPDATES']
  },
  streamStatus:'LIVE_MARKET_AND_ORDER_UPDATES',
  notes:['Execution Slicing is upstream; Dhan native order slicing is not used.','A strategy leg is transmitted as an ordinary broker order; Dhan has no strategy-leg semantics.']
};}

export class DhanBrokerPort {
  constructor({provider,readiness,config,streams=null,translator=new DhanTranslator(),now=Date.now}){this.provider=provider;this.readiness=readiness;this.config=config;this.streams=streams;this.translator=translator;this.now=now;}
  async call({kind,operation,payload={}}){
    if(!Object.values(ProviderOperationKind).includes(kind)) throw invalidRequest('Broker port request has invalid kind',operation||'unknown');
    if(!Object.values(DhanBrokerOperation).includes(operation)) throw invalidRequest(`Unsupported Dhan broker operation: ${operation}`,operation||'unknown',kind);
    const spec=this._spec(operation);
    if(spec.kind!==kind) throw invalidRequest(`Operation ${operation} requires kind ${spec.kind}, received ${kind}`,operation,kind);
    const started=process.hrtime.bigint(), raw=await spec.run(payload), data=spec.normalize(raw), ended=process.hrtime.bigint();
    return {contractVersion:BROKER_FACT_CONTRACT_VERSION,provider:'dhan',kind,operation,observedAt:new Date(this.now()).toISOString(),providerOverheadMicros:Number((ended-started)/1000n),data};
  }
  async openStream({operation,payload={},onEvent,onError,onState}){
    if(![DhanBrokerOperation.STREAM_MARKET,DhanBrokerOperation.STREAM_ORDER_UPDATES].includes(operation)) throw invalidRequest(`Unsupported Dhan stream operation: ${operation}`,operation,ProviderOperationKind.STREAM);
    if(!this.streams) throw new ProviderError({category:ProviderErrorCategory.UNSUPPORTED,code:ProviderErrorCode.UNSUPPORTED,message:'Dhan stream transport is not configured',operation,kind:ProviderOperationKind.STREAM,outcome:ProviderCommandOutcome.NOT_APPLICABLE,provider:{key:'dhan',reason:'STREAM_TRANSPORT_UNAVAILABLE'}});
    const wrap=(data)=>onEvent?.({contractVersion:BROKER_FACT_CONTRACT_VERSION,provider:'dhan',kind:ProviderOperationKind.STREAM,operation,observedAt:new Date(this.now()).toISOString(),data});
    if(operation===DhanBrokerOperation.STREAM_MARKET) return this.streams.openMarket({...payload,onEvent:wrap,onError,onState});
    return this.streams.openOrders({...payload,onEvent:wrap,onError,onState});
  }
  _spec(operation){
    const p=this.provider;
    switch(operation){
      case DhanBrokerOperation.GET_CAPABILITIES:return{kind:QUERY,run:async()=>capabilities(this.config),normalize:x=>x};
      case DhanBrokerOperation.GET_READINESS:return{kind:QUERY,run:async x=>this.readiness.inspect({refresh:Boolean(x.refresh)}),normalize:x=>x};
      case DhanBrokerOperation.RESOLVE_INSTRUMENT:return{kind:QUERY,run:x=>p.resolveInstrument(x.instrument??x),normalize:normalizeDhanInstrument};
      case DhanBrokerOperation.GET_ACCOUNT_SNAPSHOT:return{kind:QUERY,run:async()=>{const [positions,funds,orders]=await Promise.all([p.getPositions(),p.getFunds(),p.getOrders()]);return{positions,funds,orders};},normalize:x=>({positions:asArray(x.positions).map(normalizeDhanPosition),funds:normalizeDhanFunds(unwrapDhan(x.funds)||{}),orders:asArray(x.orders).map(normalizeDhanOrder)})};
      case DhanBrokerOperation.GET_POSITIONS:return{kind:QUERY,run:()=>p.getPositions(),normalize:x=>asArray(x).map(normalizeDhanPosition)};
      case DhanBrokerOperation.GET_FUNDS:return{kind:QUERY,run:()=>p.getFunds(),normalize:x=>normalizeDhanFunds(unwrapDhan(x)||{})};
      case DhanBrokerOperation.GET_ORDERS:return{kind:QUERY,run:()=>p.getOrders(),normalize:x=>asArray(x).map(normalizeDhanOrder)};
      case DhanBrokerOperation.GET_ORDER:return{kind:QUERY,run:x=>p.getOrder(x.orderId),normalize:x=>normalizeDhanOrder(unwrapDhan(x)||{})};
      case DhanBrokerOperation.GET_ORDER_BY_CORRELATION:return{kind:QUERY,run:async x=>{const c=this.translator.correlation(x.correlationId);return{raw:await p.getOrderByCorrelation(c.providerCorrelationRef),correlation:c};},normalize:x=>({...normalizeDhanOrder(unwrapDhan(x.raw)||{}),coreCorrelationId:x.correlation.coreCorrelationId,providerCorrelationRef:x.correlation.providerCorrelationRef})};
      case DhanBrokerOperation.GET_TRADES:return{kind:QUERY,run:()=>p.getTrades(),normalize:x=>asArray(x).map(normalizeDhanTrade)};
      case DhanBrokerOperation.GET_ORDER_TRADES:return{kind:QUERY,run:x=>p.getOrderTrades(x.orderId),normalize:x=>asArray(x).map(normalizeDhanTrade)};
      case DhanBrokerOperation.GET_HISTORICAL_TRADES:return{kind:QUERY,run:x=>p.getHistoricalTrades(x),normalize:x=>asArray(x).map(normalizeDhanTrade)};
      case DhanBrokerOperation.GET_MARGIN:return{kind:QUERY,run:x=>p.getMargin(this.translator.marginOrder(x.order)),normalize:x=>normalizeDhanMargin(unwrapDhan(x)||{})};
      case DhanBrokerOperation.GET_BASKET_MARGIN:return{kind:QUERY,run:x=>p.getBasketMargin(this.translator.basketMargin(x.orders),x.options),normalize:x=>normalizeDhanMargin(unwrapDhan(x)||{})};
      case DhanBrokerOperation.GET_LTP:return{kind:QUERY,run:x=>p.getLtp(this.translator.instruments(x.instruments,'get_ltp')),normalize:normalizeDhanLtp};
      case DhanBrokerOperation.GET_QUOTE:return{kind:QUERY,run:x=>p.getQuote(this.translator.instruments(x.instruments,'get_quote')),normalize:normalizeDhanQuote};
      case DhanBrokerOperation.PLACE_ORDER:return{kind:COMMAND,run:async x=>{const translated=this.translator.order(x.order);return{raw:await p.placeOrder(translated.dhanOrder),translated};},normalize:x=>({...normalizeDhanMutationAck(x.raw),coreCorrelationId:x.translated.coreCorrelationId,providerCorrelationRef:x.translated.providerCorrelationRef})};
      case DhanBrokerOperation.MODIFY_ORDER:return{kind:COMMAND,run:x=>p.modifyOrder(x.orderId,this.translator.modify(x.changes)),normalize:normalizeDhanMutationAck};
      case DhanBrokerOperation.CANCEL_ORDER:return{kind:COMMAND,run:x=>p.cancelOrder(x.orderId),normalize:normalizeDhanMutationAck};
      default:throw invalidRequest(`Unsupported Dhan broker operation: ${operation}`,operation);
    }
  }
}
