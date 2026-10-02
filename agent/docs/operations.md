# Operating the laboratory

`butterfly-lab --help` is the command authority. Global `--root DIRECTORY` precedes
the subcommand. The runtime must be private, outside Git and cloud synchronization.

## Data and campaigns

```sh
butterfly-lab data inspect dataset.json
butterfly-lab data validate dataset.json
butterfly-lab data register dataset.json
butterfly-lab campaign validate campaign.json
butterfly-lab campaign run campaign.json --dataset dataset.json --wait
butterfly-lab campaign status CAMPAIGN_ID
butterfly-lab campaign report CAMPAIGN_ID
```

Without `--wait`, admitted experiments enqueue and park. A short bounded batch is
prepared concurrently; numerical dispatch is controlled separately. A campaign may
succeed with rejected, inconclusive and data-limited findings. An unapproved campaign
fails before generation. The provider defaults to a **synthetic fixture**, explicitly
labelled; configuring `provider: openai` requires a real adapter and finite spending
configuration, never a silent fixture fallback.

A full pending queue parks the experiment at a queue-capacity interrupt; `resume`
rechecks durable queue state. It does not consume an extra run reservation or turn
temporary backpressure into budget exhaustion. Per-hypothesis search budgets count
selection trials, while Monte Carlo draws and operational reruns retain separate
lineage and still consume campaign compute budgets. `--wait` uses a bounded watcher;
on timeout it reports the still-running supervisor PID rather than assuming failure.

`experiment validate FILE`, `experiment run FILE`, `experiment status ID` and
`experiment report ID` operate on already registered campaign/hypothesis/data scope.
A new experiment freezes current evaluator/environment hashes. Resume refuses changed
scientific logic. Repair, rerun and replication have distinct lineage; changed
scientific specifications require new IDs rather than overwriting earlier records.

## Reproducible file-configured campaign

From `agent/`, after installation:

```sh
python examples/make_campaign.py "$HOME/.local/share/lab-example-inputs" --kind fourleg
butterfly-lab --root "$HOME/.local/share/lab-example-runtime" campaign run \
  "$HOME/.local/share/lab-example-inputs/campaign.json" \
  --dataset "$HOME/.local/share/lab-example-inputs/dataset.json" \
  --hypotheses "$HOME/.local/share/lab-example-inputs/hypotheses.json" --wait
butterfly-lab --root "$HOME/.local/share/lab-example-runtime" campaign report example-fourleg
```

This exact example was exercised: H011 completed at F0 exploratory support;
H001 was DATA_LIMITED on the option-only fixture. Use `--kind spot` for the
EXP-001 input example. For real data, run
`python examples/register_real_data.py --help`, supply verified timestamp and
source semantics, then validate the generated manifest before registration.
The adapter never certifies contract identity from a lane filename.

## Numerical service and recovery

```sh
butterfly-lab worker start --concurrency 2 --detach
butterfly-lab worker status
butterfly-lab reconcile
butterfly-lab resume
butterfly-lab campaign cancel CAMPAIGN_ID
```

For bounded foreground operation use `worker start --max-jobs 10 --idle-timeout 2`.
The detached supervisor survives the graph/CLI. Cancellation marks queued jobs and
requests running-child termination; uncertain process identity remains
`LOST_UNRESOLVED`. Never delete a run or force a new attempt merely because its
lease expired. [Detailed job protocol](job-recovery.md).

`resume` reads authoritative terminal events. No numerical result is accepted from
an arbitrary resume payload. Duplicate completion or ingestion preserves one result;
conflicting hashes are errors. Registered economic failure never initiates repair.

## Protected confirmation

Register a **manifest only** with `partition: confirmation`; ordinary inspection and
ordinary research graphs cannot read its bytes. Supply a documented prior-exposure
attestation and immutable source hash. Old inspected history is ineligible.

After replicated exploratory finalists finish, the campaign may freeze an eligible
batch and park at a release interrupt. With no eligible partition it terminates
exploratorily instead of waiting forever. Approval is an operator action in the
product, not a requirement to approve every ordinary backtest.

```sh
butterfly-lab confirmation freeze BATCH_ID batch.json
butterfly-lab confirmation authorize BATCH_ID --principal OWNER
butterfly-lab confirmation evaluate BATCH_ID --token-file PRIVATE_RELEASE_FILE
butterfly-lab confirmation report BATCH_ID
butterfly-lab resume CAMPAIGN_ID
```

`authorize` writes the private release file and reports its location without printing
the token. A frozen batch binds experiment/evaluator, independent validation,
source bytes, inference family and program error budget. The service computes the
whole batch, applies Holm, signs one bundle and consumes the partition **before**
feedback. A failure after access leaves the data consumed. Published findings
supersede exploratory records; they do not overwrite them. Synthetic confirmation
remains F0 demonstration evidence. Result-informed descendants require fresh data.

## Backup and restore

```sh
butterfly-lab backup /private/backup-location
butterfly-lab --root /private/new-runtime restore /private/backup-location
```

Quiesce workers/checkpoint writers before backup; unsafe active jobs are rejected.
Backup includes consistent SQLite copies and artifact hashes, not external raw data
or provider credentials. Restore requires an absent destination and verifies the
manifest and content; preserve the separately reported manifest SHA out-of-band.
Reconcile after restore before dispatch. Keep original source datasets by their hashes.

## Logs and scope

Structured registry events retain all transitions, exposure, claims, budgets and
failures; detached-service stderr is private runtime evidence. Reports show fidelity,
provenance, precision, replication and limitations. Never interpret F0/F1 or a spot
forecast as execution-quality butterfly evidence. No command can place a broker order.
