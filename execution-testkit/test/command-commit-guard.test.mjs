import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CommandCommitGuard,
  CommandCommitGuardErrorCode
} from '../../execution-engine/recovery/command-commit-guard.mjs';
import { ComponentHarness, createExecutionTestbed } from '../src/harness.mjs';
import { checkInvariants, noBlindRetryAfterAmbiguity } from '../src/invariants.mjs';

const instrument = {
  provider: 'simulated',
  providerInstrumentId: 'NIFTY-TEST',
  exchangeSegment: 'SIM'
};

const allowIntent = { isCurrent: async () => true };
const allowIntegrity = { allows: async () => true };
const allowInterrupt = { allows: async () => true };

function factory(deps) {
  return new CommandCommitGuard({
    brokerPort: deps.broker,
    ledger: deps.ledger,
    clock: deps.clock,
    intentAuthority: deps.intentAuthority ?? allowIntent,
    integrityAuthority: deps.integrityAuthority ?? allowIntegrity,
    interruptAuthority: deps.interruptAuthority ?? allowInterrupt
  });
}

function placeAction(overrides = {}) {
  return {
    actionId: 'action-1',
    actionClass: 'RISK_ADDING_PLACE',
    originType: 'ALGORITHM',
    originId: 'passive-chase',
    intentId: 'intent-1',
    intentVersion: 1,
    sliceId: 'slice-1',
    operation: 'PLACE_ORDER',
    payload: {
      order: {
        providerInstrumentRef: instrument,
        side: 'BUY',
        quantity: 10,
        orderType: 'LIMIT',
        productType: 'INTRADAY',
        validity: 'DAY',
        price: 100
      }
    },
    ...overrides
  };
}

test('command commit guard writes intent before releasing a broker mutation', async () => {
  const harness = new ComponentHarness({ componentFactory: factory });
  const out = await harness.invoke('commit', placeAction());

  assert.equal(out.brokerResult.operation, 'PLACE_ORDER');
  assert.equal(out.action.correlationId, 'exec:action-1');

  const rows = harness.testbed.ledger.entries();
  assert.equal(rows[0].eventType, 'MUTATION_INTENDED');
  assert.equal(rows[1].eventType, 'BROKER_RESULT');
  assert.equal(rows[1].status, 'ACKNOWLEDGED');

  const events = harness.testbed.trace.all();
  const ledgerEvent = events.find(x => x.type === 'ledger.append' && x.payload.actionId === 'action-1');
  const brokerEvent = events.find(x => x.type === 'broker.command.applied' && x.payload.actionId === 'action-1');
  assert.ok(ledgerEvent.seq < brokerEvent.seq);
  assert.doesNotThrow(() => checkInvariants(events));
});

test('ledger write failure prevents the broker mutation entirely', async () => {
  const testbed = createExecutionTestbed();
  const failingLedger = {
    entries: () => [],
    append: () => { throw new Error('disk unavailable'); }
  };
  const harness = new ComponentHarness({
    testbed,
    overrides: { ledger: failingLedger },
    componentFactory: factory
  });

  await assert.rejects(
    harness.invoke('commit', placeAction()),
    error => error.code === CommandCommitGuardErrorCode.WRITE_AHEAD_FAILED
  );
  assert.equal(testbed.trace.count('broker.call'), 0);
  assert.equal(testbed.trace.count('broker.command.applied'), 0);
});

test('stale intent is rejected before ledger or broker mutation', async () => {
  const harness = new ComponentHarness({
    componentFactory: factory,
    overrides: {
      intentAuthority: { isCurrent: async () => ({ allowed: false, reason: 'superseded by v2' }) }
    }
  });

  await assert.rejects(
    harness.invoke('commit', placeAction()),
    error => error.code === CommandCommitGuardErrorCode.STALE_INTENT
  );
  assert.equal(harness.testbed.ledger.entries().length, 0);
  assert.equal(harness.testbed.trace.count('broker.call'), 0);
});

