# Repository cleanup audit — 2026-10-03

> **Publication boundary update — 2026-10-04:** This is a dated report of the
> private-repository cleanup. Its financial/journal preservation claims and the
> accompanying classification TSV describe that earlier state. Public-release
> preparation subsequently removed personal financial payloads from public source
> and retained originals in a verified private backup. The classification TSV
> replaces both path cells for 21 personal-record rows with neutral
> `private-record-NNN` identifiers; filenames can themselves reveal trading dates,
> instruments and cycle identities. Categories, row order, counts and historical
> rationales are unchanged. The original TSV and exact identifier-to-path mapping
> are retained privately, not in Git. These rows remain historical personal records,
> not synthetic fixtures, available datasets or restore instructions.

## Scope and baseline

Audited private `ayyararyan/volarb` from `origin/main` **`ec534e8`**: **402 tracked files**, including hidden CI/configuration, source, tests, skills, research assets and dated records. Read the full tree and recent architecture history before moving files. Used parallel architecture/execution, provider/services/installation, and research/skills reviewers, plus a repository navigation/operations/CI pass.

Work was isolated from the older Drive checkout and its existing dashboard edit. No service deployment, broker request, credential change, scheduler action, live ledger mutation or trading operation formed part of this cleanup.

## Classification

[Baseline file classification](2026-10-03-file-classification.tsv) accounts for every original tracked path, category, retained/archive destination and reason.

- **A:** canonical active source, documentation, regression or deliberate generated resource.
- **B:** active but required corrections.
- **C:** compatibility/legacy active — retained in place.
- **D:** historical/superseded — archived unless explicit preservation requires established journal paths.
- **E/F/G:** duplicate/disposable/uncertain were considered. No substantive file was discarded merely because it looked old. Frozen research/controller mirrors and generated schemas are intentional, validated assets.

Baseline totals: **A: 273**, **B: 91**, **C: 12**, **D: 26**.

The classification is a dated audit receipt, not a live deployment manifest. New navigation/checker/test files are current maintenance source. The [repository map](../REPOSITORY_MAP.md) is the ongoing navigation authority.

## Problems found and resolutions

1. **Identity and ownership drift:** active strategy/execution diagrams still used the old name, an assembled registry claimed old ownership, component/composition versions differed, and one interrupt diagram bypassed the Command Commit Guard. Corrected active terminology and bindings without renumbering any VID or changing retirement status; validator now checks the stronger invariants.
2. **Implementation-status overclaims:** testkit and design prose could be read as a completed production convergence engine. Clearly separated implemented ports, provider mechanics and deterministic harnesses from the still-unimplemented generic pipeline/environment loader/production orchestration.
3. **Portable/provider import breakage:** the new Dhan runtime imports shared `execution-engine/` contracts omitted by older package/container layouts. Corrected source package roots and repository-root Docker context/import closure; production image does not contain testkit code.
4. **Read-only default drift:** portable launch/diagnostics disabled only the legacy executor flag, not the newer provider command flag. Both mutation flags are now disabled for kit launches and checked by diagnostics, with regressions.
5. **v2.6 workflow integration drift:** older synthetic packets/adapters omitted new gate evidence and mishandled the RV decision clock. Repaired evidence plumbing against the existing evaluator/controller without changing gate thresholds or enabling live operation.
6. **Stale active documentation:** outdated versions, TODOs, data-capability claims, provider operation descriptions and skill output/acquisition guidance contradicted current code. Aligned current docs; retained dated deployment/research receipts as explicitly historical.
7. **Unsafe-looking prompt defaults:** removed hard-coded zero session loss; use verified fill records and reconciled pending orders; distinguish a requested re-entry search from a completed fresh pass. These clarify existing operating requirements, not amend the covenant.
8. **Navigation/CI gaps:** root omitted the research lab, archives were absent, and consumer workflows missed shared-runtime path changes. Added focused indexes, repository map, validation guide, local source-hygiene checks and consumer path filters.

## Archival and reorganization

