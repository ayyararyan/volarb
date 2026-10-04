// Transitional JavaScript compatibility contract for legacy Dhan/testkit consumers.
// Canonical Execution Engine implementation lives in execution-engine/volarb_execution/.

export const BrokerOperationKind = Object.freeze({
  QUERY:'QUERY',
  COMMAND:'COMMAND',
  STREAM:'STREAM'
});

export const BrokerOperation = Object.freeze({
  GET_CAPABILITIES:'GET_CAPABILITIES',
  GET_READINESS:'GET_READINESS',
  RESOLVE_INSTRUMENT:'RESOLVE_INSTRUMENT',
  GET_ACCOUNT_SNAPSHOT:'GET_ACCOUNT_SNAPSHOT',
  GET_POSITIONS:'GET_POSITIONS',
  GET_FUNDS:'GET_FUNDS',
  GET_ORDERS:'GET_ORDERS',
  GET_ORDER:'GET_ORDER',
  GET_ORDER_BY_CORRELATION:'GET_ORDER_BY_CORRELATION',
  GET_TRADES:'GET_TRADES',
  GET_ORDER_TRADES:'GET_ORDER_TRADES',
  GET_HISTORICAL_TRADES:'GET_HISTORICAL_TRADES',
  GET_MARGIN:'GET_MARGIN',
  GET_BASKET_MARGIN:'GET_BASKET_MARGIN',
  GET_LTP:'GET_LTP',
  GET_QUOTE:'GET_QUOTE',
  PLACE_ORDER:'PLACE_ORDER',
  MODIFY_ORDER:'MODIFY_ORDER',
  CANCEL_ORDER:'CANCEL_ORDER',
  STREAM_MARKET:'STREAM_MARKET',
  STREAM_ORDER_UPDATES:'STREAM_ORDER_UPDATES'
});

const QUERY=new Set([
  BrokerOperation.GET_CAPABILITIES,BrokerOperation.GET_READINESS,BrokerOperation.RESOLVE_INSTRUMENT,
  BrokerOperation.GET_ACCOUNT_SNAPSHOT,BrokerOperation.GET_POSITIONS,BrokerOperation.GET_FUNDS,
  BrokerOperation.GET_ORDERS,BrokerOperation.GET_ORDER,BrokerOperation.GET_ORDER_BY_CORRELATION,
  BrokerOperation.GET_TRADES,BrokerOperation.GET_ORDER_TRADES,BrokerOperation.GET_HISTORICAL_TRADES,
  BrokerOperation.GET_MARGIN,BrokerOperation.GET_BASKET_MARGIN,BrokerOperation.GET_LTP,BrokerOperation.GET_QUOTE
]);
const COMMAND=new Set([BrokerOperation.PLACE_ORDER,BrokerOperation.MODIFY_ORDER,BrokerOperation.CANCEL_ORDER]);
const STREAM=new Set([BrokerOperation.STREAM_MARKET,BrokerOperation.STREAM_ORDER_UPDATES]);

export function brokerOperationKind(operation){
  if(QUERY.has(operation)) return BrokerOperationKind.QUERY;
  if(COMMAND.has(operation)) return BrokerOperationKind.COMMAND;
  if(STREAM.has(operation)) return BrokerOperationKind.STREAM;
  return null;
}

export function assertBrokerRequest({kind,operation}){
  if(!Object.values(BrokerOperationKind).includes(kind)) throw new TypeError('Unknown broker operation kind');
  if(!Object.values(BrokerOperation).includes(operation)) throw new TypeError(`Unknown broker operation: ${operation}`);
  const expected=brokerOperationKind(operation);
  if(expected!==kind) throw new TypeError(`Broker operation ${operation} requires ${expected}, received ${kind}`);
  return true;
}
