export const PROVIDER_ERROR_CONTRACT_VERSION = '1.0';

export const ProviderOperationKind = Object.freeze({
  COMMAND: 'COMMAND',
  QUERY: 'QUERY',
  STREAM: 'STREAM'
});

export const ProviderCommandOutcome = Object.freeze({
  NOT_APPLICABLE: 'NOT_APPLICABLE',
  KNOWN_NOT_APPLIED: 'KNOWN_NOT_APPLIED',
  UNKNOWN: 'UNKNOWN'
});

export const ProviderErrorCategory = Object.freeze({
  AUTHENTICATION: 'AUTHENTICATION',
  AUTHORIZATION: 'AUTHORIZATION',
  ACCOUNT_STATE: 'ACCOUNT_STATE',
  RATE_LIMIT: 'RATE_LIMIT',
  INVALID_REQUEST: 'INVALID_REQUEST',
  ORDER_REJECTED: 'ORDER_REJECTED',
  DATA_UNAVAILABLE: 'DATA_UNAVAILABLE',
  RESOURCE_NOT_FOUND: 'RESOURCE_NOT_FOUND',
  PROVIDER_INTERNAL: 'PROVIDER_INTERNAL',
  NETWORK: 'NETWORK',
  TIMEOUT: 'TIMEOUT',
  PROTOCOL: 'PROTOCOL',
  UNSUPPORTED: 'UNSUPPORTED',
  UNKNOWN: 'UNKNOWN'
});

export const ProviderErrorCode = Object.freeze({
  AUTHENTICATION_FAILED: 'PROVIDER.AUTHENTICATION_FAILED',
  AUTHORIZATION_FAILED: 'PROVIDER.AUTHORIZATION_FAILED',
  ACCOUNT_STATE_INVALID: 'PROVIDER.ACCOUNT_STATE_INVALID',
  RATE_LIMITED: 'PROVIDER.RATE_LIMITED',
  INVALID_REQUEST: 'PROVIDER.INVALID_REQUEST',
  ORDER_REJECTED: 'PROVIDER.ORDER_REJECTED',
  DATA_UNAVAILABLE: 'PROVIDER.DATA_UNAVAILABLE',
  RESOURCE_NOT_FOUND: 'PROVIDER.RESOURCE_NOT_FOUND',
  INTERNAL_FAILURE: 'PROVIDER.INTERNAL_FAILURE',
  NETWORK_FAILURE: 'PROVIDER.NETWORK_FAILURE',
  TIMEOUT: 'PROVIDER.TIMEOUT',
  PROTOCOL_FAILURE: 'PROVIDER.PROTOCOL_FAILURE',
  UNSUPPORTED: 'PROVIDER.UNSUPPORTED',
  UNKNOWN: 'PROVIDER.UNKNOWN'
});

const CATEGORY_SET = new Set(Object.values(ProviderErrorCategory));
const CODE_SET = new Set(Object.values(ProviderErrorCode));
const KIND_SET = new Set(Object.values(ProviderOperationKind));
const OUTCOME_SET = new Set(Object.values(ProviderCommandOutcome));

export class ProviderError extends Error {
  constructor({
    category,
    code,
    message,
    operation,
    kind,
    outcome,
    provider,
    observedAt = new Date().toISOString(),
    cause
  }) {
    if (!CATEGORY_SET.has(category)) throw new Error(`Unknown provider error category: ${category}`);
    if (!CODE_SET.has(code)) throw new Error(`Unknown provider error code: ${code}`);
    if (!KIND_SET.has(kind)) throw new Error(`Unknown provider operation kind: ${kind}`);
    if (!OUTCOME_SET.has(outcome)) throw new Error(`Unknown provider command outcome: ${outcome}`);
    super(message || code, cause ? { cause } : undefined);
    this.name = 'ProviderError';
    this.contractVersion = PROVIDER_ERROR_CONTRACT_VERSION;
    this.category = category;
    this.code = code;
    this.operation = operation;
    this.kind = kind;
    this.outcome = outcome;
    this.provider = Object.freeze({ ...(provider || {}) });
    this.observedAt = observedAt;
  }

  toJSON() {
    return {
      name: this.name,
      contractVersion: this.contractVersion,
      category: this.category,
      code: this.code,
      message: this.message,
      operation: this.operation,
      kind: this.kind,
      outcome: this.outcome,
      provider: this.provider,
      observedAt: this.observedAt
    };
  }
}

export function isProviderError(error) {
  return error instanceof ProviderError || (
    error?.name === 'ProviderError' &&
    error?.contractVersion === PROVIDER_ERROR_CONTRACT_VERSION &&
    CATEGORY_SET.has(error?.category) &&
    CODE_SET.has(error?.code)
  );
}
