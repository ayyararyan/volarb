# Numerical jobs, recovery, and backups

The graph, registry, supervisor, numerical process, and artifacts have separate
lifetimes. A graph restart does not restart an already registered computation.
Only allowlisted, installed evaluators execute; there is no generated-Python path.

## Guarantees and operational states

Registration atomically freezes experiment/data/environment/evaluator identity,
reserves approved resources, and writes the durable submission outbox. Repeating
that registration returns the same run ID. A new seed, implementation, data,
environment or explicit rerun identity is distinct but remains in its trial lineage.

SQLite writes use an interprocess file lock plus `BEGIN IMMEDIATE`, unique SQL
constraints, full synchronous commits and WAL. Immutable scientific records reject
conflicting replacements. Database migrations are separate from scientific schema
and graph versions. Runtime paths in repositories or common cloud-sync roots are
rejected. Active checkpoints are a separate SQLite store.

Each claim increments a fencing token and creates an attempt. A launch-intent row
is persisted **before** creating the child process. Completion is accepted only
for that run's current attempt/fence, after recursively verifying artifact hashes.
Duplicate identical completion is harmless; conflicting output is rejected.
Ingestion has one SQL record per run. Result-publication markers permit recovery
after publication but before completion registration.

States are `QUEUED → RUNNING → COMPLETED → INGESTED`, with explicit `FAILED`,
`CANCEL_REQUESTED`, `CANCELLED`, and `LOST_UNRESOLVED` branches. These are operational
states, not evidence grades or profitable/unprofitable outcomes.

An expired lease **never** proves a process is dead. Reconciliation uses host, PID,
and process-birth identity for the supervisor and evaluator. A live orphan child,
unreadable identity, remote owner, or launch intent with unknown child PID becomes
`LOST_UNRESOLVED`; it occupies capacity and cannot be blindly reclaimed. Inspect
and resolve the process evidence before replacement. If both processes are
verified dead, a published hash-verified result is recovered; otherwise a bounded
operational retry is possible with a new attempt and additional budget reservation.

There is no claim of universal exactly-once computation. Guarantees are idempotent
registration, controlled submission, explicit uncertainty, fenced acceptance and
single accepted ingestion.

## Running and restarting

Use the installed `butterfly-lab` CLI's `worker start`, `worker status`,
`reconcile`, `resume`, and `campaign cancel` commands. The low-level service is also
directly executable:

```sh
python -m butterfly_lab.workers --root "$LAB_RUNTIME" --concurrency 2 --idle-timeout -1
```

`--idle-timeout -1` stays alive until stopped; positive values stop after an idle
period. `--max-jobs N` bounds attempts processed. Campaign concurrency remains an
independent ceiling, and unresolved attempts consume slots. A detached supervisor
continues after its caller exits. Start a graph, run a worker, then resume from the
registry's terminal event; event IDs from other runs/fences are rejected. Wait
registration precedes a terminal-event read, closing the completion-before-wait race.

After interruption:

1. Run `reconcile` and inspect unresolved attempts before starting replacements.
2. Preserve `jobs/<run>/<attempt>/published.json`, local error evidence and artifacts.
3. Run `resume` to continue the graph with the verified terminal event.
4. Do not edit a registered specification or force a success row into SQLite.

Cancellation immediately stops queued runs; running children acknowledge it and
are terminated as a process group. A crash before acknowledgment stays explicit.
Already completed results remain evidence. Poor economic results never retry as
implementation failures.

## Resource and security boundaries

Numerical children receive a scrubbed environment, only registered source paths,
read-only installed scientific code, and their own writable output directory.
The OS sandbox denies general home access and networking; absent sandbox support
fails closed. Ordinary workers reject confirmation partitions. The separate
confirmation service uses registered, shared-budget service reservations that are
not claimable by ordinary workers.

Execution admission requires byte-bound external data. A single-file manifest
needs its SHA256; a directory needs `metadata.file_sha256` mapping every selected
safe relative filename to its SHA256, with `source_sha256` equal to the canonical
JSON digest of that map. The selected glob must match the map exactly. Unbound
inputs may be inspected, but cannot reserve compute or create an outbox entry.
Admission and numerical children verify bytes, including after evaluation;
changed inputs are a data limitation, not a negative economic result. Inline
synthetic/model rows and controlled synthetic generator settings are already
bound by the immutable dataset/run specification. Ordinary workers also reject
path/hash aliases of registered protected sources, regardless of a new label.
Read-only sandbox access assumes the trusted data custodian does not mutate the
source concurrently; it is not protection against an adversarial host operator.

CPU and individual output-file sizes have OS resource limits. Linux additionally
has an address-space bound. macOS uses RSS watchdogs because `RLIMIT_AS` is not a
reliable scientific-Python memory boundary there; sampling can overshoot briefly.
Parent and child wall-time limits survive graph or supervisor loss. Aggregate
storage and RSS are checked during execution and output publication. Reservations
are conservative upper bounds and are not silently recycled after crashes; actual
CPU/RSS/wall observations are recorded separately. Attempts reserve additional
compute rather than spending the same allowance repeatedly.

Hash-bound `RunManifest` artifacts record the working source tree, commit or
explicit unknown reason, environment, seed, configuration, worker identity,
fence, timestamps, result artifacts and quantities with units. A Git commit alone
does not identify uncommitted source; the working-tree hash does.

## Backup and restore

`backup` uses SQLite's online backup API, not raw copies of WAL-backed databases,
and hashes copied immutable artifacts and recovery markers. It excludes raw
datasets, credentials and transient job output. Checkpoint and registry snapshots
are individually consistent; quiesce graph activity when an exact coordinated
workflow snapshot is required. Keep the returned manifest hash independently.

Restore only into a **new** non-repository, non-cloud runtime path. It verifies all
file hashes, rejects traversal and conflicting destinations, checks SQLite
integrity, rebases recovery-marker paths, and marks formerly active attempts
unresolved. It does not launch jobs. Provide source datasets separately and run
reconciliation before dispatch. Use the trusted manifest hash to verify the
manifest itself; internal hashes alone do not authenticate an adversarial backup.

Fault tests cover budget races, immutable conflicts, stale fences, duplicate
completion, completion before wait, live workers with expired leases, missing
launch receipts, live orphan children, publication-before-completion recovery,
cancellation, incompatible code, artifact corruption, and backup/restore integrity.
