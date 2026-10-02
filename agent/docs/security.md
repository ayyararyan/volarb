# Security and protected confirmation

## Provider and configuration boundary

Runtime/provider configuration and user-supplied secrets belong only in ignored
`agent/.env`; Codex owns its OAuth storage. The managed Codex adapter verifies
its restricted effective configuration before model access, explicitly disables
inherited MCP entries and tool/app/hook/shell capabilities, and submits turns
with restricted read-only scratch roots. It never grants server tool/permission
requests. Its process necessarily retains Codex-owned authentication access;
this is a different boundary from the network-denied numerical sandbox below.
Model role inputs reject raw/protected data and credential/configuration fields.
No API key, `.env` contents or account identity is logged or placed in provenance.
[Protocol and operational details](providers.md).

## Enforced boundary and threat model

The trusted CLI/service and host operator administer the research environment.
Untrusted numerical/research child processes run under macOS `sandbox-exec` or
Linux `bwrap`, with a scrubbed environment and no network. Only the Python runtime,
explicit source inputs and protected evaluator package are readable; only the
job's scratch directory is writable. Broker credentials are never passed.

`security.verify_boundary()` actually attempts forbidden confirmation reads,
evaluator writes, network access and inherited credential access. A missing or
nonfunctional OS sandbox raises `BoundaryUnavailable`; sensitive operations fail
closed. Same-UID `chmod`, private graph channels and prompts are **not** described
as process isolation. The host owner/root can deliberately read local files or
invoke arbitrary programs outside this application; that actor is outside this
threat model.

macOS runtime loading requires read access to the literal root directory `/` (its
directory entry, not the recursive subtree). Runtime symlink aliases are allowed
only where needed for the selected interpreter. Linux uses a separate mount and
network namespace with read-only binds. CPU and wall limits are enforced;
Linux also uses an address-space limit. The numerical supervisor measures RSS
because macOS address-space limits are unreliable for scientific runtimes; the
protected confirmation subprocess has its own measured-RSS watchdog too.

No arbitrary generated Python path is provided. Scientific extensions require
an independently reviewed, tested and versioned evaluator change.

## Confirmation lifecycle

1. Register an approved campaign and independently reconstructed finalist reports.
2. Register a confirmation manifest with immutable source hash, an explicit
   `unexamined_attestation`, `prior_exposed=false`, and no prior exposure records.
3. Freeze the **whole finalist batch**, exact experiment/implementation hashes,
   replication-report IDs and inference policy. One batch contains all primary
   claims; do not spend separate alpha on each selected winner.
4. Explicitly authorize the signed batch with the trusted release credential and
   expiry. Authorizations reserve the program-level alpha budget.
5. Reserve ordinary campaign compute/storage budget for the protected service.
6. Verify the OS boundary. Mark the source bytes consumed **before** numerical
   access; compute in the protected subprocess; release one signed artifact.
7. Publish deterministic findings and supersession links from the accepted bundle.

The frozen batch also binds the installed scientific evaluator and environment
fingerprints. A changed runtime cannot silently resume scientific evaluation.
Full raw-evaluation Parquet accounting, opportunity and path artifacts are
published content-addressably before scratch cleanup and linked from the signed
result bundle. A protected computation is a registered, budget-reserved service
job, not an unregistered shortcut around the numerical queue.

`ConfirmationService` provides `eligibility`, `freeze`, `authorize`, `evaluate`,
`report`, `publish_findings` and `register_descendant`. CLI commands expose the
same operator lifecycle. The release token is a scoped HMAC signature, not a
request to trust a model's “approved” prose. Signing/authorization material lives
under the private runtime authority directory, outside agent child permissions.

The service rejects inspected historical data, missing replication evidence,
changed implementations, missing/changed sources, expired/wrong authorizations,
unknown timestamps, mismatched opportunities and reused bytes under a renamed
dataset. A failed computation after access remains consumed. An existing accepted
bundle is returned idempotently, not recomputed. A result-informed descendant
requires new confirmation data; the old partition never becomes pristine again.

## Protected numerical input contracts

Two actual evaluation paths exist:

- **Frozen paired session panel:** JSON `claims` maps each registered hypothesis
  ID to `session_ids`, `baseline` and `candidate` arrays. This is a scientific input
  contract, not an array of caller-supplied p-values. All claims share the same
  unique chronological sessions. Null targets fail; no complete-case selection.
- **Raw standardized data:** the protected subprocess calls the actual frozen
  evaluator on spot bars, identified option bars, model marks or synchronized
  quotes. Manifest `metadata.confirmation_session_dates` must exactly match the
  resulting paired opportunity set. A spot experiment still needs the registered
  training history and split policy; unavailable training or final outcomes fail
  rather than inventing a forecast. Unexamined attestation refers to the declared
  protected scope and must not misdescribe already-inspected training data.

Each claim supplies `higher_is_better`. `effect_scale="relative_baseline"` is
required for EXP-001's relative MAE hurdle; net-INR claims normally use `absolute`.
The service independently calculates paired differences, circular moving-block
bootstrap uncertainty and one-sided practical-effect p-values. Holm adjustment
controls the registered finite batch under valid individual p-values; it does not
repair nonstationarity or invalid dependence assumptions. The alpha policy is
bounded at the program level to prevent repeating batches until one passes.

Synthetic confirmation fixtures exercise authorization, OS isolation, numerical
computation, release, consumption and findings, but remain **F0 synthetic**. The
`demonstration_outcome` shows what the controlled test pathway computed without
claiming independently supported market evidence.

## Verification

```sh
python -m pytest tests/test_security.py tests/test_confirmation.py -q
```

Host-specific positive sandbox tests skip only when the OS boundary cannot run;
the fail-closed negative test still runs. This is visible in the test summary, not
reported as a successful protected integration. Supported hosts additionally run
a protected thirty-session four-leg evaluation on segregated synthetic quotes.
