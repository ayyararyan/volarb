# Repository releases

## Version policy

[`VERSION`](../VERSION) is the authoritative **repository release version**. Annotated Git tags use `vMAJOR.MINOR.PATCH`; the [changelog](../CHANGELOG.md) summarizes each release. A repository release identifies a source snapshot, not a monolithic installable package or a deployment.

The first repository release is **0.1.0**. The release audit found no earlier Git tags, GitHub Releases or repository-wide version convention. Existing package, component, schema and skill versions are independent and are **not** reset or synchronized to the repository version.

We use [Semantic Versioning](https://semver.org/spec/v2.0.0.html) for repository milestones:

- During `0.x`, a minor increment records substantial capability/architecture changes or documented contract incompatibilities; patches are compatible fixes or documentation corrections. Contracts may still evolve before 1.0.
- The compatibility surface is the documented exported ports/provider APIs, identity model and portable source/setup interfaces. Canonical VIDs remain immutable even across version increments.
- `1.0.0` requires an explicitly accepted stable contract and implementation boundary; it is not implied by this foundation release.
- Normal `0.x` releases are validated milestones. Use a prerelease suffix/flag for preview candidates that have not met the intended release acceptance boundary. A normal release does not mean live-trading or production readiness.
- Never move or replace a published version tag. Corrections to released source require a new version.

## First release decision

| Field | Decision |
|---|---|
| Previous repository version | None; previously unversioned |
| First version | `0.1.0` |
| Reason | First validated execution-infrastructure foundation, not a patch to an existing repository release |
| Scope | Contracts, Dhan integration, deterministic test infrastructure, research tooling and repository organization |
| GitHub classification | Normal `0.x` release, not a prerelease: the stated foundation scope is validated, while incomplete runtime work is explicitly excluded |

The Dhan service package is `0.3.0`, research laboratory and portable kit are `0.1.0`, Execution Engine architecture manifest is `1.1.0`, Dhan architecture manifest is `1.4.0`, and the active butterfly decision skill is `2.6`. These are separate version domains, not earlier VolArb repository releases.

## Release procedure

1. Fetch `main`, tags and GitHub Releases. Inspect the working tree and version history; isolate unrelated edits. Record the previous/proposed version, rationale, scope and known limitations.
2. Audit implementation against canonical docs. Preserve strategy/provider boundaries, compatibility aliases and immutable VIDs. Preserve private state and historical financial evidence outside the source repository.
3. Update `VERSION`, the root README version reference, changelog and versioned notes in `docs/releases/`. Change component versions only when their own release scope requires it. Keep `VERSION` and `CHANGELOG.md` in the portable source manifest.
4. Run the [offline validation guide](VALIDATION.md), including architecture/testbed, provider, research/skills, auxiliary services and portable setup/packaging. Keep raw logs local. Do not source production credentials or contact the broker.
5. Commit preparation changes on a short-lived branch following the [branch convention](REPOSITORY_MAP.md#branch-naming-and-lifecycle), open a PR and merge to `main` only after validation. All ten CI workflow families run on every PR; a `VERSION` change also exercises all ten on `main`. Verify the exact merged candidate SHA and every relevant run, including container import closure, without force-pushing. Passing checks on an ancestor are not a release receipt. Tags normally make a permanent release branch unnecessary.
6. Record the validated full SHA, local checks and hosted run URLs in the GitHub Release body. Verify the candidate is still the intended `main` commit before creating an annotated tag. If new work changes the boundary, reconcile and revalidate first.
7. Push the annotated tag and create the GitHub Release with explicit notes and the intended normal/prerelease flag. Use `--verify-tag` when publishing with `gh`; do not let an omitted tag silently select a new target. GitHub's automatic source archives are sufficient; do not attach private/runtime artifacts.
8. Verify the remote peeled tag SHA, release tag/title/body, README links, all candidate checks and clean worktree. Tag publication may trigger additional offline workflows; inspect those too. Published release notes carry the final commit/run receipt so no post-tag documentation commit is necessary.

Releasing source never deploys services, enables provider mutations, changes credentials, starts monitoring or authorizes trading.
