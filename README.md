# Volarb

Indian index-option butterfly research and decision tooling, plus reusable broker-neutral execution infrastructure under development. The repository contains **three distinct systems**: the current manual trading workflow, an offline research laboratory, and the evolving execution architecture. Source publication does not deploy services or authorize trading.

## Architecture

```text
Strategy (Volarb or another strategy)
    │ optional Strategy Execution Adapter
    ▼
Execution Engine — component.execution_engine, immutable [5,0,...]
    │ Broker Execution Port
    ▼
Broker Provider — Dhan / future providers
```

The Execution Engine is **strategy-agnostic**, not owned by Volarb. Strategy geometry and risk decisions stay upstream; the Dhan Provider performs mechanical broker operations. `component.internal_execution` is a compatibility alias only.

The designed normal path is **Margin Optimization → Execution Slicing → Optimal Execution → Execution Recovery / Command Commit Guard → Broker Execution Port**. State Integrity, Execution Recovery and Interrupt Control are cross-cutting. See the [architecture index](architecture/README.md) and [canonical execution design](docs/workflows/execution-engine.md).

**Implementation status:** `execution-engine/` currently supplies runtime ports and contracts, not a completed convergence pipeline. The Dhan connector and deterministic test infrastructure are implemented. Test/replay/shadow/production inject dependencies; production must never import `execution-testkit`. Environment manifests are declarations, not deployment or activation commands.

## Start here

| Goal | Canonical entrypoint |
|---|---|
| Understand the whole repository | [Repository map](docs/REPOSITORY_MAP.md) |
| Follow the current manual trading workflow | [Daily operating algorithm](docs/DAILY_OPERATING_ALGORITHM.md), [covenant](docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md), [prompts](prompts/README.md) |
| Understand strategy composition and identities | [Architecture](architecture/README.md), [Volarb design](docs/autonomous-butterfly-workflow.md) |
| Build reusable execution infrastructure | [Execution Engine](execution-engine/README.md) |
| Test with deterministic broker/clock/ledger dependencies | [Execution Testbed](execution-testkit/README.md), [environments](environments/execution/README.md) |
| Integrate a broker | [Dhan Provider](services/dhan-chatgpt-mcp/README.md), [global Provider Error Envelope](docs/providers/provider-error-contract.md) |
| Run offline research | [Butterfly Research Laboratory](agent/README.md) |
| Use current-observation research modules | [Skills](skill/README.md) |
| Install a portable research kit | [Agent kit](docs/AGENT_KIT.md) |
| Review development decisions or older generations | [Current notes](notes.md), [history](docs/DEVELOPMENT_HISTORY.md), [archive](archive/README.md) |

## Stable directory ownership

- `architecture/` — component identities, manifests, composition bindings and validation.
- `execution-engine/` — reusable broker-neutral runtime contracts and future pipeline implementation.
- `execution-testkit/`, `environments/` — non-production testing tools and explicit dependency declarations.
- `services/` — Dhan integration, SHADOW day-workflow prototype and optional eSSVI/HAR dashboard.
- `agent/` — research-only laboratory, distinct from the portable `agent-kit/` deployment templates.
- `skill/` — Butterfly Market Outlook v2.6, intraday HF-RV model and news filter.
- `docs/`, `prompts/` — canonical explanations, operational procedure and bounded user-invoked prompts.
- `tools/`, `tests/`, `.github/` — source packaging, regression checks and CI.
- `market-outlook/`, `trade-log/` — preserved dated journals and historical execution evidence, **not live account truth**.
- `archive/` — superseded architecture/research/deployment material, explicitly non-operational.

## Operating boundaries

The personal covenant requires **intraday only, flat by 15:00 IST, no entry or recenter thereafter**. Dhandho researches; Aryan executes. New-entry research is one selected butterfly, one lot total, with the adopted ₹1,000 daily decision-loss budget and a separate ₹1,000 free-cash margin reserve. Neither is a guaranteed realized-loss cap.

Fresh broker positions/orders and executable quotes precede recommendations; first terminal gate wins. Generic overnight diagnostics cannot override the covenant. Private credentials, browser state, raw broker evidence and the sole live `Trading/ledger/` store remain outside this repository. Installed skills and running services do not automatically track source updates.

For local offline checks, see [validation](docs/VALIDATION.md). CI checks source behavior; it does not establish live broker readiness.
