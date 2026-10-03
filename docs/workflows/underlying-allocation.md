# [2,0,0,0,0] Underlying Allocation

Status: **active Volarb strategy design**, not a deployed autonomous workflow. See [workflow ownership](README.md) for the current human-executed controller and governing covenant; design schedulers and broader strategy choices do not authorize orders or monitoring.

This graph owns the **intraday** portfolio-selection horizon after Regime Gate has emitted a favorable regime.

## Graph

```mermaid
flowchart TD
    A["[2,0,1,7,1] REGIME_FAVORABLE input"]
    B["[2,0,2,1,1] Read normalized market data + account/capital state"]
    C["[2,0,3,1,1] Evaluate NIFTY / BANKNIFTY / SENSEX"]
    D["[2,0,4,1,1] Apply capital + margin feasibility constraints"]
    E{"[2,0,5,1,1] Selected set S empty?"}
    F["[2,0,6,2,1] INTRADAY OPPORTUNITY WAIT"]
    G["[2,0,7,3,1] Intraday Opportunity Recheck Scheduler"]
    H["[2,0,8,2,1] Wait until next intraday scan"]
    I["[2,0,6,7,1] Selected set S"]
    J["[2,0,7,1,1] Portfolio Capital Allocator"]
    K["[2,0,8,9,1] Assign W_X to every X in S"]
    L["[2,0,9,7,1] Create DailyUnderlyingCommitment"]
    M["[2,0,10,9,1] Reserve each W_X"]
    N{"[2,0,11,1,1] For each X in S"}
    O["[2,0,12,1,1] Launch Trade Selection X"]

    A -->|"[2,0,1,4,1]"| B
    B -->|"[2,0,2,4,1]"| C
    C -->|"[2,0,3,4,1]"| D
    D -->|"[2,0,4,4,1]"| E
    E -->|"[2,0,5,4,1] YES"| F
    F -->|"[2,0,6,4,1]"| G
    G -->|"[2,0,7,4,1]"| H
    H -->|"[2,0,8,4,1]"| B
    E -->|"[2,0,5,4,2] NO"| I
    I -->|"[2,0,6,4,2]"| J
    J -->|"[2,0,7,4,2]"| K
    K -->|"[2,0,8,4,2]"| L
    L -->|"[2,0,9,4,1]"| M
    M -->|"[2,0,10,4,1]"| N
    N -->|"[2,0,11,4,1]"| O
```

## Established decisions

- Underlying Allocation is reached only when Regime Gate is favorable.
- The selector may output any subset of `{NIFTY, BANKNIFTY, SENSEX}`, including all three or none.
- Capital can shrink the feasible instrument universe.
- An empty set stays in Underlying Allocation and uses `[2,0,7,3,1]`; it does not automatically return to Regime Gate.
- Once X is selected, it becomes a durable daily commitment.
- `W_X` is reserved for Graph X and cannot be opportunistically consumed by another graph while X waits.
- Multiple selected underlyings may run concurrently.
- Shared capital may not be double-counted.

## Outputs

```text
[2,0,6,7,1] DailySelection
  selected_set S = {X1, X2, ...}

[2,0,9,7,1] DailyUnderlyingCommitment
  underlying = X
  capital_budget = W_X
  state = SELECTED_AND_RESERVED
```

## Still TBD

- cross-index attractiveness logic;
- objective/rule for allocating total deployable capital into W_X;
- exact intraday recheck cadence;
- revocation conditions for a daily underlying commitment;
- end-of-session expiry behavior;
- exceptional-event force invalidation.
