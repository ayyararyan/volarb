import { mapDhanError, dhanRejectedOrderError } from './dhan-error-mapper.mjs';
import { ProviderOperationKind } from './provider-error.mjs';

// Strategy-agnostic Dhan capability facade.
//
// Every failure leaving this boundary is a broker-neutral ProviderError.
// Dhan-native codes/messages remain attached only as provider provenance.
export class DhanProvider {
  constructor({ client, instrumentMaster }) {
    if (!client) throw new Error('DhanProvider requires a DhanClient');
    if (!instrumentMaster) throw new Error('DhanProvider requires an InstrumentMaster');
    this.client = client;
    this.instrumentMaster = instrumentMaster;
    this.providerKey = 'dhan';
  }

  _invoke(operation, kind, fn, { rejectOrderStatus = false } = {}) {
    let result;
    try {
      result = fn();
    } catch (error) {
      throw mapDhanError(error, { operation, kind });
    }

    return Promise.resolve(result).then(
      (value) => {
        if (rejectOrderStatus && String(value?.orderStatus || '').toUpperCase() === 'REJECTED') {
          throw dhanRejectedOrderError(value, { operation });
        }
        return value;
      },
      (error) => {
        throw mapDhanError(error, { operation, kind });
      }
    );
  }

  _query(operation, fn) {
    return this._invoke(operation, ProviderOperationKind.QUERY, fn);
  }

  _command(operation, fn) {
    return this._invoke(operation, ProviderOperationKind.COMMAND, fn, { rejectOrderStatus: true });
  }

  resolveInstrument(identity) {
    return this._query('resolve_instrument', () => this.instrumentMaster.resolveInstrument(identity));
  }

  placeOrder(order) { return this._command('place_order', () => this.client.placeOrder(order)); }
  modifyOrder(orderId, changes) { return this._command('modify_order', () => this.client.modifyOrder(orderId, changes)); }
  cancelOrder(orderId) { return this._command('cancel_order', () => this.client.cancelOrder(orderId)); }

  getOrder(orderId) { return this._query('get_order', () => this.client.getOrder(orderId)); }
  getOrderByCorrelation(correlationId) { return this._query('get_order_by_correlation', () => this.client.getOrderByCorrelation(correlationId)); }
  getOrderTrades(orderId) { return this._query('get_order_trades', () => this.client.getOrderTrades(orderId)); }
  getOrders() { return this._query('get_orders', () => this.client.getOrders()); }
  getTrades() { return this._query('get_trades', () => this.client.getTrades()); }

  getPositions() { return this._query('get_positions', () => this.client.getPositions()); }
  getHoldings() { return this._query('get_holdings', () => this.client.getHoldings()); }
  getFunds() { return this._query('get_funds', () => this.client.getFunds()); }

  getMargin(order) { return this._query('get_margin', () => this.client.getMargin(order)); }
  getBasketMargin(orders, options) { return this._query('get_basket_margin', () => this.client.getBasketMargin(orders, options)); }

  getLtp(instruments) { return this._query('get_ltp', () => this.client.getLtp(instruments)); }
  getQuote(instruments) { return this._query('get_quote', () => this.client.getQuote(instruments)); }
  getOptionExpiries(request) { return this._query('get_option_expiries', () => this.client.getOptionExpiries(request)); }
  getOptionChain(request) { return this._query('get_option_chain', () => this.client.getOptionChain(request)); }

  getProfile() { return this._query('get_profile', () => this.client.getProfile()); }
  getWhitelistedIps() { return this._query('get_whitelisted_ips', () => this.client.getWhitelistedIps()); }
}