| Original material | Preserved destination | Active replacement |
|---|---|---|
| Long evolving `notes.md` (1,432 lines) | `archive/architecture/design-notes/2026-10-03-autonomous-butterfly-notes.md` | Concise root notes and canonical architecture docs |
| Single-owner VID v1 guide | `archive/architecture/internal-execution-era/vector-id-system.md` | Existing guide path now routes compositional identity |
| Initial lab data audit and verification | `archive/research/laboratory/2026-10-02/` | Compatibility stubs, current capabilities/lifecycle docs |
| September Dhan setup/deployment receipts | `archive/deployment/dhan-office-mac/` | Current provider README + separate legacy-executor reference |
| September dashboard validation receipt | `archive/research/essvi-dashboard/` | Current dashboard methods/setup README |
| Orphan housekeeping policy (workflow retired in `ebc773e`) | `archive/deployment/retired-housekeeping/` | Explicit source CI, no replacement scheduler |

Every archive directory has a README with its period, supersession and non-operational warning. Historical text is preserved apart from notices and relocated links. Moves retain Git history; extracted historical receipts cite their source. No historical financial record was moved or rewritten.

**Deleted disposable material:** none found in the tracked baseline. The old service `.dockerignore` was replaced by a Dockerfile-specific repository-root allowlist, not a deletion of useful historical code. Existing ignored caches/dependency directories were not published.

## Compatibility retained

- `architecture/components/internal-execution/` alias manifest and mirror registry.
- `docs/workflows/internal-execution.md` and old Dhan call-map redirect.
- Assembled `docs/workflows/vector-id-registry.json` view.
- Existing Dhan MCP/legacy butterfly executor, OAuth and helper/import/export paths.
- Day-workflow SHADOW prototype and explicit accounting interfaces.
- Frozen research `observed_controller_v26.py`, evidence JSON, schema/resource mirrors and diagram render receipts.
- Old lab data-audit/verification links via stubs.

## Validation record

All practical offline source suites passed in their appropriate isolated environments:

| Check | Result |
|---|---|
| Architecture identities + validator | PASS; 100 canonical execution entities, 2 mounts, 4 bindings |
| Combined identity/metadata/Execution Testbed tests | 26 passed |
| Dhan Provider/MCP | 109 passed |
| Day-workflow/accounting | 189 passed |
| Portable kit + source-hygiene regressions | 18 passed (13 kit + 5 hygiene) |
| Butterfly skill | 56 passed |
| RV fixture validation | 9 positive/negative checks passed |
| Research laboratory | 413 passed, zero skipped; Ruff lint/format and mypy passed |
| Laboratory generated closure | 15 schemas, 2 resource mirrors, 5 diagram receipts passed |
| Laboratory config/doctor and demos | Offline checks, sandbox probes and both fixture graphs passed |
| Dashboard HAR | 12 passed in its separate NumPy/pandas environment |
| All three skill packages | Validated and rebuilt; bundled local links remain inside each skill |
| Portable setup | Real locked setup twice, preservation/idempotence, offline doctor and source ZIP passed |
| Extracted portable ZIP | Full local links/anchors, JSON and provider import closure passed; journals/private state omitted |
| Docker | Build passed; network-disabled non-root import/disabled-flags/no-testkit smoke passed |
| Whole source hygiene | Local Markdown paths/anchors, JSON, JS imports, archive indexes and whitespace passed |
| Workflow files | All 9 workflows parsed; shared consumer path filters repaired |

Total unit/regression cases across the seven suites: **823**, plus the nine RV fixtures and packaging/build/structural checks. The independent passes used fresh reviewers without relying on the original classifications.

Initial local failures were investigated, not ignored: the old workflow adapter lacked v2.6 gate evidence; macOS sandbox tests needed the canonical `/private/tmp` interpreter path; dashboard tests require their documented separate pandas environment. Final checks passed after source repairs or correct environment selection.

### Hosted publication verification

All **nine workflow families passed** after publication. The implementation/archive tree was tested at `84368b0cdb931700a89f8b5c3922ca435ff8c771`. The first hygiene run exposed a CI-only shallow-checkout issue: `git show --check HEAD` treated the shallow tip as a root commit and inspected unchanged historical whitespace. Commit `1eff16ab551facaae6916a83771081476a71942f` retains HEAD's parent; hygiene and portable-kit CI then passed. Historical records and the covenant were not changed to appease the check.

