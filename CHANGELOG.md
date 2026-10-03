# Changelog

Repository source releases are versioned independently of component packages and schemas. See the [release policy](docs/RELEASING.md); dated development detail remains in [development history](docs/DEVELOPMENT_HISTORY.md).

## Unreleased — proprietary publication preparation

- Establish Shunya ownership and a proprietary inspection-only LICENSE, with explicit GitHub-platform and third-party exceptions. Preserve Plotly/dependency and embedded-font notices; do not relicense dependencies.
- Remove private financial payloads from the proposed source tree, retain their originals privately, and route future account journals outside the checkout. Replace observed/undocumented fixture inputs with synthetic scenarios and independently replace packaging helpers with uncertain historical attribution.
- Add publication-guard and packaging regressions, legal-file export coverage, unconditional PR validation and a proposed main ruleset. Canonical architecture, trading limits and production behavior are unchanged.
- **Not a public release:** remote history and PR-cache remediation remain pending; private-repository protection requires an available GitHub plan. The owner chose to remain private. No release/version change, history force-push, deployment or trading activation. [Audit and remaining gates](docs/audits/2026-10-04-public-preparation.md).

## [0.1.0] - 2026-10-04

**Execution Infrastructure Foundation** — first repository release; no earlier repository version or tag. [Full release notes](docs/releases/v0.1.0.md).

### Architecture and execution

- Canonical, strategy-agnostic `component.execution_engine`, preserved `[5,0,...]` VIDs, composition identities and optional Strategy Execution Adapter boundary.
- Implemented provider-neutral broker vocabulary, injected runtime ports and global Provider Error Envelope. The complete execution policy/convergence pipeline remains under development.

### Broker provider

- Dhan configuration/readiness, neutral order translation, queries and mutation primitives, recovery lookup, market/order streams, correlation projection and normalized errors.
- Corrected stale HTTP User-Agent strings to the existing Dhan package version `0.3.0`; no unrelated component/schema versions changed.

### Testing and repository quality

- Deterministic clock/RNG, simulated broker/market, test ledger, faults, component/composition harnesses, scenario/mass drivers and trace invariants.
- Explicit test/replay/shadow/production dependency declarations; production excludes `execution-testkit`.
- Structured archival, canonical repository map, updated documentation and README/logo, portable import closure and source hygiene.
- Repository version changes now trigger all CI workflow families. Portable source packages include release metadata.

### Compatibility and known limitations

- `component.internal_execution` and legacy provider/executor surfaces remain compatibility paths; VIDs and historical records are preserved.
- No complete generic engine runtime, durable production ledger, environment loader, replay/live-shadow runners, additional broker provider or production-readiness claim. Synthetic validation is not live broker validation.
- Source-only release; no deployment, broker orders, credential changes or trading activation.

[0.1.0]: https://github.com/ayyararyan/volarb/releases/tag/v0.1.0
