import {
  ProviderCommandOutcome,
  ProviderError,
  ProviderErrorCategory,
  ProviderErrorCode,
  ProviderOperationKind,
  isProviderError
} from './provider-error.mjs';

const TRADING_CODE_MAP = Object.freeze({
  'DH-901': [ProviderErrorCategory.AUTHENTICATION, ProviderErrorCode.AUTHENTICATION_FAILED],
  'DH-902': [ProviderErrorCategory.AUTHORIZATION, ProviderErrorCode.AUTHORIZATION_FAILED],
  'DH-903': [ProviderErrorCategory.ACCOUNT_STATE, ProviderErrorCode.ACCOUNT_STATE_INVALID],
  'DH-904': [ProviderErrorCategory.RATE_LIMIT, ProviderErrorCode.RATE_LIMITED],
  'DH-905': [ProviderErrorCategory.INVALID_REQUEST, ProviderErrorCode.INVALID_REQUEST],
  'DH-906': [ProviderErrorCategory.ORDER_REJECTED, ProviderErrorCode.ORDER_REJECTED],
  'DH-907': [ProviderErrorCategory.DATA_UNAVAILABLE, ProviderErrorCode.DATA_UNAVAILABLE],
  'DH-908': [ProviderErrorCategory.PROVIDER_INTERNAL, ProviderErrorCode.INTERNAL_FAILURE],
  'DH-909': [ProviderErrorCategory.NETWORK, ProviderErrorCode.NETWORK_FAILURE],
  'DH-910': [ProviderErrorCategory.UNKNOWN, ProviderErrorCode.UNKNOWN]
});

const DATA_CODE_MAP = Object.freeze({
  '800': [ProviderErrorCategory.PROVIDER_INTERNAL, ProviderErrorCode.INTERNAL_FAILURE],
  '804': [ProviderErrorCategory.INVALID_REQUEST, ProviderErrorCode.INVALID_REQUEST],
  '805': [ProviderErrorCategory.RATE_LIMIT, ProviderErrorCode.RATE_LIMITED],
  '806': [ProviderErrorCategory.AUTHORIZATION, ProviderErrorCode.AUTHORIZATION_FAILED],
  '807': [ProviderErrorCategory.AUTHENTICATION, ProviderErrorCode.AUTHENTICATION_FAILED],
  '808': [ProviderErrorCategory.AUTHENTICATION, ProviderErrorCode.AUTHENTICATION_FAILED],
  '809': [ProviderErrorCategory.AUTHENTICATION, ProviderErrorCode.AUTHENTICATION_FAILED],
  '810': [ProviderErrorCategory.AUTHENTICATION, ProviderErrorCode.AUTHENTICATION_FAILED],
  '811': [ProviderErrorCategory.INVALID_REQUEST, ProviderErrorCode.INVALID_REQUEST],
  '812': [ProviderErrorCategory.INVALID_REQUEST, ProviderErrorCode.INVALID_REQUEST],
  '813': [ProviderErrorCategory.INVALID_REQUEST, ProviderErrorCode.INVALID_REQUEST],
  '814': [ProviderErrorCategory.INVALID_REQUEST, ProviderErrorCode.INVALID_REQUEST]
});

function pair(category, code) {
  return { category, code };
}

function httpFallback(status) {
  if (status === 401) return pair(ProviderErrorCategory.AUTHENTICATION, ProviderErrorCode.AUTHENTICATION_FAILED);
  if (status === 403) return pair(ProviderErrorCategory.AUTHORIZATION, ProviderErrorCode.AUTHORIZATION_FAILED);
  if (status === 404) return pair(ProviderErrorCategory.RESOURCE_NOT_FOUND, ProviderErrorCode.RESOURCE_NOT_FOUND);
  if (status === 408 || status === 504) return pair(ProviderErrorCategory.TIMEOUT, ProviderErrorCode.TIMEOUT);
  if (status === 429) return pair(ProviderErrorCategory.RATE_LIMIT, ProviderErrorCode.RATE_LIMITED);
  if (status === 400 || status === 409 || status === 422) return pair(ProviderErrorCategory.INVALID_REQUEST, ProviderErrorCode.INVALID_REQUEST);
  if (Number.isInteger(status) && status >= 500) return pair(ProviderErrorCategory.PROVIDER_INTERNAL, ProviderErrorCode.INTERNAL_FAILURE);
  return null;
}

function extractNative(error) {
  const payload = error?.payload && typeof error.payload === 'object' ? error.payload : {};
  const nativeCode = payload.errorCode ?? payload.code ?? payload.omsErrorCode ?? null;
  const nativeType = payload.errorType ?? null;
  const nativeMessage = payload.errorMessage ?? payload.message ?? payload.omsErrorDescription ?? error?.message ?? null;
  return {
    nativeCode: nativeCode === null || nativeCode === undefined ? null : String(nativeCode),
    nativeType: nativeType === null || nativeType === undefined ? null : String(nativeType),
    nativeMessage: nativeMessage === null || nativeMessage === undefined ? null : String(nativeMessage),
    omsCode: payload.omsErrorCode ?? null,
    omsDescription: payload.omsErrorDescription ?? null
  };
}

