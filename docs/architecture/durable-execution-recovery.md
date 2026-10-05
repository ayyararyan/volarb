# Durable admission and account-scoped reconciliation

Implemented in the canonical Python engine: `SQLiteExecutionLedger`, `LedgerIntentAuthority`, the strengthened `CommandCommitGuard`, `ExecutionScope`/`AccountBrokerPort`, and `ScopedReconciler`. These components retain the algorithmic classifications of `[5,0,8,9,1]`, `[5,0,8,1,2]` and `[5,0,8,1,1]`.

## Scope and deployment contract

The first durable backend supports **one POSIX host, a local filesystem, and one shared database/lock directory for all dispatchers controlling a broker account**. It uses SQLite rollback journaling (`journal_mode=DELETE`) and `synchronous=EXTRA`, atomic SQL transactions, and nonblocking OS account locks. SQLite is provided by Python's standard library; no database server or new package is required. This conservative journaling choice avoids depending on a particular WAL fix level in runner/system SQLite builds. SQLite's [synchronous documentation](https://www.sqlite.org/pragma.html#pragma_synchronous) describes the commit and directory-sync behavior. Durability still depends on the filesystem and storage honoring synchronization.

Account scope is `(provider, account_id)` from a trusted, verified provider binding. Strategy, composition, mount, instrument, action and intent IDs do **not** subdivide that account's admission fence. Two strategies trading the same account cannot avoid an unresolved order by assigning different scope or action IDs. Other broker accounts may progress independently. Action and correlation identities are unique across the database and remain reserved after resolution.

This first version deliberately serializes account mutations. It does not implement instrument-level parallel admission, distributed coordination, a network-filesystem database, an environment loader or a new live provider connection. The production driver must verify the configured account against provider credentials/readiness and inject a matching `AccountBrokerPort`. Swapping that connection's account at runtime violates the binding contract. Keep the database and its lock directory in private runtime storage. Do not delete, replace, hard-link, independently copy or relocate an active database/lock directory; stop all writers before migration and use a consistent database backup. An existing corrupt/unsupported database must fail rather than be reset to empty state.

## Admission protocol

1. Acquire the account's nonblocking OS lock. If another dispatcher or reconciler holds it, return `SCOPE_BUSY` without sending anything.
2. Check current intent, interrupt and integrity authorities. In one database transaction, reserve the action/correlation IDs, occupy the account's unresolved-action slot and record `MUTATION_INTENDED`.
3. Recheck authorities and verify that callbacks have not changed the admitted request. A denied or invalid action is aborted before dispatch. Authority callbacks must be read-only.
4. Commit a separate `DISPATCH_STARTED` marker before invoking the broker. Only a confirmed marker permits the call.
5. Invoke the bound broker once under an explicit command timeout. The broker port must be nonblocking/async and must not suppress cancellation.
6. Persist acknowledgement, known non-application or uncertainty. Timeout, task cancellation, a malformed response or an unclassified error means uncertainty. A claimed `KNOWN_NOT_APPLIED` is accepted only from a matching provider COMMAND error for that operation.
7. Release the OS lock. Releasing a lock never clears the durable account block. The broker call and its outcome recording occur while the lock is held, so reconciliation cannot overtake a suspended sender.

No SQLite transaction spans broker I/O. Short database writes still serialize, and a busy/write error rejects the affected operation. There is no automatic mutation retry. The original action ID remains an identity for one attempt; a workflow replay must preserve it.

The new `assert_admission_ledger_port` requires atomic admission, account fencing and transition methods. The older `append`/`entries` trace contract remains available to legacy infrastructure, but it is insufficient for the production guard. There is no silent fallback to an append-only memory ledger.

## Durable states and restart behavior

| Persisted state | Account blocked? | Meaning and recovery |
|---|---|---|
| `INTENDED` | Yes | Identity and request committed; dispatch marker absent. Once the reconciler owns the account lock, it can prove this implementation has not sent the command and mark it `NOT_SENT`. |
| `DISPATCHING` | Yes | Dispatch may have occurred, including if the process crashed before recording a result. Broker evidence is required. |
| `ACKNOWLEDGED` | Yes | A normalized acknowledgement was recorded. It does not establish position completion or authorize a replacement. Reconcile first. |
| `UNKNOWN` / `AMBIGUOUS` | Yes | Outcome or subsequent observations are insufficient. New IDs and process restart cannot evade the block. |
| `KNOWN_NOT_APPLIED` | No | Matching provider command evidence confirms no application. The original action/correlation identities remain reserved. |
| `NOT_SENT` | No | The command never reached the durable dispatch point. |
| `RECONCILED` | No | Sufficient broker evidence and the reconciliation result were committed atomically with release of the account slot. |

A write failure before dispatch prevents the broker call. A write failure after a broker call leaves a durable unresolved record. If a dispatch-marker commit succeeds but its local receipt is lost, the command is conservatively treated as potentially sent. No absence-based shortcut clears it.

`LedgerIntentAuthority` reads durable intent versions. `publish_intent` takes the same account lock as dispatch and accepts only increasing versions. Therefore a version publication cannot interleave with an admitted send. A caller receiving `SCOPE_BUSY` must reschedule the authority update; it cannot bypass the fence. The active guard rechecks injected authorities after admission. Future State Integrity and Interrupt Control implementations must coordinate their relevant updates through this same fence. Their full persistent policies/latches are still outstanding. An already dispatched command cannot be retroactively unsent; it must be reconciled before subsequent action.

## Broker evidence and conservative limits

`ScopedReconciler.reconcile()` holds the account lock while it reads and resolves the pending action. Its broker calls are **QUERY only**:

- For placement, `GET_ORDER_BY_CORRELATION` must identify the exact admitted correlation, consistent provider correlation, instrument, side, product and quantity. A previously acknowledged order ID must agree.
- `GET_ORDER_TRADES` supplies fills. Identical trade duplicates are counted once; conflicting identities, mismatched instruments/sides/products, missing trade history or a total differing from the order's filled quantity preserve ambiguity.
- `GET_POSITIONS` supplies a normalized position observation. Its net quantities are not assumed to equal the effects of one order, because other controlled/manual activity may exist.
- A final `GET_ORDER` must agree on the relevant order state and quantities. Changed state during the observation sequence requires a fresh reconciliation attempt.
- Every envelope must match the provider, operation and contract version, have an aware timestamp at or after dispatch, and pass the configured age limit. Future observations, invalid values, expired evidence and query failures cannot release admission.

`CLEAN` means **no unresolved command in this account**. It does not mean all positions are flat, the strategy target is achieved, or the observed position list is an atomic broker snapshot. The result preserves observations, confirmed fills, confirmed unfilled quantity, order status and whether the order is still fillable. Downstream registry/State Integrity logic must use these facts before deciding further work. In particular, an identified live placement can be reconciled while its existing order remains fillable; its remainder is not permission for a second placement.

Cancellation is resolved only after the target is terminal, including when a fill wins the cancel race. For a live modification, matching price/quantity is insufficient to prove that an old delayed modify will not apply later. **The current provider contract lacks a command-specific final modification receipt, so both acknowledged and uncertain modifications remain blocked until the target order is terminal.** This is a throughput/availability limitation for future Passive Chase; extending the provider evidence contract is a required follow-up before enabling ongoing modification/reprice loops.

An empty lookup or order-not-found error never proves non-application after dispatch. Brokers with delayed visibility or incomplete historical trade queries may remain unresolved; a future provider-specific final receipt can support a stronger resolution rule. This implementation supplies no operator “force clean” method and no mutation retries. Account blocking applies to emergency-originated commands too; the upcoming Interrupt Control work must explicitly address emergency handling while a command is uncertain rather than bypass this invariant.

## Wiring

The following constructor example is for a future verified environment loader. `provider`, `clock`, configured timeouts, private storage location and the authority objects are injected dependencies; this example does not obtain credentials or issue an order.

```python
from volarb_execution import (
    AccountBrokerPort, CommandCommitGuard, ExecutionScope,
    LedgerIntentAuthority, SQLiteExecutionLedger, ScopedReconciler,
)

scope = ExecutionScope(provider_name, verified_account_id)
broker = AccountBrokerPort(scope, provider)
ledger = SQLiteExecutionLedger(private_state_dir / "execution.sqlite3")
intent_authority = LedgerIntentAuthority(ledger, scope)
guard = CommandCommitGuard(
    broker_port=broker, ledger=ledger, clock=clock,
    intent_authority=intent_authority,
    integrity_authority=integrity_authority,
    interrupt_authority=interrupt_authority,
    command_timeout_s=command_timeout_s,
)
reconciler = ScopedReconciler(
    broker_port=broker, ledger=ledger, clock=clock,
    max_observation_age_ms=max_observation_age_ms,
    query_timeout_s=query_timeout_s,
)
```

The driver publishes approved intent versions before admission, invokes reconciliation on startup and after acknowledgement/ambiguity, and sends only newly planned work after the relevant authorities permit it. Model code does not receive these mutation or ledger capabilities.

## Verification

Run `python3.12 -B -m unittest discover -s execution-engine/tests -p 'test_*.py' -v`. The tests use real temporary database files and deterministic synthetic broker observations, with actual separate processes for concurrent admission and a crash after a simulated broker effect. They exercise transaction rollback, restart, duplicate identities, account isolation, task cancellation, timeout, stale/malformed evidence, lost acknowledgement, cancel/fill races, uncertain modifications and failed outcome/reconciliation persistence. No live broker or account is accessed.

Architecture identity and legacy testbed validation remain the normal companion checks. Live adapter integration, latency calibration, full State Integrity/Interrupt Control and the complete execution pipeline remain separate work.
