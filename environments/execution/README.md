# Execution environment definitions

Status: **declarative dependency contracts**. No environment loader or production execution pipeline is implemented by these JSON files. Reading a manifest does not enable trading, create services, or supply credentials.

The same Execution Engine components must run in every environment with injected dependencies; no internal `test_mode` branch or second engine is permitted.

| Manifest | Market | Broker target | Clock/ledger | Testkit |
|---|---|---|---|---|
| [test.json](test.json) | Simulated | Simulated only | Virtual / memory | Allowed |
| [replay.json](replay.json) | Recorded | Simulated only | Virtual / memory or temporary | Allowed |
| [shadow.json](shadow.json) | Live read-only | No mutations | Real / shadow | Allowed |
| [production.json](production.json) | Live provider | Real provider, subject to separately configured authorization/readiness | Real / durable | Forbidden |

`production.json` describes the intended real-provider boundary; it is not a switch that authorizes broker mutations. Replay ingestion and live shadow runners remain to be implemented. [The current testkit](../../execution-testkit/README.md) provides deterministic primitives and caller-supplied component/scenario harnesses.

From the repository root, run `node --test execution-testkit/test/environment.test.mjs` to check the declarative separation. Production code must never import `execution-testkit`; the test suite also checks source dependencies.