| Workflow | Tested commit | Verified result |
|---|---|---|
| Architecture identity checks | `84368b0` | [PASS](https://github.com/ayyararyan/volarb/actions/runs/37141960598) |
| Execution testbed | `84368b0` | [PASS](https://github.com/ayyararyan/volarb/actions/runs/37141960429) |
| Dhan Provider/MCP, including Docker build | `84368b0` | [PASS](https://github.com/ayyararyan/volarb/actions/runs/37141960664) |
| Shadow day workflow | `84368b0` | [PASS](https://github.com/ayyararyan/volarb/actions/runs/37141960636) |
| Butterfly skill regressions, RV fixtures and packages | `84368b0` | [PASS](https://github.com/ayyararyan/volarb/actions/runs/37141960534) |
| Research laboratory | `84368b0` | [PASS](https://github.com/ayyararyan/volarb/actions/runs/37141960652) |
| Dashboard HAR | `84368b0` | [PASS](https://github.com/ayyararyan/volarb/actions/runs/37141960620) |
| Portable Agent Kit | `1eff16a` | [PASS](https://github.com/ayyararyan/volarb/actions/runs/37142016600) |
| Repository source hygiene | `1eff16a` | [PASS](https://github.com/ayyararyan/volarb/actions/runs/37142016589) |

These are source-validation receipts, not deployment or broker-readiness claims. This subsequent documentation-only receipt records observed results without implying that all workflows ran on one identical SHA. The final tree has **439 tracked files**; the isolated worktree is clean and the original Drive checkout's unrelated dashboard edit remains intact.

## Independent second pass

Fresh architecture/testbed, documentation/research/CI, and provider/packaging reviewers inspected the reorganized tree. Their additional findings were repaired and rechecked:

- Simulator order-modification fields, weighted fills, ambiguity tracing, write-ahead identity ordering, virtual-clock monotonicity and deterministic error timestamps (seven regressions).
- Passive Chase parameter wording aligned to its existing counter semantics; no values or production strategy policy selected.
- Day-workflow CI includes its RV dependency; PR07 respects authorized review windows; logging preserves the sole live ledger and stable adjustment cycle IDs.
- Standalone skill and extracted-kit navigation closure; news calibration explicitly requires a research request.
- Malformed session-VRP objects and missing fit/arbitrage proof now return UNKNOWN; unavailable optional open-position loss evidence cannot mask a verified risk exit. Thresholds and frozen research behavior are unchanged.

All three reviewers concluded **no major unresolved findings** in their assigned areas. Parent verification preserved all VID/status pairs (100 canonical, 100 alias, 221 assembled), the covenant and 21 historical financial/journal files byte-for-byte, and the frozen research controller checksum.

## Updated files and indexes

The file-level classification above records original paths and dispositions; the grouped commits provide the exact diffs. Active edits cover identity metadata/validators, simulator correctness, provider capability export, package/Docker source closure, workflow evidence adapters/regressions, skills, current operating references/prompts, service READMEs and CI.

New current navigation includes root/docs maps, `architecture/README.md`, `docs/workflows/README.md`, `environments/execution/README.md`, `services/README.md`, `docs/providers/README.md`, `agent-kit/README.md`, `agent/docs/README.md`, `agent/docs/evidence/README.md`, `skill/README.md` and `docs/VALIDATION.md`. Each archive generation has its own index. No executable source module was relocated for cosmetic organization.

## Intentionally outstanding implementation

- Full generic Execution Engine convergence pipeline, production persistence/clock/scheduling and environment loader are not implemented by cleanup.
- Replay/shadow declarations and injected harnesses are not complete production or historical-replay runners.
- Dhan readiness/authentication and external Shaurya dashboard integrations remain deployment-specific and unverified by offline tests.
- Current manual workflow still requires supplied/reconciled evidence. The generic controller's missing-loss-input warning is not a verified budget pass; operational callers must validate it. Frozen replay behavior is unchanged.
- Inactive execution policy remains unadopted. No new trading authority, loss guarantee, multi-lot permission or monitoring has been introduced.
- Laboratory scientific limitations, external-data coverage and frozen evidence remain explicit; source cleanup does not promote research into production.

See [open tasks](../../tasks.md), [validation commands](../VALIDATION.md) and the [canonical map](../REPOSITORY_MAP.md).

## Commit groups

- `ed8050b` — execution identities, validators and deterministic testbed correctness.
- `50b532a` — provider packaging, portable source closure, current workflow evidence gates and skill consistency.
- `84368b0` — historical archives, current navigation, classification and audit report.
- `1eff16a` — preserve the parent commit for accurate hosted whitespace checks.
- This final documentation-only verification receipt records the completed CI results; its SHA is supplied in the handoff.
