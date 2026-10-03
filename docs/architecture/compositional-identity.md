# Compositional Identity Architecture

Status: **active architecture**.

## Purpose

Volarb no longer treats Execution Engine as strategy-owned. Execution Engine is a reusable, broker-neutral component that can be mounted into any compatible strategy. Dhan is independently reusable as a broker provider. The identity model therefore separates **what an entity is** from **where an occurrence of that entity is mounted** and from **which live runtime object is currently using it**.

## Three identity levels

1. **Canonical identity (CVID)** — immutable identity inside a reusable component. Existing Execution Engine vectors `[5,0,...]` are preserved exactly and now belong to `component.execution_engine`.
2. **Bound identity (BVID)** — derived identity of a canonical entity when a component is mounted in a composition. A BVID is composition + mount + canonical VID. It never replaces or mutates the CVID.
3. **Runtime identity (RID)** — ephemeral/live identities such as `intent_id`, `intent_version`, `slice_id`, `action_id`, `correlation_id`, order IDs and provider event IDs. Runtime identity points back to a bound/canonical context but is not architecture identity.

Canonical example:

```text
cvid://component.execution_engine/5.0.8.1.2
```

The same Command Commit Guard mounted in Volarb:

```text
bvid://composition.volarb/mount.volarb.execution.main/5.0.8.1.2
```

A future strategy can mount the same canonical component and obtain a different BVID without changing `[5,0,8,1,2]`.

## Components own canonical identities

`component.execution_engine` owns the canonical `[5,0,...]` namespace. The leading legacy code `5` is preserved to avoid a destructive renumbering; its semantics are now **Execution Engine component namespace**, not "Box 5 owned by Volarb."

`provider.dhan` has a stable string component identity but deliberately has **no Volarb VID**. Provider-internal IDs remain provider-owned. Mount and binding IDs are created by compositions.

## Compositions own mounts and bindings

`composition.volarb` owns:

- the mount `mount.volarb.execution.main`;
- the nested provider mount `mount.volarb.execution.main.broker.primary`;
- strategy-to-execution intent binding;
- execution-to-strategy fact binding;
- strategy-to-execution interrupt binding;
- the Broker Execution Port -> Dhan provider implementation binding.

A cross-component connection is never canonical to either endpoint. It is a first-class composition entity with its own immutable `binding_id`.

## Strategy / execution / broker separation

```text
strategy.volarb
    |
    | broker-neutral execution requirement
    v
mount.volarb.execution.main
    component.execution_engine
    |
    | Broker Execution Port
    v
mount.volarb.execution.main.broker.primary
    provider.dhan
```

The strategy owns the desired economic state. Execution Engine owns how to converge toward that state under its margin, slicing, optimal-execution, interrupt, integrity and recovery rules. The provider owns mechanical broker translation/transport/observation only.

## Authoritative files

- Component catalog: `architecture/registries/component-registry.json`
- Composition catalog: `architecture/registries/composition-registry.json`
- Execution Engine manifest: `architecture/components/execution-engine/manifest.json`
- Execution Engine canonical VID registry: `architecture/components/execution-engine/vector-id-registry.json`
- Dhan provider manifest: `architecture/providers/dhan/manifest.json`
- Volarb composition: `architecture/strategies/volarb/composition.json`
- Identity helpers: `architecture/lib/identity.mjs`
- Consistency validator: `architecture/validate.mjs`

The historical `docs/workflows/vector-id-registry.json` remains a compatibility/assembled view. It mirrors the canonical Execution Engine entries but is no longer the ownership authority for `[5,0,...]`.

## Non-destructive migration rule

No existing Execution Engine VID is renumbered or reused. Existing cross-box edge VIDs remain as compatibility references, but their architectural ownership is transferred to the explicit Volarb composition bindings.

## Recursive composition

Mounts can be nested. The Dhan provider is mounted under the execution mount today; future execution algorithms, market-data providers or broker providers can be mounted in the same manner. The model does not require extending the five-element canonical VID whenever composition depth increases.

## Runtime requirement

Every live execution object should ultimately carry enough context to resolve:

```text
composition_id
mount_id
canonical_component_id
canonical_vid
intent_id / intent_version
slice_id
action_id
correlation_id
provider references
```

This preserves strategy separation, prevents state collisions across multiple mounts, and keeps audit/recovery traces reproducible.


## Strategy Execution Adapter

A strategy may optionally place a strategy-specific adapter between itself and the Execution Engine. The adapter translates strategy semantics into broker-neutral economic execution requirements.

The current Volarb composition may bind directly when Position Management already emits that broker-neutral contract. A separate adapter is introduced only when strategy semantics genuinely need translation.

## Legacy alias

`component.internal_execution` is retained only as a compatibility alias for `component.execution_engine`. No existing `[5,0,...]` VID was renumbered.
