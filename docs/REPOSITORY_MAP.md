# Canonical repository map

Updated 2026-10-04. This map describes source ownership and implementation status, not a running deployment. Start at the [root README](../README.md); [validation commands](VALIDATION.md) cover the source tree.

## Architecture and execution

| Location | Ownership and canonical entrypoint |
|---|---|
| [`architecture/`](../architecture/README.md) | Component and composition catalogs, immutable identities, manifests and validators. [Compositional identity](architecture/compositional-identity.md) is the identity specification. |
| [`architecture/components/execution-engine/`](../architecture/components/execution-engine/manifest.json) | Canonical `component.execution_engine` and `[5,0,...]` registry. Old `internal-execution/` paths are compatibility mirrors/aliases, not another component. |
| [`architecture/strategies/volarb/`](../architecture/strategies/volarb/composition.json) | Volarb mounts and bindings. [Strategy master graph](autonomous-butterfly-workflow.md) links regime/allocation/selection/position-management designs. |
| [`execution-engine/`](../execution-engine/README.md) | Generic runtime ports and global provider errors. The full policy/convergence pipeline is designed in [execution-engine.md](workflows/execution-engine.md), not yet implemented here. |
| [`execution-testkit/`](../execution-testkit/README.md) | Virtual clock, seeded randomness, simulated broker/market, memory ledger, faults, composition harness and invariant tests. Not production code. |
| [`environments/execution/`](../environments/execution/README.md) | Test/replay/shadow/production dependency declarations. Not an environment loader or authorization to send broker commands. |

The boundary is **Strategy → optional Strategy Execution Adapter → Execution Engine → Broker Execution Port → Broker Provider**. Strategy semantics are never moved into the generic engine, and Dhan never chooses execution policy. Production must not depend on `execution-testkit`.

## Providers, services and installation

| Location | Purpose |
|---|---|
| [`services/dhan-chatgpt-mcp/`](../services/dhan-chatgpt-mcp/README.md) | Reusable Dhan Provider/Broker Execution Port implementation, read-only MCP facade and separately gated legacy butterfly executor. [Call map](providers/dhan-execution-engine-call-map.md) distinguishes generic operations from compatibility tools. |
| [`services/day-workflow/`](../services/day-workflow/README.md) | Existing strategy-specific SHADOW orchestration, read-only acquisition and explicit accounting tooling. Not the generic Execution Engine and not an end-to-end live bot. |
| [`services/essvi-dashboard/`](../services/essvi-dashboard/README.md) | Optional eSSVI/IV/HAR dashboard, external data/package requirements and local launch procedure. |
| [`agent-kit/`](AGENT_KIT.md), [`tools/volarb.py`](../tools/volarb.py) | Portable source/profile/workspace packaging and offline diagnostics. Not the research laboratory itself; credentials and private runtime remain separate. |

## Research and strategy operation

| Location | Purpose |
|---|---|
| [`agent/`](../agent/README.md) | Offline Butterfly Research Laboratory, datasets, campaigns, evaluators, scientific contracts and tests. Frozen controller copies/evidence are versioned scientific baselines, not duplicate live controllers. |
| [`skill/`](../skill/README.md) | Current-observation research modules: Butterfly Market Outlook v2.6, HF realized-volatility forecast and news filter. |
| [`docs/DAILY_OPERATING_ALGORITHM.md`](DAILY_OPERATING_ALGORITHM.md) | Current manual daily sequence; [standing workflow](WORKFLOW.md) and [covenant](PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md) supply operating constraints. |
| [`prompts/`](../prompts/README.md) | Bounded user-invoked workflow prompts, not schedules or order authority. |
| [`market-outlook/`](../market-outlook/README.md) | Public navigation notice only. Dated market/position reviews belong in a configured private journal outside source. |
| [`trade-log/`](../trade-log/README.md) | Public navigation notice and private schema reference. Personal executions, account snapshots and calibration episodes are intentionally excluded. |

## Maintenance and history

- [Validation guide](VALIDATION.md), `.github/workflows/` and `tests/` explain practical offline checks.
- [Branch naming and lifecycle](#branch-naming-and-lifecycle) is the single branch convention; the [release guide](RELEASING.md) covers immutable version tags.
- [Current notes](../notes.md) route decisions to canonical documents; [tasks](../tasks.md) distinguish outstanding implementation from completed design.
- [Development history](DEVELOPMENT_HISTORY.md) records changes; [file classification](audits/2026-10-03-file-classification.tsv) accounts for every cleanup-baseline tracked file; its historical financial-record dispositions were superseded by the public-release privacy boundary.
- [Archive](../archive/README.md) separates superseded architecture, research reports and retired deployment policy. Archived content is historical evidence, never a runtime dependency or current instruction.

### Branch naming and lifecycle

**`main` is the default and only permanent integration branch.** Work uses short-lived branches:

```text
<type>/<short-description>
```

Allowed types: `feature`, `fix`, `refactor`, `docs`, `test`, `chore`, `release`,
`hotfix`, `research`, `experiment`, `archive`.

- Use lowercase words separated by hyphens. Choose a short description of the
  work, not the author. Avoid spaces, underscores, camelCase, personal prefixes,
  unexplained abbreviations and dates unless the work genuinely needs a date.
  Generic descriptions such as `test`, `new`, `temp`, `final`, `working`, `misc`,
  `changes` or `update` are not sufficient on their own.
- Examples: `feature/execution-engine-runtime`, `fix/dhan-stream-reconnect`,
  `docs/repository-map`, `test/execution-recovery-races`, `chore/branch-hygiene`.
- `research/execution-slicing` denotes research intended to inform canonical
  architecture; `experiment/alternative-fill-model` denotes exploratory work
  with uncertain disposition. Neither becomes production behavior by naming it.
- Releases normally use immutable tags on validated `main`, not permanent release
  branches. If temporary release preparation needs a branch, use
  `release/vMAJOR.MINOR.PATCH` (for example `release/v0.4.0`); semantic-version
  punctuation is the explicit exception to hyphen-only descriptions.
- Use `archive/<topic>` only when a meaningful unmerged line must remain available.
  Do not create archive branches or tags merely to retain integrated work; Git
  history, merged PRs and deliberate private recovery backups preserve provenance.
- Open a PR into `main`; satisfy the required, uniquely named CI checks and
  resolved review threads before merging. The branch describes the unit of work;
  commit messages describe its atomic changes. No workflow should depend on a
  short-lived task branch.
- Delete an integrated task branch once no open PR, automation or documentation
  depends on it. Check both remote and local tips: ancestry proves a normal merge;
  a squash merge requires verified content equivalence and preservation of any
  useful original commit sequence. Preserve uncertain or genuinely unique work.
- Before deleting a checked-out local branch, coordinate its worktree. A clean
  historical checkout may be detached at the **same SHA**; preserve its files and
  environments. Never reset, switch or discard a dirty checkout merely for hygiene.

Keep `main` protected from deletion and force pushes, with PRs and current required
checks. GitHub-hosted protection must be verified separately from the proposed
ruleset file; plan/visibility limitations do not justify claiming enforcement.
Prefer automatic deletion of merged PR branches, while retaining the local
ancestry/worktree checks above. Changes to repository visibility, sensitive Git
history or production runtime are separate operations, not branch cleanup.
