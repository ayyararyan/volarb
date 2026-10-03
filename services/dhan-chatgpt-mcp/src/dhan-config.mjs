import { isIP } from 'node:net';
import {
  ProviderCommandOutcome,
  ProviderError,
  ProviderErrorCategory,
  ProviderErrorCode,
  ProviderOperationKind
} from './provider-error.mjs';

const text = (value) => String(value ?? '').trim();
const yes = (value) => ['1', 'true', 'yes', 'on'].includes(text(value).toLowerCase());
const positiveInt = (value, fallback) => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
};

export function loadDhanConfig(env = process.env, { hasTokenProvider = false } = {}) {
  const clientId = text(env.DHAN_CLIENT_ID);
  const accessTokenConfigured = Boolean(text(env.DHAN_ACCESS_TOKEN));
  const credentialSourceConfigured = accessTokenConfigured || hasTokenProvider;
  const commandsEnabled = yes(env.DHAN_PROVIDER_COMMANDS_ENABLED ?? env.DHAN_EXECUTION_ENABLED);
  const expectedEgressIp = text(env.DHAN_PROVIDER_EGRESS_IP ?? env.DHAN_EXECUTION_EGRESS_IP);
  const staticIpConfirmed = yes(env.DHAN_PROVIDER_STATIC_IP_CONFIRMED ?? env.DHAN_EXECUTION_STATIC_IP_CONFIRMED);

  const missingQueryConfiguration = [];
  if (!clientId) missingQueryConfiguration.push('DHAN_CLIENT_ID');
  if (!credentialSourceConfigured) missingQueryConfiguration.push('DHAN_ACCESS_TOKEN_OR_TOKEN_PROVIDER');

  return Object.freeze({
    providerKey: 'dhan',
    clientId,
    queryConfigured: missingQueryConfiguration.length === 0,
    missingQueryConfiguration: Object.freeze(missingQueryConfiguration),
    credentialSourceConfigured,
    accessTokenConfigured,
    commandsEnabled,
    expectedEgressIp,
    staticIpConfigured: isIP(expectedEgressIp) !== 0,
    staticIpConfirmed,
    apiBaseUrl: text(env.DHAN_API_BASE_URL) || 'https://api.dhan.co/v2',
    apiTimeoutMs: positiveInt(env.DHAN_API_TIMEOUT_MS, 15000),
    readinessTtlMs: positiveInt(env.DHAN_PROVIDER_READINESS_TTL_MS, 30000),
    egressCheckTimeoutMs: positiveInt(env.DHAN_PROVIDER_EGRESS_CHECK_TIMEOUT_MS, 5000),
    instrumentMasterUrl: text(env.DHAN_INSTRUMENT_MASTER_URL) || undefined,
    instrumentMasterTtlMs: positiveInt(env.DHAN_INSTRUMENT_MASTER_TTL_MS, 21600000)
  });
}

function outcomeFor(kind) {
  return kind === ProviderOperationKind.COMMAND
    ? ProviderCommandOutcome.KNOWN_NOT_APPLIED
    : ProviderCommandOutcome.NOT_APPLICABLE;
}

export function dhanNotConfiguredError(config, { operation, kind = ProviderOperationKind.QUERY } = {}) {
  return new ProviderError({
    category: ProviderErrorCategory.CONFIGURATION,
    code: ProviderErrorCode.NOT_CONFIGURED,
    message: `Dhan provider is not configured: missing ${config.missingQueryConfiguration.join(', ') || 'required configuration'}`,
    operation,
    kind,
    outcome: outcomeFor(kind),
    provider: {
      key: 'dhan',
      reason: 'BROKER_NOT_CONFIGURED',
      missing: [...config.missingQueryConfiguration]
    }
  });
}

export function dhanMutationNotReadyError(reason, message, { operation } = {}) {
  return new ProviderError({
    category: ProviderErrorCategory.CONFIGURATION,
    code: ProviderErrorCode.MUTATION_NOT_READY,
    message,
    operation,
    kind: ProviderOperationKind.COMMAND,
    outcome: ProviderCommandOutcome.KNOWN_NOT_APPLIED,
    provider: { key: 'dhan', reason }
  });
}