test('state-integrity denial is rejected before ledger or broker mutation', async () => {
  const harness = new ComponentHarness({
    componentFactory: factory,
    overrides: {
      integrityAuthority: { allows: async () => ({ allowed: false, reason: 'market state stale' }) }
    }
  });

  await assert.rejects(
    harness.invoke('commit', placeAction()),
    error => error.code === CommandCommitGuardErrorCode.INTEGRITY_DENIED
  );
  assert.equal(harness.testbed.ledger.entries().length, 0);
  assert.equal(harness.testbed.trace.count('broker.call'), 0);
});

test('interrupt conflict is rejected before ledger or broker mutation', async () => {
  const harness = new ComponentHarness({
    componentFactory: factory,
    overrides: {
      interruptAuthority: { allows: async () => ({ allowed: false, reason: 'flatten latch active' }) }
    }
  });

  await assert.rejects(
    harness.invoke('commit', placeAction()),
    error => error.code === CommandCommitGuardErrorCode.INTERRUPT_CONFLICT
  );
  assert.equal(harness.testbed.ledger.entries().length, 0);
  assert.equal(harness.testbed.trace.count('broker.call'), 0);
});

test('ambiguous acknowledgement is durably recorded and the same action cannot be retried blindly', async () => {
  const testbed = createExecutionTestbed({
    brokerScripts: { byCorrelation: { 'exec:action-ambiguous': { ackLost: true } } }
  });
  const harness = new ComponentHarness({ testbed, componentFactory: factory });
  const action = placeAction({ actionId: 'action-ambiguous' });

  await assert.rejects(
    harness.invoke('commit', action),
    error => error?.outcome === 'UNKNOWN'
  );

  const result = testbed.ledger.entries().find(x =>
    x.actionId === 'action-ambiguous' && x.eventType === 'BROKER_RESULT'
  );
  assert.equal(result.status, 'UNKNOWN');
  assert.equal(testbed.trace.count('broker.command.applied'), 1);

  await assert.rejects(
    harness.invoke('commit', action),
    error => error.code === CommandCommitGuardErrorCode.DUPLICATE_ACTION
  );

  assert.equal(testbed.trace.count('broker.command.applied'), 1);
  assert.doesNotThrow(() => noBlindRetryAfterAmbiguity(testbed.trace.all()));
});

test('correlation identity cannot be reused by a different action', async () => {
  const harness = new ComponentHarness({ componentFactory: factory });
  await harness.invoke('commit', placeAction({ correlationId: 'corr-shared' }));

  await assert.rejects(
    harness.invoke('commit', placeAction({
      actionId: 'action-2',
      correlationId: 'corr-shared'
    })),
    error => error.code === CommandCommitGuardErrorCode.CORRELATION_COLLISION
  );
  assert.equal(harness.testbed.trace.count('broker.command.applied'), 1);
});

test('interrupt-originated actions may omit runtime intent identity but still use the guard', async () => {
  const harness = new ComponentHarness({ componentFactory: factory });
  const action = placeAction({
    actionId: 'interrupt-cancel',
    actionClass: 'EMERGENCY_CANCEL',
    originType: 'INTERRUPT',
    originId: 'interrupt-1',
    intentId: undefined,
    intentVersion: undefined,
    sliceId: undefined,
    operation: 'CANCEL_ORDER',
    payload: { orderId: 'missing-order' }
  });

  await assert.rejects(harness.invoke('commit', action), error => error?.outcome === 'KNOWN_NOT_APPLIED');
  const rows = harness.testbed.ledger.entries().filter(x => x.actionId === 'interrupt-cancel');
  assert.equal(rows[0].eventType, 'MUTATION_INTENDED');
  assert.equal(rows[1].status, 'KNOWN_NOT_APPLIED');
});


test('concurrent duplicate admission cannot release the same action twice', async () => {
  const harness = new ComponentHarness({ componentFactory: factory });
  const action = placeAction({ actionId: 'action-concurrent' });

  const settled = await Promise.allSettled([
    harness.invoke('commit', action),
    harness.invoke('commit', action)
  ]);

  assert.equal(settled.filter(x => x.status === 'fulfilled').length, 1);
  const rejected = settled.find(x => x.status === 'rejected');
  assert.equal(rejected.reason.code, CommandCommitGuardErrorCode.DUPLICATE_ACTION);
  assert.equal(harness.testbed.trace.count('broker.command.applied'), 1);
  assert.doesNotThrow(() => checkInvariants(harness.testbed.trace.all()));
});
