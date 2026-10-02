# Requirements and acceptance traceability

Created before implementation; updated against executed evidence. Source base:
`98cdabea49ca45aa237b51ebe8865351c20d3125`. The original checkout's unrelated
dashboard edit was preserved. Operational trading, authentication and ledgers
are outside the change scope. Module names below refer to `src/butterfly_lab/`.

| ID | Mandatory behavior | Implementation | Executed acceptance | Status |
|---|---|---|---|---|
| R01 | Strict versioned contracts, units, aware clocks, immutable evidence | schemas, config | test_contracts_cli; test_registry; 14 generated schemas | Passed |
| R02 | Complete registry, migrations, controlled writer, lineage/supersession | registry, dedup, evidence | test_registry; test_dedup; graph duplicate lineage | Passed |
| R03 | Atomic campaign/hypothesis budgets, bounded queue | registry, providers | concurrent overspend, CPU rounding, selection/Monte Carlo distinction, queue parking | Passed |
| R04 | Identity, PIT/availability, clocks, expiry/lots, source binding | data, registry | test_data; source mutation/directory/alias tests; actual-data gates | Passed; real inputs limited |
| R05 | B-as-observed, B-policy, B0 remain distinct | baselines, frozen controller | golden cases, source hash, symmetry, recorded non-ATM selection, future availability and missing gate/selection cases | Passed |
| R06 | Six functioning roles, real provider, replay/fixture distinction | agents, providers | role tests; HTTP contract, reservation and refusal tests | Passed offline; live service unverified |
| R07 | Twelve complete seeds, capability admission, dedup | configs/seeds.json, compiler, dedup | seed validation; canonical/feature/semantic/behavior tests; admitted and blocked demo questions | Passed |
| R08 | Actual campaign, experiment, review, confirmation graphs | graph | test_graph; clean installed CLI demos; Send aggregation and checkpoints | Passed |
| R09 | Registered outbox, external workers, attempts, leases, fencing | registry, workers | test_workers; test_registry; subprocess demos and load test | Passed |
| R10 | Recovery, early/duplicate completion, unresolved and cancelled work | registry, workers, graph | Failure matrix below | Passed |
| R11 | Full four-leg F0/F1/F2/F3 accounting; F4 rejected | accounting, evaluators | model/bar/quote, partial fill, latency, recenter, missing exit, capital tests | Passed on fixtures |
| R12 | Frozen EXP-001; training-only transformations | evaluators, scientific-contract | future perturbation, clock/lag, missing target, rerun and independent reconstruction | Passed on fixtures; real source blocked |
| R13 | Session inference, practical effects, robustness, negative audit | statistics, replication, evaluators | statistical/replication tests; preregistered null/planted benchmark; all negatives reconstructed | Passed |
| R14 | All terminal outcomes and deterministic grade ceilings | evidence, graph, schemas | grade tests, negative economics termination, inconclusive versus informative negative | Passed |
| R15 | Protected batch, release, isolation, exposure/consumption | confirmation, security | authorization/denial/consumption tests; protected raw 30-session four-leg fixture | Passed on macOS; fresh real partition absent |
| R16 | Evidence-linked memory, authoritative campaign synthesis | evidence, agents, graph | prose upgrade rejection, supersession, both campaign reports | Passed |
| R17 | Coherent CLI, configurable roots, backup/restore | cli, backup | CLI tests; installed doctor/demo; example campaign; 32-file verified restore | Passed |
| R18 | Null/effect/defect benchmarks and matched workflow harness | benchmarks, tests | 40 null + 40 planted draws; three matched fixture workflows; injected numerical/security defects | Passed; no superiority claim |
| R19 | 250 hypotheses and 2,000 actual lightweight jobs | benchmarks | real registration, queue, execution, ingestion, controller restart and duplicate checks | Passed; synthetic capacity only |
| R20 | Locked clean install, lint/types, schemas, rendered diagrams, CI | lock, examples, docs, workflow | full suite; Ruff; contract typing; five SVG render/hash checks | Local passed; remote receipt in verification |
| R21 | Scoped commit/push and normal branch policy | GitHub delivery | verified remote SHA/tree/CI/PR | See release verification |

## Failure-injection and scientific invariants

| Required case | Test evidence |
|---|---|
| Future observations cannot change earlier features/predictions | test_evaluators: future_perturbation |
| Bar labels, timezone/session boundaries | test_data: bar_labels, timezone_naive, session_closed; EXP001 lag |
| Matched opportunities, missing targets, no outcome-conditioned drops | test_statistics: opportunity_mismatch; test_evaluators: missing_target/missing_exit; confirmation missing targets |
| Bid/ask signs, lots once, unknown fees, rolls, recenter costs | test_accounting; test_data: contract_roll; test_evaluators: fourleg_recenter/unknown_fees |
| Reproducible reruns, independently detected defects | test_evaluators: exp001; test_replication: altered metrics/double lots |
| Prose cannot upgrade evidence; poor economics terminates | test_agents: model_prose; test_contracts_cli: grades; test_graph: negative_economics |
| Duplicates preserve lineage; unregistered work denied | test_dedup; test_graph: campaign_duplicate; test_registry: registered_hypothesis_and_trial |
| Budget races, backpressure, CPU/concurrency limits | test_registry; test_graph: queue_backpressure; test_independent_review: CPU/concurrency |
| Restart after outbox commit and while worker runs | test_graph: real_graph_restart_outbox/restart_while_external_worker_runs |
| Early completion, forged resumption, duplicate completion | test_graph: completion_before_graph_wait/forged_resume; test_registry: claim_fencing |
| Publication-before-death, conflicting artifacts, stale fences | test_workers: publication_before_completion_crash; test_registry: artifacts/fencing |
| Cancellation, expired lease, uncertain process identity | test_registry: cancellation/expired_lease/launch_intent; test_workers: running_child_without_supervisor; test_independent_review: unresolved_slot |
| Graph/schema/evaluator/environment mismatch | test_registry: migration; test_graph: versions; test_workers: incompatible_science_hash; confirmation frozen_runtime |
| Hash-verified backup, corruption and traversal rejection | test_backup; separately executed full-demo backup/restore |
| Confirmation denial, renamed consumed data, descendants | test_security OS probes; test_confirmation: unauthorized/consumed/program_budget |

## Frozen definitions and boundaries

See [scientific-contract.md](scientific-contract.md) for EXP-001 definitions,
thresholds and exclusions. `configs/benchmarks.json` fixes seeds and tolerances;
acceptance criteria were not weakened after results.

All admitted numerical results, including negatives, are independently reconstructed.
Schema-format repair permits one retry. Protected evaluator defects terminate;
models cannot modify the evaluator or optimize away poor economics. New scientific
primitives require reviewed, tested, versioned extensions. Unsupported primitives
return UNSUPPORTED_HYPOTHESIS; verified missing data returns DATA_LIMITED.
F4 depth replay and adaptive allocation are the proposal's optional extensions,
not hidden mandatory-path stubs. Detailed measured evidence and external limits:
[verification.md](verification.md).

## Codex/provider configuration release

The subsequent provider/runtime migration has its own [requirements-to-test map
and measured verification](codex-verification.md#requirements--acceptance-evidence).
It preserves the research requirements above and adds managed Codex protocol,
one `.env`, subscription-call ceilings, no-spend diagnostics and secret hygiene.
