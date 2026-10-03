# Volarb Vector Identity System (VID) — v1.0

> Historical snapshot, archived 2026-10-03. The ownership rules below are superseded; use the [current compositional identity model](../../../docs/architecture/compositional-identity.md). Original terminology is preserved for provenance.

Every architectural object in the autonomous Volarb workflow must have one immutable **Vector ID (VID)**.

The canonical form is:

```text
VID = [B, I, L, T, N]
```

where:

| Coordinate | Meaning | Rule |
|---|---|---|
| `B` | Top-level module code | `0` master/global, `1` regime, `2` intraday selection, `3` per-underlying, `4` execution/risk, `5` broker-neutral optimal execution |
| `I` | Instance | `0` canonical/template/shared instance; Trade Selection uses `1=NIFTY`, `2=BANKNIFTY`, `3=SENSEX` for instantiated graphs |
| `L` | Logical layer/depth inside the box | `0` for the box root; positive integers for deeper architectural layers |
| `T` | Entity type code | identifies whether the entity is a node, state, scheduler, edge, worker, port, contract, adapter, resource, etc. |
| `N` | Ordinal | stable unique ordinal within the same `[B,I,L,T]` namespace |

## Type codes

| `T` | Entity type |
|---:|---|
| 0 | graph / box / container root |
| 1 | process / action / decision / gate node |
| 2 | state |
| 3 | scheduler / timer |
| 4 | edge / transition / arrow |
| 5 | worker / agent |
| 6 | interface / port |
| 7 | data contract / event / message |
| 8 | adapter / external provider connector |
| 9 | resource / allocation / reservation |

Type codes are reserved globally. New entity classes should receive a new code rather than overloading an existing one.

## Canonical module names

The numeric first coordinate remains immutable, but modules are referred to by semantic names rather than numeric module labels.

## Root IDs

```text
Master / global architecture                     [0,0,0,0,0]
Regime Gate                          [1,0,0,0,0]
Underlying Allocation  [2,0,0,0,0]
Trade Selection            [3,0,0,0,0]
Position Management       [4,0,0,0,0]
Internal Execution        [5,0,0,0,0]
```

## Trade Selection instance convention

Trade Selection is a reusable graph template. Its local architecture is defined with `I=0`.

When instantiated:

```text
NIFTY      I = 1
BANKNIFTY  I = 2
SENSEX     I = 3
```

Example:

```text
Template constrained optimizer   [3,0,5,1,1]
NIFTY constrained optimizer      [3,1,5,1,1]
BANKNIFTY constrained optimizer  [3,2,5,1,1]
SENSEX constrained optimizer     [3,3,5,1,1]
```

The local coordinates remain identical; only the instance coordinate changes.

## Examples

```text
Regime Gate root                         [1,0,0,0,0]
Regime Gate decision                 [1,0,3,1,1]
Regime Gate recheck scheduler    [1,0,5,3,1]
Regime Gate favorable transition        [1,0,3,4,1]

Underlying Allocation capital allocator [2,0,7,1,1]
Underlying Allocation W_X reservation             [2,0,10,9,1]

Trade Selection optimizer template          [3,0,5,1,1]
Trade Selection within-hour scheduler       [3,0,7,3,1]

Position Management margin feasibility port     [4,0,5,6,1]
Position Management broker provider plug-in     [4,0,6,8,1]
```

## Edge convention

Every arrow is an entity and therefore receives its own VID.

For an edge, `T=4`. Its `L` coordinate is anchored to the source node's logical layer.

Example:

```text
Regime Gate -> REGIME_FAVORABLE
edge VID = [1,0,3,4,1]
```

Cross-box transitions belong to the master/global scope `B=0`.

## Parent relationships

The VID gives a stable coordinate, but the graph can be a DAG and may have loops or multiple parents. Therefore the canonical registry also stores explicit `parent_vid`, `source_vid`, and `target_vid` fields where applicable.

Do not try to infer graph topology solely from the numerical vector.

## Immutability rules

1. **Never renumber an existing VID.**
2. **Never reuse a retired VID.** Retired entities remain tombstoned in the registry.
3. A display name may change; its VID does not.
4. Every new box, node, state, scheduler, edge, worker, interface, data contract, adapter, and resource gets a VID before it is added to the architecture.
5. Existing layers are not renumbered if a new decision is inserted later. The graph topology is defined by edges, not by renumbering the vector.
6. IDs are architectural identities, not timestamps.
7. Runtime/session/trade identifiers may be attached separately; they must not replace the architectural VID.

## Human-readable use

Always show the VID alongside the semantic name:

```text
[1,0,3,1,1] Multi-day Regime Gate
[3,1,5,1,1] NIFTY Constrained Structure Optimizer
[4,0,5,6,1] BrokerMarginFeasibilityPort
```

The semantic name explains the object. The VID locates it.

## Registry

The machine-readable registry is maintained at:

`docs/workflows/vector-id-registry.json`

From this point forward, architectural changes should update both:
- the relevant graph document; and
- the central VID registry.


## External provider plug-ins

The VID namespace identifies **Volarb-owned architectural objects**.

Concrete external provider implementations that plug into a numbered Volarb interface are not themselves numbered boxes and do not receive Volarb VIDs.

Examples:
- Dhan execution provider;
- Kotak execution provider;
- ICICI Securities execution provider.

The Volarb-owned interface/port receives a VID. The concrete provider implementation is identified using provider metadata such as a provider key and implementation/version.

This exception prevents broker replacement from changing the core vector architecture.

If provider-independent logic is moved into Volarb itself, that logic must receive a VID.

## Internal Execution correction history

`[5,0,0,0,0]` was initially reserved provisionally as an external Dhan execution layer before its internal architecture was clarified. It is now canonically **Internal Execution**, with layered **Margin Optimization** and **Optimal Execution** sub-boxes.

It is now canonically **Broker-Neutral Optimal Execution Layer**.

This is a correction of the provisional root meaning, not reuse of a retired internal VID.
