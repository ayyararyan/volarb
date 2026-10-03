# Vector identity — current authority and compatibility

Status: **active identity guide**, compositional identity model v2.0.

The canonical identity rules are in [Compositional Identity](../architecture/compositional-identity.md). This stable path replaces the former v1 guide; its [historical text](../../archive/architecture/internal-execution-era/vector-id-system.md) is preserved, not an alternative authority.

## Ownership

| Identity | Authority | Meaning |
|---|---|---|
| Strategy-local `[0,...]` through `[4,...]` | [Assembled strategy registry](vector-id-registry.json) | Volarb's global contracts and strategy design |
| Canonical `[5,0,...]` | [Execution Engine registry](../../architecture/components/execution-engine/vector-id-registry.json) | Immutable `component.execution_engine` entities, independent of strategy placement |
| Composition mounts and bindings | [Volarb composition](../../architecture/strategies/volarb/composition.json) | Where components are mounted and how their ports connect |
| Dhan provider | [Provider manifest](../../architecture/providers/dhan/manifest.json) | `provider.dhan`, without a Volarb VID |
| Runtime intent/slice/action/order references | [Execution identity contract](execution-engine.md#runtime-execution-identity) | Live objects associated with canonical and bound architecture identities |

The five-integer vector remains `[namespace, instance, layer, type, ordinal]`. Existing values and retired tombstones are immutable. Namespace `5` is not a strategy-owned box. A display-name change must never renumber a VID.

`docs/workflows/vector-id-registry.json` retains the strategy entities and an assembled compatibility mirror of Execution Engine entities. It is not the ownership authority for the execution namespace. `component.internal_execution` and its original directory remain explicitly legacy aliases only.

For changes, update the owning registry/manifest and its graph specification, preserve compatibility mirrors, and run from the repository root:

```sh
node architecture/validate.mjs
node --test architecture/lib/*.test.mjs architecture/*.test.mjs
```
