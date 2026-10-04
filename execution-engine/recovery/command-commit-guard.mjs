import {
  ProviderCommandOutcome,
  isProviderError
} from '../contracts/provider-error.mjs';
import {
  assertBrokerPort,
  assertClockPort,
  assertLedgerPort
} from '../ports/runtime-ports.mjs';
import {
  brokerRequestForExecutionAction,
  normalizeExecutionAction
} from './execution-action-envelope.mjs';

export const CommandCommitGuardErrorCode = Object.freeze({
  STALE_INTENT: 'COMMAND_COMMIT_GUARD.STALE_INTENT',
  INTERRUPT_CONFLICT: 'COMMAND_COMMIT_GUARD.INTERRUPT_CONFLICT',
  INTEGRITY_DENIED: 'COMMAND_COMMIT_GUARD.INTEGRITY_DENIED',
  DUPLICATE_ACTION: 'COMMAND_COMMIT_GUARD.DUPLICATE_ACTION',
  CORRELATION_COLLISION: 'COMMAND_COMMIT_GUARD.CORRELATION_COLLISION',
  WRITE_AHEAD_FAILED: 'COMMAND_COMMIT_GUARD.WRITE_AHEAD_FAILED',
  POST_MUTATION_LEDGER_FAILED: 'COMMAND_COMMIT_GUARD.POST_MUTATION_LEDGER_FAILED'
});

export class CommandCommitGuardError extends Error {
  constructor(code, message, details = {}, cause) {
    super(message, cause ? { cause } : undefined);
    this.name = 'CommandCommitGuardError';
    this.code = code;
    this.details = Object.freeze(structuredClone(details));
  }
}

function requireMethod(value, name, method) {
  if (!value || typeof value[method] !== 'function') {
    throw new TypeError(`${name} must implement ${method}()`);
  }
  return value;
}

function allowed(result) {
  if (typeof result === 'boolean') return result;
  if (result && typeof result === 'object' && typeof result.allowed === 'boolean') return result.allowed;
  throw new TypeError('authority result must be boolean or { allowed: boolean }');
}

function authorityReason(result) {
  return result && typeof result === 'object' ? result.reason ?? null : null;
}

function ledgerIdentity(action) {
  return {
    actionId: action.actionId,
    actionClass: action.actionClass,
    originType: action.originType,
    originId: action.originId,
    intentId: action.intentId,
    intentVersion: action.intentVersion,
    sliceId: action.sliceId,
    correlationId: action.correlationId,
    operation: action.operation
  };
}

export class CommandCommitGuard {
  constructor({
    brokerPort,
    ledger,
    clock,
    intentAuthority,
    integrityAuthority,
    interruptAuthority,
    correlationIdFactory
  }) {
    this.brokerPort = assertBrokerPort(brokerPort);
    this.ledger = assertLedgerPort(ledger);
    this.clock = assertClockPort(clock);
    this.intentAuthority = requireMethod(intentAuthority, 'intentAuthority', 'isCurrent');
    this.integrityAuthority = requireMethod(integrityAuthority, 'integrityAuthority', 'allows');
    this.interruptAuthority = requireMethod(interruptAuthority, 'interruptAuthority', 'allows');
    this.correlationIdFactory = correlationIdFactory;
    this.commitTail = Promise.resolve();
  }

  async _ledgerEntries() {
    const entries = await this.ledger.entries();
    if (!Array.isArray(entries)) throw new TypeError('ledger.entries() must return an array');
    return entries;
  }

  async _assertUnique(action) {
    const rows = await this._ledgerEntries();
    if (rows.some(row => row?.actionId === action.actionId)) {
      throw new CommandCommitGuardError(
        CommandCommitGuardErrorCode.DUPLICATE_ACTION,
        `action ${action.actionId} already exists in the execution ledger`,
        ledgerIdentity(action)
      );
    }
    const collision = rows.find(row => row?.correlationId === action.correlationId && row?.actionId !== action.actionId);
    if (collision) {
      throw new CommandCommitGuardError(
        CommandCommitGuardErrorCode.CORRELATION_COLLISION,
        `correlation ${action.correlationId} is already bound to another action`,
        { ...ledgerIdentity(action), existingActionId: collision.actionId ?? null }
      );
    }
  }

