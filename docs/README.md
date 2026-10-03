# Documentation index

Use the [repository map](REPOSITORY_MAP.md) for ownership and implementation status. These documents have different authority; none of the design or historical material activates live execution.

| Area | Canonical material | Status |
|---|---|---|
| Personal trading limits | [Covenant](PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md) | Adopted policy, unchanged by cleanup |
| Current manual workflow | [Daily algorithm](DAILY_OPERATING_ALGORITHM.md), [standing workflow](WORKFLOW.md) | Current v2.6 process; no automatic monitoring |
| Reusable architecture | [Architecture index](../architecture/README.md), [compositional identity](architecture/compositional-identity.md) | Canonical identities and boundaries |
| Volarb strategy design | [Master graph](autonomous-butterfly-workflow.md), [workflow index](workflows/README.md) | Design, not adopted autonomous authority |
| Generic execution | [Execution Engine design](workflows/execution-engine.md), [runtime status](../execution-engine/README.md) | Design plus implemented contracts |
| Provider contracts | [Dhan Provider](providers/dhan-execution.md), [call map](providers/dhan-execution-engine-call-map.md), [error envelope](providers/provider-error-contract.md) | Current provider integration |
| Testing | [Execution Testbed](testing/execution-testbed.md), [validation commands](VALIDATION.md) | Offline checks; not live readiness |
| Deployment | [Portable kit](AGENT_KIT.md), [dependencies](DEPENDENCY_INVENTORY.md) | Source-only setup; private state external |
| Proposed execution authority | [Inactive policy draft](AUTONOMOUS_EXECUTION_POLICY_DRAFT.md) | Unadopted proposal, not current governance |
| Releases | [Changelog](../CHANGELOG.md), [release policy](RELEASING.md), [v0.1.0 notes](releases/v0.1.0.md) | Source milestones, not deployment approval |
| Ownership and publication | [Proprietary LICENSE](../LICENSE), [third-party notices](../THIRD_PARTY_NOTICES.md), [preparation audit](audits/2026-10-04-public-preparation.md) | Shunya-owned; publication remains blocked pending history and protection prerequisites |
| Development record | [History](DEVELOPMENT_HISTORY.md), [cleanup audit](audits/2026-10-03-repository-cleanup.md) | Dated provenance |
| Superseded generations | [Archive](../archive/README.md) | Historical, never operational |
