# Proprietary public-source preparation — 2026-10-04

**Status: private preparation; not publication clearance.** The owner explicitly
chose to keep this repository private pending enforceable private-repository
branch protection. This preparation does not authorize deployment or trading.
It must not be merged or described as safe for public visibility until the
remaining history and platform-exposure work below is resolved.

## Ownership and scope

VolArb remains proprietary software of **Shunya, the sole proprietorship of
Aryan Ayyar**. The [LICENSE](../../LICENSE) permits limited inspection, preserves
necessary GitHub platform rights and non-waivable legal rights, and otherwise
requires written authorization for use, modification, deployment and
redistribution. Public visibility would not make VolArb open source.

The audit baseline is the existing private `v0.1.0` source release. Repository
and component versions are unchanged. No release was retagged, no remote Git
history was rewritten and no live financial ledger was changed by this work.

## Audit coverage and findings

| Surface | Review | Result / disposition |
|---|---|---|
| Reachable Git history | 389 commits, 1,092 unique blobs, 18 refs: ten branches, one annotated tag and seven PR heads | Private financial records and identifiers remain in remote history; removal is not complete |
| Credentials | Gitleaks 8.30.1 maintained rules; full-history patches, every reachable blob, current tree, commit/tag metadata and GitHub metadata; full redaction, decoding/archive inspection and manual triage | No confirmed credentials; no credential-rotation requirement identified by this audit |
| Financial records | Journals, ledgers, trade write-ups and broker snapshots | 21 payload files removed from the proposed source tree; originals preserved privately; historical copies still block publication |
| Market fixtures | One observed IV/HAR dashboard fixture and four RV fixtures without documented provenance | Replaced with independently specified synthetic inputs; RV bytes reproduce from a checked-in generator |
| Private identifiers | Documentation, archived receipts and Git metadata | Current source neutralized; historical workstation/tunnel identifiers, personal financial narratives and two private identity emails require history remediation |
| GitHub text | Release, issues, PR comments, reviews and commit comments | Targeted manual review found technical/synthetic discussion rather than account payloads or confirmed credentials |
| Actions logs | 192 available run-log archives; one additional run had zero jobs and no log | No confirmed credentials or private financial payloads in reviewed logs |
| Actions artifacts | All 78 artifact archives; 11,892 nested entries across downloaded archives | 40 old packages contained private workstation paths; privately backed up, deleted from GitHub and individually verified absent; 38 unaffected baseline artifacts retained |
| Artifact scanner triage | 230 generic-key alerts, with 9,449 file hashes recomputed across 36 checksum manifests | All alerts were checksum false positives, not credentials |

This is bounded evidence, not a guarantee that a detector finds every secret or
establishes data redistribution rights. Raw findings, exact private identifiers,
downloaded artifacts, the verified Git bundle and rewrite maps remain outside
the repository. They must never be attached to a public PR or release.

## Proposed source remediation

- Account journals and ledgers belong in private storage outside this checkout.
  The two historical journal directories retain navigation-only READMEs.
  Prompts, skills, kit templates and workflow documentation now enforce that
  boundary rather than instructing account-data publication.
- The historical classification table retains its 402 rows and classifications,
  but 42 identifying path cells for 21 private records are explicitly redacted
  to neutral record IDs. The original table and mapping remain private; a
  candidate-wide scan found no remaining attributable trade filenames/cycle IDs.
- Trading limits, controller decisions, broker APIs, canonical VIDs and the
  Execution Engine/provider boundary are unchanged.
- Five fixture inputs are explicitly synthetic. Four RV scenarios are generated
  from constants and analytic functions, not copied observations.
- Two packaging helpers with uncertain historical attribution were replaced by
  independent implementations preserving the required interface. Skill exports
  now include the proprietary LICENSE and reject unsafe packaging inputs.
- [Third-party notices](../../THIRD_PARTY_NOTICES.md) preserve the bundled Plotly
  distribution/dependency notices and the Recursive font's SIL OFL. External
  package-manager dependencies keep their own terms and are not Shunya property.
