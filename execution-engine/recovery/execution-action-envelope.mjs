import { BrokerOperationKind, assertBrokerRequest } from '../ports/broker-port.mjs';

const clone = value => value === undefined ? undefined : structuredClone(value);

function requiredText(value, name) {
  if (typeof value !== 'string' || !value.trim()) throw new TypeError(`${name} must be a non-empty string`);
  return value.trim();
}

function normalizeCreatedAt(value, nowMs) {
  if (value === undefined || value === null) return new Date(nowMs).toISOString();
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) throw new TypeError('createdAt must be a valid timestamp');
  return parsed.toISOString();
}

function defaultCorrelationId(actionId) {
  return `exec:${actionId}`;
}

export function normalizeExecutionAction(action, {
  nowMs = Date.now(),
  correlationIdFactory = defaultCorrelationId
} = {}) {
  if (!action || typeof action !== 'object' || Array.isArray(action)) {
    throw new TypeError('execution action must be an object');
  }

  const actionId = requiredText(action.actionId, 'actionId');
  const actionClass = requiredText(action.actionClass, 'actionClass');
  const originType = requiredText(action.originType, 'originType').toUpperCase();
  const originId = requiredText(action.originId, 'originId');
  const operation = requiredText(action.operation ?? action.requestedOperation, 'operation').toUpperCase();

  assertBrokerRequest({ kind: BrokerOperationKind.COMMAND, operation });

  const hasIntentId = action.intentId !== undefined && action.intentId !== null && action.intentId !== '';
  const hasIntentVersion = action.intentVersion !== undefined && action.intentVersion !== null;
  if (hasIntentId !== hasIntentVersion) {
    throw new TypeError('intentId and intentVersion must either both be present or both be absent');
  }
  if (originType !== 'INTERRUPT' && !hasIntentId) {
    throw new TypeError('non-interrupt execution actions require intentId and intentVersion');
  }

  const intentId = hasIntentId ? requiredText(String(action.intentId), 'intentId') : null;
  const intentVersion = hasIntentVersion ? Number(action.intentVersion) : null;
  if (intentVersion !== null && (!Number.isInteger(intentVersion) || intentVersion < 1)) {
    throw new TypeError('intentVersion must be a positive integer');
  }

  const sliceId = action.sliceId === undefined || action.sliceId === null
    ? null
    : requiredText(String(action.sliceId), 'sliceId');

  const requestedCorrelationId = action.correlationId === undefined || action.correlationId === null || action.correlationId === ''
    ? correlationIdFactory(actionId, action)
    : action.correlationId;
  const correlationId = requiredText(String(requestedCorrelationId), 'correlationId');

  const payload = action.payload === undefined ? {} : clone(action.payload);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new TypeError('payload must be an object');
  }

  return Object.freeze({
    actionId,
    actionClass,
    originType,
    originId,
    intentId,
    intentVersion,
    sliceId,
    correlationId,
    operation,
    payload,
    createdAt: normalizeCreatedAt(action.createdAt, nowMs)
  });
}

export function brokerRequestForExecutionAction(action) {
  const payload = clone(action.payload) ?? {};
  const identity = {
    actionId: action.actionId,
    correlationId: action.correlationId,
    intentId: action.intentId,
    intentVersion: action.intentVersion,
    sliceId: action.sliceId
  };

  if (action.operation === 'PLACE_ORDER') {
    payload.order = { ...(payload.order ?? {}), ...identity };
  } else {
    Object.assign(payload, identity);
  }

  return {
    kind: BrokerOperationKind.COMMAND,
    operation: action.operation,
    payload
  };
}