function classify(error, native) {
  if (error?.transportKind === 'AUTHENTICATION') {
    return pair(ProviderErrorCategory.AUTHENTICATION, ProviderErrorCode.AUTHENTICATION_FAILED);
  }
  if (error?.transportKind === 'TIMEOUT' || error?.name === 'AbortError') {
    return pair(ProviderErrorCategory.TIMEOUT, ProviderErrorCode.TIMEOUT);
  }
  if (error?.transportKind === 'NETWORK' || error?.name === 'TypeError') {
    return pair(ProviderErrorCategory.NETWORK, ProviderErrorCode.NETWORK_FAILURE);
  }
  if (error?.transportKind === 'PROTOCOL') {
    return pair(ProviderErrorCategory.PROTOCOL, ProviderErrorCode.PROTOCOL_FAILURE);
  }
  if (native.nativeCode && TRADING_CODE_MAP[native.nativeCode]) {
    const [category, code] = TRADING_CODE_MAP[native.nativeCode];
    return pair(category, code);
  }
  if (native.nativeCode && DATA_CODE_MAP[native.nativeCode]) {
    const [category, code] = DATA_CODE_MAP[native.nativeCode];
    return pair(category, code);
  }
  return httpFallback(error?.status) || pair(ProviderErrorCategory.UNKNOWN, ProviderErrorCode.UNKNOWN);
}

function commandOutcome(kind, category) {
  if (kind !== ProviderOperationKind.COMMAND) return ProviderCommandOutcome.NOT_APPLICABLE;

  // If the provider returned a definitive validation/rejection/access response,
  // the requested broker mutation is known not to have been applied.
  if ([
    ProviderErrorCategory.AUTHENTICATION,
    ProviderErrorCategory.AUTHORIZATION,
    ProviderErrorCategory.ACCOUNT_STATE,
    ProviderErrorCategory.RATE_LIMIT,
    ProviderErrorCategory.INVALID_REQUEST,
    ProviderErrorCategory.ORDER_REJECTED,
    ProviderErrorCategory.RESOURCE_NOT_FOUND,
    ProviderErrorCategory.UNSUPPORTED
  ].includes(category)) {
    return ProviderCommandOutcome.KNOWN_NOT_APPLIED;
  }

  // Transport loss, unreadable responses, provider internal failure and unknown
  // failures can occur after transmission. The caller must treat mutation outcome
  // as unknown rather than retrying blindly.
  return ProviderCommandOutcome.UNKNOWN;
}

export function mapDhanError(error, { operation, kind }) {
  if (isProviderError(error)) return error;

  const native = extractNative(error);
  const { category, code } = classify(error, native);
  return new ProviderError({
    category,
    code,
    message: native.nativeMessage || `Dhan provider failure during ${operation}`,
    operation,
    kind,
    outcome: commandOutcome(kind, category),
    provider: {
      key: 'dhan',
      nativeCode: native.nativeCode,
      nativeType: native.nativeType,
      nativeMessage: native.nativeMessage,
      httpStatus: Number.isInteger(error?.status) ? error.status : null,
      omsCode: native.omsCode,
      omsDescription: native.omsDescription,
      path: error?.path ?? null
    },
    cause: error
  });
}

export function dhanRejectedOrderError(response, { operation }) {
  const payload = response && typeof response === 'object' ? response : {};
  return new ProviderError({
    category: ProviderErrorCategory.ORDER_REJECTED,
    code: ProviderErrorCode.ORDER_REJECTED,
    message: payload.omsErrorDescription || payload.errorMessage || 'Dhan rejected the requested order operation',
    operation,
    kind: ProviderOperationKind.COMMAND,
    outcome: ProviderCommandOutcome.KNOWN_NOT_APPLIED,
    provider: {
      key: 'dhan',
      nativeCode: payload.errorCode ?? payload.omsErrorCode ?? null,
      nativeType: payload.errorType ?? 'Order Rejected',
      nativeMessage: payload.errorMessage ?? payload.omsErrorDescription ?? null,
      httpStatus: null,
      omsCode: payload.omsErrorCode ?? null,
      omsDescription: payload.omsErrorDescription ?? null,
      path: null
    }
  });
}

export const DHAN_DOCUMENTED_ERROR_CODES = Object.freeze({
  trading: Object.freeze(Object.keys(TRADING_CODE_MAP)),
  data: Object.freeze(Object.keys(DATA_CODE_MAP))
});