  async _assertAuthorities(action) {
    if (action.intentId !== null) {
      const current = await this.intentAuthority.isCurrent({
        intentId: action.intentId,
        intentVersion: action.intentVersion,
        action
      });
      if (!allowed(current)) {
        throw new CommandCommitGuardError(
          CommandCommitGuardErrorCode.STALE_INTENT,
          `intent ${action.intentId} version ${action.intentVersion} is not current`,
          { ...ledgerIdentity(action), reason: authorityReason(current) }
        );
      }
    }

    const interrupt = await this.interruptAuthority.allows(action);
    if (!allowed(interrupt)) {
      throw new CommandCommitGuardError(
        CommandCommitGuardErrorCode.INTERRUPT_CONFLICT,
        `action ${action.actionId} conflicts with the active interrupt state`,
        { ...ledgerIdentity(action), reason: authorityReason(interrupt) }
      );
    }

    const integrity = await this.integrityAuthority.allows(action);
    if (!allowed(integrity)) {
      throw new CommandCommitGuardError(
        CommandCommitGuardErrorCode.INTEGRITY_DENIED,
        `state integrity does not permit action ${action.actionId}`,
        { ...ledgerIdentity(action), reason: authorityReason(integrity) }
      );
    }
  }

  async _appendBeforeMutation(action) {
    try {
      return await this.ledger.append({
        eventType: 'MUTATION_INTENDED',
        status: 'INTENDED',
        ...ledgerIdentity(action),
        createdAt: action.createdAt,
        request: structuredClone(action.payload)
      });
    } catch (error) {
      throw new CommandCommitGuardError(
        CommandCommitGuardErrorCode.WRITE_AHEAD_FAILED,
        `write-ahead ledger append failed for action ${action.actionId}`,
        ledgerIdentity(action),
        error
      );
    }
  }

  async _appendAfterMutation(action, entry) {
    try {
      return await this.ledger.append(entry);
    } catch (error) {
      throw new CommandCommitGuardError(
        CommandCommitGuardErrorCode.POST_MUTATION_LEDGER_FAILED,
        `post-mutation ledger append failed for action ${action.actionId}; broker truth must be reconciled before another mutation`,
        ledgerIdentity(action),
        error
      );
    }
  }

  commit(input) {
    const run = this.commitTail.then(() => this._commitOnce(input));
    this.commitTail = run.catch(() => undefined);
    return run;
  }

  async _commitOnce(input) {
    const action = normalizeExecutionAction(input, {
      nowMs: this.clock.now(),
      correlationIdFactory: this.correlationIdFactory
    });

    await this._assertUnique(action);
    await this._assertAuthorities(action);
    const intended = await this._appendBeforeMutation(action);
    const request = brokerRequestForExecutionAction(action);

    try {
      const brokerResult = await this.brokerPort.call(request);
      const acknowledged = await this._appendAfterMutation(action, {
        eventType: 'BROKER_RESULT',
        status: 'ACKNOWLEDGED',
        ...ledgerIdentity(action),
        brokerObservedAt: brokerResult?.observedAt ?? null,
        brokerProvider: brokerResult?.provider ?? null,
        brokerResult: structuredClone(brokerResult)
      });
      return Object.freeze({ action, intended, acknowledged, brokerResult });
    } catch (error) {
      if (error instanceof CommandCommitGuardError) throw error;

      const providerOutcome = isProviderError(error) ? error.outcome : ProviderCommandOutcome.UNKNOWN;
      const status = providerOutcome === ProviderCommandOutcome.KNOWN_NOT_APPLIED
        ? 'KNOWN_NOT_APPLIED'
        : 'UNKNOWN';

      await this._appendAfterMutation(action, {
        eventType: 'BROKER_RESULT',
        status,
        ...ledgerIdentity(action),
        providerOutcome,
        providerError: isProviderError(error) ? error.toJSON() : {
          name: error?.name ?? 'Error',
          message: error?.message ?? String(error)
        }
      });

      throw error;
    }
  }
}

export function createCommandCommitGuard(dependencies) {
  return new CommandCommitGuard(dependencies);
}
