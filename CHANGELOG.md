# Changelog

Repository source releases are versioned independently of component packages and schemas. See the [release policy](docs/RELEASING.md); dated development detail remains in [development history](docs/DEVELOPMENT_HISTORY.md).

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
