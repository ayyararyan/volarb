# Architecture and identity

The repository separates Volarb strategy semantics, reusable execution policy, and mechanical broker providers:

```text
Strategy -> optional Strategy Execution Adapter -> Execution Engine
         -> Broker Execution Port -> Dhan Provider / future provider
```

`component.execution_engine` owns immutable canonical VIDs `[5,0,...]`; it does not belong to Volarb. Dhan owns translation, transport and normalized observations, not execution or strategy policy.

## Authoritative files

| Area | Entry point |
|---|---|
| Identity model | [Canonical, bound and runtime identity](../docs/architecture/compositional-identity.md) |
| Components | [Component catalog](registries/component-registry.json) |
| Execution Engine | [Manifest](components/execution-engine/manifest.json), [canonical VIDs](components/execution-engine/vector-id-registry.json), [design](../docs/workflows/execution-engine.md) |
| Decision modes | [Detailed classification and authority boundaries](../docs/architecture/decision-modes.md), [execution inventory](components/execution-engine/decision-modes.json), [strategy inventory](strategies/volarb/decision-modes.json) |
| Providers | [Dhan manifest](providers/dhan/manifest.json), [implementation](../services/dhan-chatgpt-mcp/README.md) |
| Strategy composition | [Composition catalog](registries/composition-registry.json), [Volarb mounts/bindings](strategies/volarb/composition.json) |
| Testing | [Execution Testbed manifest](testing/execution-testbed.json), [test infrastructure](../execution-testkit/README.md) |
| Compatibility | [Assembled registry](../docs/workflows/vector-id-registry.json), legacy `components/internal-execution/` alias/mirror |
| History | [Archived architecture](../archive/architecture/README.md) |

## Implementation status

These manifests define architecture, not an autonomous production deployment. [execution-engine/](../execution-engine/README.md) currently implements shared contracts, structural ports and the Python Command Commit Guard. The remaining margin/slicing/optimal-execution/recovery/integrity/interrupt pipeline is an active design; testkit primitives and injected harnesses exist, but a complete pipeline is not implemented here.

Retired registry entries remain tombstones. Never reuse or renumber them. New code should use `component.execution_engine`; `component.internal_execution` remains a compatibility alias only.

## Offline validation

Run from the repository root:

```sh
node architecture/validate.mjs
node --test architecture/lib/*.test.mjs architecture/*.test.mjs
```

Validation covers manifest paths, identities, versions, mounts/bindings, provider port declarations, compatibility mirrors and complete decision-mode coverage. Hybrid entries require an explicit LLM role, deterministic responsibility and invalid-output behavior. It makes no broker calls.
