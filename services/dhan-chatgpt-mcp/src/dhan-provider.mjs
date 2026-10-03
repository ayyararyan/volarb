// Strategy-agnostic Dhan capability facade.
//
// This class deliberately contains no strategy, sequencing, slicing, repricing,
// hedging, timing or recovery policy. It is safe to use as a thin provider from
// any authorized Volarb client; the caller owns the meaning of the request.
export class DhanProvider {
  constructor({ client, instrumentMaster }) {
    if (!client) throw new Error('DhanProvider requires a DhanClient');
    if (!instrumentMaster) throw new Error('DhanProvider requires an InstrumentMaster');
    this.client = client;
    this.instrumentMaster = instrumentMaster;
    this.providerKey = 'dhan';
  }

  resolveInstrument(identity) { return this.instrumentMaster.resolveInstrument(identity); }

  placeOrder(order) { return this.client.placeOrder(order); }
  modifyOrder(orderId, changes) { return this.client.modifyOrder(orderId, changes); }
  cancelOrder(orderId) { return this.client.cancelOrder(orderId); }

  getOrder(orderId) { return this.client.getOrder(orderId); }
  getOrderByCorrelation(correlationId) { return this.client.getOrderByCorrelation(correlationId); }
  getOrderTrades(orderId) { return this.client.getOrderTrades(orderId); }
  getOrders() { return this.client.getOrders(); }
  getTrades() { return this.client.getTrades(); }

  getPositions() { return this.client.getPositions(); }
  getHoldings() { return this.client.getHoldings(); }
  getFunds() { return this.client.getFunds(); }

  getMargin(order) { return this.client.getMargin(order); }
  getBasketMargin(orders, options) { return this.client.getBasketMargin(orders, options); }

  getLtp(instruments) { return this.client.getLtp(instruments); }
  getQuote(instruments) { return this.client.getQuote(instruments); }
  getOptionExpiries(request) { return this.client.getOptionExpiries(request); }
  getOptionChain(request) { return this.client.getOptionChain(request); }

  getProfile() { return this.client.getProfile(); }
  getWhitelistedIps() { return this.client.getWhitelistedIps(); }
}
