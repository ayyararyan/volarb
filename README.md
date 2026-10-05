<h1 id="volarb">
  <a href="docs/assets/volarb-logo-light.svg#gh-light-mode-only"><img src="docs/assets/volarb-logo-light.svg" width="360" alt="VolArb"></a>
  <a href="docs/assets/volarb-logo-dark.svg#gh-dark-mode-only"><img src="docs/assets/volarb-logo-dark.svg" width="360" alt="VolArb"></a>
</h1>

**Quantitative research. Broker-neutral execution. Deterministic testing.**

VolArb brings Indian index-option research and strategy workflows together with reusable execution infrastructure. It separates the decision to trade from execution policy and broker mechanics, so research, simulation and provider integration can evolve independently.

[![Architecture validation](https://github.com/ayyararyan/volarb/actions/workflows/architecture-identity.yml/badge.svg?branch=main)](https://github.com/ayyararyan/volarb/actions/workflows/architecture-identity.yml)
[![Execution Testbed](https://github.com/ayyararyan/volarb/actions/workflows/execution-testbed.yml/badge.svg?branch=main)](https://github.com/ayyararyan/volarb/actions/workflows/execution-testbed.yml)
[![Dhan Provider tests](https://github.com/ayyararyan/volarb/actions/workflows/test-dhan-mcp.yml/badge.svg?branch=main)](https://github.com/ayyararyan/volarb/actions/workflows/test-dhan-mcp.yml)

[Architecture](#architecture) · [Start here](#start-here) · [Development](#local-development) · [Repository map](docs/REPOSITORY_MAP.md)

**Current scope:** broker contracts, the Dhan Provider, deterministic test infrastructure and research tooling are implemented. The complete generic Execution Engine is **under development**, not a deployed autonomous trading system.

## Capabilities and status

- **Execution contracts — implemented in Python.** Provider-neutral ports, the global Provider Error Envelope, immutable component identities and validated composition bindings are canonical under `execution-engine/volarb_execution/`. The policy/convergence pipeline and production environment loader remain in development.
- **Durable admission and recovery — implemented in Python.** Atomic ledger admission, account fencing and conservative broker-evidence reconciliation; [supported topology and limitations](docs/architecture/durable-execution-recovery.md). The full engine remains under development.
- **Dhan Provider — implemented.** REST/WebSocket integration; normalized commands, queries and streams; instrument translation and readiness gates. Broker mechanics, not trading policy.
- **Execution Testbed — implemented.** Virtual time, seeded scenarios, simulated broker/market, faults, traces and composition harnesses. Complete-engine coverage awaits the engine.
- **Research skills — implemented decision support.** Option-surface analytics, physical realized-volatility forecasting, event/news filtering and butterfly workflows. No order authority.
- **Research laboratory — experimental.** Offline experiments, isolated workers, dataset provenance and evidence grading. A separate scientific baseline, not the live decision controller.

The [SHADOW day-workflow prototype](services/day-workflow/README.md) and optional [eSSVI/IV/HAR dashboard](services/essvi-dashboard/README.md) are supporting services. Their deployment-specific dependencies are documented separately.

## Architecture

The canonical boundary is **Strategy → optional Strategy Execution Adapter → Execution Engine → Broker Execution Port → Broker Provider**.

The Execution Engine is reusable and strategy-agnostic: **`component.execution_engine`**, with immutable VID namespace **`[5,0,...]`**. VolArb's position/strategy layer owns instrument intent, butterfly semantics and risk decisions. Dhan translates, transmits and normalizes broker facts; it does not choose execution policy.

The **designed** execution path is:

```text
Margin Optimization → Execution Slicing → Optimal Execution
    → Execution Recovery / Command Commit Guard → Broker Execution Port
```

**State Integrity, Execution Recovery and Interrupt Control** span that path. The former `component.internal_execution` name is a compatibility alias only.

See the [architecture index](architecture/README.md) for identities and composition, and the [Execution Engine design](docs/workflows/execution-engine.md) for policy and recovery semantics.

### One engine, injected environments

The testing model requires **the same engine code**, with dependencies supplied through ports—not a second engine or test-only policy branches.

| Test dependencies | Production target |
|---|---|
| Simulated broker | Dhan Provider |
| Virtual clock, simulated observations | Real clock, live observations |
| Seeded faults and recorded traces | Normalized provider errors and reconciliation |

The five intended levels are **box tests → composition tests → full-engine scenarios → mass simulation → replay/shadow**. Box/composition harnesses and scenario/mass drivers exist; complete-engine mounting and dedicated replay/shadow runners remain planned. Environment manifests are declarations, not an executable loader.

[Execution Testbed](docs/testing/execution-testbed.md) · [Environment definitions](environments/execution/README.md)

## Start here

Choose a path by the work you want to do. The [full repository map](docs/REPOSITORY_MAP.md) covers secondary services, tooling and historical records.

| Work on | Canonical entrypoint |
|---|---|
| Architecture and identities | [architecture/](architecture/README.md) — manifests, registries, composition and validation |
| Generic execution | [execution-engine/](execution-engine/README.md) — implemented contracts and the runtime boundary |
| Execution testing | [execution-testkit/](execution-testkit/README.md) and [environments/execution/](environments/execution/README.md) |
| Broker integration | [services/dhan-chatgpt-mcp/](services/dhan-chatgpt-mcp/README.md) — Dhan Provider and service interfaces |
| VolArb strategy | [Strategy composition/design](docs/autonomous-butterfly-workflow.md); [current operating algorithm](docs/DAILY_OPERATING_ALGORITHM.md) |
| Research and decision modules | [skill/](skill/README.md) — butterfly outlook, realized volatility and market news |
| Offline experiments | [agent/](agent/README.md) — Butterfly Research Laboratory |
| Source/workspace packaging | [agent-kit/](agent-kit/README.md) — distinct from the research laboratory |
| Operations and documentation | [docs/](docs/README.md) and [prompts/](prompts/README.md) — canonical procedures and bounded prompts |
| Historical generations | [archive/](archive/README.md) — superseded designs and reports, not operational instructions |

## Local development

Start with **offline source validation**. No broker credentials or running services are required. Use the repository pins: **Node 26.5.0**, **npm 11.17.0** and **Python 3.12.13**. Run from the repository root:

```sh
# Canonical Python Execution Engine box tests.
python3.12 -B -m unittest discover -s execution-engine/tests -p 'test_*.py' -v

# Architecture and legacy JavaScript Execution Testbed: no npm install required.
node architecture/validate.mjs
node --test architecture/lib/*.test.mjs architecture/*.test.mjs \
  execution-testkit/test/*.test.mjs

# Locked provider dependencies and synthetic tests.
npm ci --ignore-scripts --prefix services/dhan-chatgpt-mcp
npm test --prefix services/dhan-chatgpt-mcp

# Local documentation paths, anchors, JSON and JavaScript imports.
python3.12 -B tools/check_repository.py
```

For Python regression suites, isolated environments, research-lab checks, skill packages and container builds, follow the [validation guide](docs/VALIDATION.md). The laboratory has its own dependency lock; do not merge it with the root kit environment. The [portable kit guide](docs/AGENT_KIT.md) covers installation without restoring private runtime state.

### Production boundary

Repository code and passing CI do not activate trading or establish live broker readiness. Credentials and account state stay private; test, replay, shadow and production dependencies are separate. **Production must never depend on `execution-testkit`.** Live mutations require explicit production configuration, broker readiness and operating authorization; they are not a quickstart step.

The current strategy workflow remains human-executed under the [adopted covenant](docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md). Account journals remain in private storage outside this source repository; they are not live account truth. Publishing source does not deploy services or refresh installed skills.

### Development conventions

- Preserve canonical VIDs and compatibility aliases; never renumber existing identities.
- Keep strategy semantics and provider-native logic outside the generic engine.
- Inject runtime dependencies; do not add test-only branches to production execution policy.
- Update canonical documentation with code, and run the affected suites plus architecture validation.

Repository release: **v0.1.0 — Execution Infrastructure Foundation**. See the [changelog](CHANGELOG.md) and [release/versioning policy](docs/RELEASING.md). Component, schema and skill versions remain independently scoped. Follow [development history](docs/DEVELOPMENT_HISTORY.md) for milestones and [open implementation work](tasks.md) for what remains.

## Licensing

VolArb is proprietary software owned by **[Shunya](https://www.shunya.solutions)**, the sole proprietorship of Aryan Ayyar. Source is provided for transparency, inspection and evaluation; public visibility does **not** make this an open-source project. Use, modification, redistribution, commercialization and derivative works require written permission except as expressly permitted by the [LICENSE](LICENSE), applicable GitHub terms or third-party licenses. Licensing enquiries: [shunya.solutions](https://www.shunya.solutions).

Copyright © 2026 Shunya. All Rights Reserved.
