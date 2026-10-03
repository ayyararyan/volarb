# [5,0,7,0,1] Execution Slicing

Status: **active reusable execution design**. The complete pipeline is not yet implemented; see [current contracts/ports](../../execution-engine/README.md). These rules specify required behavior, not a live trading service.

Execution Slicing is the normal-flow sub-box between Margin Optimization and Optimal Execution.

Its purpose is to decide whether a permitted instrument quantity should be executed as one execution slice or split into several smaller slices.

This is **not** option-strategy leg construction. A strategy leg is an economic instrument decided upstream. An execution slice is a chunk of one permitted instrument quantity.

## Default

The current default is intentionally trivial:

~~~text
slice_count = 1
scheduling_mode = SEQUENTIAL
~~~

Under this specified baseline, the full permitted quantity becomes one slice and is handed to Optimal Execution once. A production Slice Planner has not yet been implemented in this repository.

## [5,0,7,1,1] Slice Planner

The Slice Planner consumes the Execution Ordering Plan and relevant eligible quantities.

It decides:

- number of slices;
- quantity per slice;
- slice order;
- scheduling mode.

It may not:

- violate Margin Optimization ordering constraints;
- increase total permitted quantity;
- change instrument identity or side;
- make ineligible work eligible.

Future implementations may use position size, LOB depth, market impact, fill rate, urgency or other execution variables to choose slices. None of that is fixed yet.

## [5,0,7,7,2] Slice Policy

Current policy:

~~~text
slice_count = 1
scheduling_mode = SEQUENTIAL
~~~

This is a replaceable policy.

Example future case:

~~~text
permitted quantity = 200 lots
slice_count = 5

slice 1 = 40 lots
slice 2 = 40 lots
slice 3 = 40 lots
slice 4 = 40 lots
slice 5 = 40 lots
~~~

The exact split need not be equal in future implementations.

## [5,0,7,7,1] Execution Slice Plan

Conceptually:

~~~text
intent_id
intent_version
ordering_mode
ordering_metadata

slice_count
scheduling_mode

slices:
  - slice_id
    slice_index
    instrument
    side
    quantity
    status
~~~

The plan carries upstream ordering constraints forward.

## [5,0,7,2,1] Slice Progress State

Tracks authoritative slice progress:

~~~text
PENDING
ACTIVE
PARTIALLY_FILLED
COMPLETE
CANCELLED
SUPERSEDED
RECOVERY_REQUIRED
~~~

Under the current default SEQUENTIAL policy, slice k+1 is not released until slice k is complete or otherwise authoritatively resolved.

## Optimal Execution relationship

Optimal Execution operates on the currently released execution slice.

Conceptually:

~~~text
Margin Optimization
        |
Execution Ordering Plan
        |
Execution Slicing
        |
slice 1 -> Optimal Execution -> reconcile
        |
slice 2 -> Optimal Execution -> reconcile
        |
...
~~~

If slice_count=1, this reduces to the current simple workflow.

Future slice optimization may alter how slices are formed or scheduled without changing the Optimal Execution algorithm interface.