- Ignore rules and the [public-source guard](../../tools/check_public_source.py)
  reject known private payloads, runtime artifacts and identifying paths. The
  guard is an additional tripwire, **not** a substitute for secret/history review.

## History remediation is still pending

A local-only rewrite rehearsal removes 28 historical paths and 126 associated
payload blobs, neutralizes identified private text and remaps private author
identities. It changes 362 of the 389 baseline commits and prunes 112. All ten
branches, all seven baseline PR refs and `v0.1.0` are affected. The original
mirror and verified private bundle are preserved; the rehearsal has no remote.

That rehearsal is **not** the runnable candidate: it must be reconciled with the
new fixtures, replacement helpers and legal/source changes and fully revalidated.
The existing release must not be silently retagged. A concrete transition must
address every reachable branch/tag, the permanent private release checkpoint,
GitHub-held PR refs and cached commit/diff views. A force push alone does not
remove those views. Any new preparation PR adds another ref to the purge scope.

A GitHub Support request draft and exact ref/commit maps have been prepared
privately, not submitted. Support's ability to remove sensitive financial data
must be confirmed; it is not a general mechanism for erasing non-sensitive
provenance. A separately isolated public-source repository would be a different
owner decision, not an automatic workaround. See GitHub's
[sensitive-data removal guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Access and branch protection

- The only human collaborator is `ayyararyan`, with administrator ownership.
  No teams, pending collaborator invitations, deploy keys or webhooks were found.
- The owner explicitly authorized all four existing apps: **Aryan Repository
  Steward, ChatGPT Codex Connector, Render and Vercel**. Their existing
  all-repository selections and permissions were retained; this audit did not
  narrow their access. Several have source/workflow write permissions, and
  Vercel has administration write permission. Authorization is not a claim of
  least-privilege scoping.
- Actions has a read-only default workflow token and cannot approve PR reviews.
- The [proposed main ruleset](../../.github/rulesets/main.json) prohibits deletion
  and force pushes, requires PRs, resolved review threads and ten uniquely named
  GitHub Actions checks against an up-to-date branch. Zero additional approvals
  accommodates a sole maintainer; it is not a two-person-review policy. There are
  no routine bypass actors. An administrator can recover by editing the ruleset.
- Every proposed required workflow runs on every PR, avoiding path-filter merge
  deadlocks. Push filters are retained where appropriate.
- **The ruleset is not active.** GitHub rejected private-repository protection
  access with an upgrade requirement. The owner chose to keep the repository
  private; no plan purchase or visibility workaround was attempted. GitHub
  documents [ruleset plan availability](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).

## Validation and publication gate

The preparation PR records exact candidate CI results. Local tests passed:

| Suite | Result |
|---|---:|
| Architecture identity + Execution Testbed | 8 + 18 tests |
| Dhan provider | 109 tests |
| Root kit, hygiene, packaging and publication guard | 36 tests |
| Day workflow | 189 tests |
| Butterfly skill | 56 tests |
| HAR dashboard | 12 tests |
| Research laboratory | 413 tests, zero skips |
| **Total** | **841 tests passed** |

Additional checks passed: nine RV checks; four reproducible synthetic fixtures;
three skill exports; architecture validation (100 entities, two mounts, four
bindings); link/path hygiene; research lint/format/types, four sandbox probes,
two controlled demo graphs and generated artifacts; isolated portable setup
twice, offline doctor and source packaging. A macOS research-runner path-alias
failure was resolved by invoking the canonical interpreter path, without source
changes or weakening sandbox enforcement. See [validation commands](../VALIDATION.md).
Synthetic/offline tests are not live broker validation.

A separate maintained-rule Gitleaks scan of the proposed source tree returned
zero findings. Required license/notice files and financial-payload exclusions
were also checked in the generated portable and skill archives.

Before public visibility, resolve and re-audit history/PR caches and old artifact
exposure; validate the exact intended main commit; merge reviewed changes; apply
and verify enforceable protection and access controls while still private; then
repeat the final source/history/platform scan. Only after all those gates may
visibility change, followed by anonymous-read and protection verification.

Until then: **private, draft preparation only; no anonymous-public verification,
no protected-main claim and no public-release clearance.**
