import {
  ProviderCommandOutcome,
  ProviderError,
  ProviderErrorCategory,
  ProviderErrorCode,
  ProviderOperationKind
} from './provider-error.mjs';
import { mapDhanError } from './dhan-error-mapper.mjs';
import { dhanMutationNotReadyError, dhanNotConfiguredError } from './dhan-config.mjs';

const unwrap = (value) => value?.data ?? value;

function networkError(message, reason, cause) {
  return new ProviderError({
    category: ProviderErrorCategory.NETWORK,
    code: ProviderErrorCode.NETWORK_FAILURE,
    message,
    operation: 'provider_readiness',
    kind: ProviderOperationKind.COMMAND,
    outcome: ProviderCommandOutcome.KNOWN_NOT_APPLIED,
    provider: { key: 'dhan', reason },
    cause
  });
}

export class DhanReadiness {
  constructor({ client, config, fetchFn = fetch, egressIpResolver, now = Date.now }) {
    this.client = client;
    this.config = config;
    this.fetchFn = fetchFn;
    this.egressIpResolver = egressIpResolver;
    this.now = now;
    this.cachedCommandReadyUntil = 0;
    this.lastSnapshot = null;
  }

  invalidate() { this.cachedCommandReadyUntil = 0; }

  assertQueryConfigured(operation) {
    if (!this.config.queryConfigured || !this.client) {
      throw dhanNotConfiguredError(this.config, { operation, kind: ProviderOperationKind.QUERY });
    }
  }

  _assertLocalCommandConfiguration(operation) {
    if (!this.config.queryConfigured || !this.client) {
      throw dhanNotConfiguredError(this.config, { operation, kind: ProviderOperationKind.COMMAND });
    }
    if (!this.config.commandsEnabled) {
      throw dhanMutationNotReadyError('COMMANDS_DISABLED', 'Dhan broker commands are disabled by provider configuration', { operation });
    }
    if (!this.config.staticIpConfigured) {
      throw dhanMutationNotReadyError('STATIC_IP_NOT_CONFIGURED', 'Dhan broker mutations require a configured static outbound IP', { operation });
    }
    if (!this.config.staticIpConfirmed) {
      throw dhanMutationNotReadyError('STATIC_IP_NOT_CONFIRMED', 'Dhan static outbound IP has not been explicitly confirmed', { operation });
    }
  }

  async _currentEgressIp() {
    if (this.egressIpResolver) return this.egressIpResolver();
    let response;
    try {
      response = await this.fetchFn('https://api.ipify.org?format=json', {
        signal: AbortSignal.timeout(this.config.egressCheckTimeoutMs)
      });
    } catch (error) {
      throw networkError('Could not verify current Dhan outbound IP', 'EGRESS_IP_CHECK_FAILED', error);
    }
    if (!response?.ok) throw networkError('Could not verify current Dhan outbound IP', 'EGRESS_IP_CHECK_FAILED');
    const payload = await response.json();
    if (!payload?.ip) throw networkError('Outbound IP resolver returned no IP', 'EGRESS_IP_CHECK_INVALID');
    return String(payload.ip);
  }

  async _verifyCommandReadiness(operation) {
    this._assertLocalCommandConfiguration(operation);
    let profile, whitelist;
    try {
      [profile, whitelist] = await Promise.all([this.client.getProfile(), this.client.getWhitelistedIps()]);
    } catch (error) {
      throw mapDhanError(error, { operation, kind: ProviderOperationKind.COMMAND });
    }

    const currentEgressIp = await this._currentEgressIp();
    if (currentEgressIp !== this.config.expectedEgressIp) {
      throw dhanMutationNotReadyError('STATIC_IP_MISMATCH', 'Current outbound IP differs from configured Dhan static IP', { operation });
    }
    const ips = unwrap(whitelist) || {};
    if (![ips.primaryIP, ips.secondaryIP].map(v => String(v ?? '')).includes(this.config.expectedEgressIp)) {
      throw dhanMutationNotReadyError('STATIC_IP_NOT_WHITELISTED', 'Configured outbound IP is not present in the Dhan whitelist', { operation });
    }
    const p = unwrap(profile) || {};
    if (String(p.dhanClientId ?? '') !== String(this.config.clientId)) {
      throw dhanMutationNotReadyError('ACCOUNT_IDENTITY_MISMATCH', 'Dhan account identity does not match provider configuration', { operation });
    }

    const checkedAtMs = this.now();
    this.cachedCommandReadyUntil = checkedAtMs + this.config.readinessTtlMs;
    this.lastSnapshot = Object.freeze({
      provider: 'dhan', configured: true, queryReady: true, commandsEnabled: true,
      commandReady: true, staticIpConfigured: true, staticIpConfirmed: true,
      staticIpWhitelisted: true, accountIdentityVerified: true,
      checkedAt: new Date(checkedAtMs).toISOString(),
      expiresAt: new Date(this.cachedCommandReadyUntil).toISOString(),
      blockers: Object.freeze([])
    });
    return this.lastSnapshot;
  }

  async assertCommandReady(operation) {
    this._assertLocalCommandConfiguration(operation);
    if (this.cachedCommandReadyUntil > this.now()) return this.lastSnapshot;
    return this._verifyCommandReadiness(operation);
  }

  async inspect({ refresh = false } = {}) {
    if (!this.config.queryConfigured || !this.client) {
      return {
        provider: 'dhan', configured: false, queryReady: false,
        commandsEnabled: this.config.commandsEnabled, commandReady: false,
        staticIpConfigured: this.config.staticIpConfigured, staticIpConfirmed: this.config.staticIpConfirmed,
        staticIpWhitelisted: false, accountIdentityVerified: false,
        checkedAt: new Date(this.now()).toISOString(), expiresAt: null,
        blockers: [{ code: ProviderErrorCode.NOT_CONFIGURED, reason: 'BROKER_NOT_CONFIGURED', missing: [...this.config.missingQueryConfiguration] }]
      };
    }
    if (!refresh && this.lastSnapshot && this.cachedCommandReadyUntil > this.now()) return this.lastSnapshot;
    if (!this.config.commandsEnabled) {
      return {
        provider: 'dhan', configured: true, queryReady: true, commandsEnabled: false,
        commandReady: false, staticIpConfigured: this.config.staticIpConfigured,
        staticIpConfirmed: this.config.staticIpConfirmed, staticIpWhitelisted: false,
        accountIdentityVerified: false, checkedAt: new Date(this.now()).toISOString(),
        expiresAt: null, blockers: [{ code: ProviderErrorCode.MUTATION_NOT_READY, reason: 'COMMANDS_DISABLED' }]
      };
    }
    try {
      return await this._verifyCommandReadiness('provider_readiness');
    } catch (error) {
      return {
        provider: 'dhan', configured: true,
        queryReady: error.category !== ProviderErrorCategory.AUTHENTICATION,
        commandsEnabled: true, commandReady: false,
        staticIpConfigured: this.config.staticIpConfigured, staticIpConfirmed: this.config.staticIpConfirmed,
        staticIpWhitelisted: false, accountIdentityVerified: false,
        checkedAt: new Date(this.now()).toISOString(), expiresAt: null,
        blockers: [{ code: error.code || ProviderErrorCode.UNKNOWN, category: error.category || ProviderErrorCategory.UNKNOWN, reason: error.provider?.reason || null, message: error.message }]
      };
    }
  }
}
