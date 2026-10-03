# Compositional Identity Architecture

Status: **active architecture**.

## Purpose

Volarb no longer treats Internal Execution as strategy-owned. Internal Execution is a reusable, broker-neutral component that can be mounted into any compatible strategy. Dhan is independently reusable as a broker provider. The identity model therefore separates **what an entity is** from **where an occurrence of that entity is mounted** and from **which live runtime object is currently using it**.

## Three identity levels

1. **Canonical identity (CVID)** — immutable identity inside a reusable component. Existing Internal Execution vectors `[5,0,...]` are preserved exactly and now belong to `component.internal_execution`.
2. **Bound identity (BVID)** — derived identity of a canonical entity when a component is mounted in a composition. A BVID is composition + mount + canonical VID. It never replaces or mutates the CVID.
3. **Runtime identity (RID)** — ephemeral/live identities such as `intent_id`, `intent_version`, `slice_id`, `action_id`, `correlation_id`, order IDs and provider event IDs. Runtime identity points back to a bound/canonical context but is not architecture identity.

Canonical example:

```text
cvid://component.internal_execution/5.0.8.1.2
```

The same Command Commit Guard mounted in Volarb:

```text
bvid://composition.volarb/mount.volarb.execution.main/5.0.8.1.2
```

A future strategy can mount the same canonical component and obtain a different BVID without changing `[5,0,8,1,2]`.

## Components own canonical identities

`component.internal_execution` owns the canonical `[5,0,...]` namespace. The leading legacy code `5` is preserved to avoid a destructive renumbering; its semantics are now **Internal Execution component namespace**, not "Box 5 owned by Volarb."

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
    component.internal_execution
    |
    | Broker Execution Port
    v
mount.volarb.execution.main.broker.primary
    provider.dhan
```

The strategy owns the desired economic state. Internal Execution owns how to converge toward that state under its margin, slicing, optimal-execution, interrupt, integrity and recovery rules. The provider owns mechanical broker translation/transport/observation only.

## Authoritative files

- Component catalog: `architecture/registries/component-registry.json`
- Composition catalog: `architecture/registries/composition-registry.json`
- Internal Execution manifest: `architecture/components/internal-execution/manifest.json`
- Internal Execution canonical VID registry: `architecture/components/internal-execution/vector-id-registry.json`
- Dhan provider manifest: `architecture/providers/dhan/manifest.json`
- Volarb composition: `architecture/strategies/volarb/composition.json`
- Identity helpers: `architecture/lib/identity.mjs`
- Consistency validator: `architecture/validate.mjs`

The historical `docs/workflows/vector-id-registry.json` remains a compatibility/assembled view. It mirrors the canonical Internal Execution entries but is no longer the ownership authority for `[5,0,...]`.

## Non-destructive migration rule

No existing Internal Execution VID is renumbered or reused. Existing cross-box edge VIDs remain as compatibility references, but their architectural ownership is transferred to the explicit Volarb composition bindings.

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
