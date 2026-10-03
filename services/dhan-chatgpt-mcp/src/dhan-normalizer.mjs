export const BROKER_FACT_CONTRACT_VERSION = '1.0';

const number = (value) => { const n = Number(value); return Number.isFinite(n) ? n : null; };
const integer = (value) => { const n = Number(value); return Number.isInteger(n) ? n : null; };
const text = (value) => value === null || value === undefined ? null : String(value);
const unwrap = (value) => value?.data ?? value;

const ORDER_STATUS = Object.freeze({
  TRANSIT: 'PENDING', PENDING: 'PENDING', PART_TRADED: 'PARTIALLY_FILLED',
  TRADED: 'FILLED', CANCELLED: 'CANCELLED', REJECTED: 'REJECTED', EXPIRED: 'EXPIRED'
});

export function normalizeDhanOrder(raw = {}) {
  return {
    brokerOrderRef: text(raw.orderId),
    brokerCorrelationRef: text(raw.correlationId),
    exchangeOrderRef: text(raw.exchangeOrderId),
    instrument: { provider: 'dhan', providerInstrumentId: text(raw.securityId), exchangeSegment: text(raw.exchangeSegment) },
    side: text(raw.transactionType), productType: text(raw.productType),
    orderType: text(raw.orderType), validity: text(raw.validity),
    status: ORDER_STATUS[String(raw.orderStatus ?? '').toUpperCase()] || 'UNKNOWN',
    requestedQuantity: integer(raw.quantity), filledQuantity: integer(raw.filledQty),
    remainingQuantity: integer(raw.remainingQuantity), limitPrice: number(raw.price),
    triggerPrice: number(raw.triggerPrice), averageFillPrice: number(raw.averageTradedPrice),
    providerTimestamps: { created: text(raw.createTime), updated: text(raw.updateTime), exchange: text(raw.exchangeTime) },
    rejection: raw.omsErrorCode || raw.omsErrorDescription
      ? { providerCode: text(raw.omsErrorCode), description: text(raw.omsErrorDescription) } : null
  };
}

export function normalizeDhanTrade(raw = {}) {
  return {
    brokerOrderRef: text(raw.orderId), exchangeOrderRef: text(raw.exchangeOrderId),
    exchangeTradeRef: text(raw.exchangeTradeId),
    instrument: { provider: 'dhan', providerInstrumentId: text(raw.securityId), exchangeSegment: text(raw.exchangeSegment) },
    side: text(raw.transactionType), productType: text(raw.productType), orderType: text(raw.orderType),
    quantity: integer(raw.tradedQuantity), price: number(raw.tradedPrice),
    providerTimestamps: { created: text(raw.createTime), updated: text(raw.updateTime), exchange: text(raw.exchangeTime) }
  };
}

export function normalizeDhanPosition(raw = {}) {
  return {
    instrument: { provider: 'dhan', providerInstrumentId: text(raw.securityId), exchangeSegment: text(raw.exchangeSegment) },
    tradingSymbol: text(raw.tradingSymbol), productType: text(raw.productType), positionType: text(raw.positionType),
    netQuantity: integer(raw.netQty), buyQuantity: integer(raw.buyQty), sellQuantity: integer(raw.sellQty),
    buyAveragePrice: number(raw.buyAvg), sellAveragePrice: number(raw.sellAvg), costPrice: number(raw.costPrice),
    realizedPnl: number(raw.realizedProfit), unrealizedPnl: number(raw.unrealizedProfit)
  };
}

export function normalizeDhanFunds(raw = {}) {
  return {
    availableBalance: number(raw.availabelBalance ?? raw.availableBalance),
    startOfDayLimit: number(raw.sodLimit), collateralAmount: number(raw.collateralAmount),
    receivableAmount: number(raw.receiveableAmount ?? raw.receivableAmount),
    utilizedAmount: number(raw.utilizedAmount), blockedPayoutAmount: number(raw.blockedPayoutAmount),
    withdrawableBalance: number(raw.withdrawableBalance)
  };
}

export function normalizeDhanMargin(raw = {}) {
  return {
    totalMargin: number(raw.totalMargin ?? raw.total_margin),
    spanMargin: number(raw.spanMargin ?? raw.span_margin),
    exposureMargin: number(raw.exposureMargin ?? raw.exposure_margin),
    variableMargin: number(raw.variableMargin ?? raw.variable_margin),
    equityMargin: number(raw.equityMargin ?? raw.equity_margin),
    foMargin: number(raw.foMargin ?? raw.fo_margin),
    commodityMargin: number(raw.commodityMargin ?? raw.commodity_margin),
    availableBalance: number(raw.availableBalance ?? raw.available_balance),
    insufficientBalance: number(raw.insufficientBalance ?? raw.insufficient_balance),
    brokerage: number(raw.brokerage), leverage: number(raw.leverage),
    currency: text(raw.currency), hedgeBenefit: number(raw.hedgeBenefit ?? raw.hedge_benefit)
  };
}

export function normalizeDhanInstrument(raw = {}) {
  return {
    providerInstrumentRef: { provider: 'dhan', providerInstrumentId: text(raw.securityId), exchangeSegment: text(raw.exchangeSegment) },
    tradingSymbol: text(raw.tradingSymbol), underlyingSymbol: text(raw.underlyingSymbol),
    expiry: text(raw.expiry), strike: number(raw.strike), optionType: text(raw.optionType),
    instrumentType: text(raw.instrumentType), lotSize: integer(raw.lotSize),
    tickSize: number(raw.tickSizeRupees), freezeQuantity: integer(raw.freezeQuantity)
  };
}

export function normalizeDhanMutationAck(raw = {}) {
  return {
    brokerOrderRef: text(raw.orderId),
    status: ORDER_STATUS[String(raw.orderStatus ?? '').toUpperCase()] || text(raw.orderStatus) || 'UNKNOWN'
  };
}

export function normalizeDhanQuote(raw) {
  const source = unwrap(raw) || {}, out = [];
  for (const [exchangeSegment, instruments] of Object.entries(source)) {
    if (!instruments || typeof instruments !== 'object') continue;
    for (const [securityId, quote] of Object.entries(instruments)) {
      const buys = Array.isArray(quote?.depth?.buy) ? quote.depth.buy : [];
      const sells = Array.isArray(quote?.depth?.sell) ? quote.depth.sell : [];
      out.push({
        instrument: { provider: 'dhan', providerInstrumentId: String(securityId), exchangeSegment },
        lastPrice: number(quote?.last_price), lastTradeTime: text(quote?.last_trade_time),
        volume: number(quote?.volume), openInterest: number(quote?.oi),
        depth: {
          bids: buys.map(x => ({ price: number(x.price), quantity: integer(x.quantity), orders: integer(x.orders) })),
          asks: sells.map(x => ({ price: number(x.price), quantity: integer(x.quantity), orders: integer(x.orders) }))
        }
      });
    }
  }
  return out;
}

export function normalizeDhanLtp(raw) {
  const source = unwrap(raw) || {}, out = [];
  for (const [exchangeSegment, instruments] of Object.entries(source)) {
    if (!instruments || typeof instruments !== 'object') continue;
    for (const [securityId, quote] of Object.entries(instruments)) {
      out.push({
        instrument: { provider: 'dhan', providerInstrumentId: String(securityId), exchangeSegment },
        lastPrice: number(quote?.last_price)
      });
    }
  }
  return out;
}

export function unwrapDhan(value) { return unwrap(value); }
