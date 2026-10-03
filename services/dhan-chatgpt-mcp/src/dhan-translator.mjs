import { createHash } from 'node:crypto';
import {
  ProviderCommandOutcome,
  ProviderError,
  ProviderErrorCategory,
  ProviderErrorCode,
  ProviderOperationKind
} from './provider-error.mjs';

function invalid(message, operation = 'translate_request') {
  return new ProviderError({
    category: ProviderErrorCategory.INVALID_REQUEST,
    code: ProviderErrorCode.INVALID_REQUEST,
    message,
    operation,
    kind: ProviderOperationKind.QUERY,
    outcome: ProviderCommandOutcome.NOT_APPLICABLE,
    provider: { key:'dhan', reason:'BROKER_NEUTRAL_TRANSLATION' }
  });
}
function need(value, name, operation) {
  if (value === undefined || value === null || value === '') throw invalid(`Missing broker-neutral field: ${name}`, operation);
  return value;
}
function providerRef(order, operation) {
  const ref = order?.providerInstrumentRef ?? order?.instrument?.providerInstrumentRef ?? order?.instrument;
  if (!ref || typeof ref !== 'object') throw invalid('Missing provider instrument reference', operation);
  if (ref.provider && ref.provider !== 'dhan') throw invalid(`Instrument reference belongs to provider ${ref.provider}, not dhan`, operation);
  return {
    securityId: String(need(ref.providerInstrumentId ?? ref.securityId, 'providerInstrumentId', operation)),
    exchangeSegment: String(need(ref.exchangeSegment, 'exchangeSegment', operation))
  };
}

export class DhanCorrelationProjector {
  constructor() { this.nativeToCore = new Map(); }
  project(coreCorrelationId) {
    const core = String(need(coreCorrelationId, 'correlationId', 'project_correlation'));
    const native = 'v' + createHash('sha256').update(core).digest('hex').slice(0,29);
    const existing = this.nativeToCore.get(native);
    if (existing && existing !== core) {
      throw new ProviderError({
        category: ProviderErrorCategory.PROVIDER_INTERNAL,
        code: ProviderErrorCode.INTERNAL_FAILURE,
        message: 'Deterministic Dhan correlation projection collision',
        operation:'project_correlation',
        kind:ProviderOperationKind.COMMAND,
        outcome:ProviderCommandOutcome.KNOWN_NOT_APPLIED,
        provider:{key:'dhan',reason:'CORRELATION_COLLISION'}
      });
    }
    this.nativeToCore.set(native, core);
    return native;
  }
  coreFor(nativeCorrelationId) { return this.nativeToCore.get(String(nativeCorrelationId)) ?? null; }
}

export class DhanTranslator {
  constructor({ correlationProjector = new DhanCorrelationProjector() } = {}) {
    this.correlationProjector = correlationProjector;
  }

  instrument(ref, operation='translate_instrument') {
    return providerRef({ providerInstrumentRef: ref }, operation);
  }

  instruments(list, operation='translate_instruments') {
    if (!Array.isArray(list) || list.length < 1) throw invalid('At least one instrument reference is required', operation);
    return list.map(x => this.instrument(x?.providerInstrumentRef ?? x, operation));
  }

  order(order) {
    const operation='place_order';
    if (!order || typeof order !== 'object') throw invalid('Order request is required', operation);
    const instrument=providerRef(order, operation);
    const correlationId=this.correlationProjector.project(order.correlationId);
    const quantity=Number(need(order.quantity,'quantity',operation));
    if (!Number.isInteger(quantity) || quantity <= 0) throw invalid('Order quantity must be a positive integer', operation);
    return {
      coreCorrelationId:String(order.correlationId),
      providerCorrelationRef:correlationId,
      dhanOrder:{
        correlationId,
        transactionType:String(need(order.side ?? order.transactionType,'side',operation)).toUpperCase(),
        exchangeSegment:instrument.exchangeSegment,
        productType:String(need(order.productType,'productType',operation)).toUpperCase(),
        orderType:String(need(order.orderType,'orderType',operation)).toUpperCase(),
        validity:String(need(order.validity,'validity',operation)).toUpperCase(),
        securityId:instrument.securityId,
        quantity,
        disclosedQuantity:Number(order.disclosedQuantity ?? 0),
        price:Number(order.price ?? 0),
        triggerPrice:Number(order.triggerPrice ?? 0),
        afterMarketOrder:Boolean(order.afterMarketOrder ?? false),
        ...(order.amoTime ? { amoTime:String(order.amoTime) } : {})
      }
    };
  }

  modify(changes) {
    const operation='modify_order';
    if (!changes || typeof changes !== 'object') throw invalid('Order modification is required', operation);
    const allowed=['orderType','legName','quantity','price','disclosedQuantity','triggerPrice','validity'];
    const out={};
    for(const key of allowed) if(changes[key] !== undefined) out[key]=changes[key];
    if (!Object.keys(out).length) throw invalid('No supported modification fields supplied', operation);
    if(out.quantity !== undefined && (!Number.isInteger(Number(out.quantity)) || Number(out.quantity)<=0)) throw invalid('Modified quantity must be a positive integer', operation);
    return out;
  }

  marginOrder(order) {
    const operation='margin_query';
    if (!order || typeof order !== 'object') throw invalid('Margin order is required', operation);
    const instrument=providerRef(order, operation);
    const quantity=Number(need(order.quantity,'quantity',operation));
    if (!Number.isInteger(quantity) || quantity <= 0) throw invalid('Margin quantity must be a positive integer', operation);
    return {
      exchangeSegment:instrument.exchangeSegment,
      transactionType:String(need(order.side ?? order.transactionType,'side',operation)).toUpperCase(),
      quantity,
      productType:String(need(order.productType,'productType',operation)).toUpperCase(),
      securityId:instrument.securityId,
      price:Number(order.price ?? 0),
      triggerPrice:Number(order.triggerPrice ?? 0)
    };
  }

  basketMargin(orders) {
    if (!Array.isArray(orders) || !orders.length) throw invalid('Basket margin requires at least one order', 'basket_margin_query');
    return orders.map(order => this.marginOrder(order));
  }

  correlation(coreCorrelationId) {
    return {
      coreCorrelationId:String(need(coreCorrelationId,'correlationId','get_order_by_correlation')),
      providerCorrelationRef:this.correlationProjector.project(coreCorrelationId)
    };
  }
}
