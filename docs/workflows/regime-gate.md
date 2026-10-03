# [1,0,0,0,0] Regime Gate

This graph owns the **days/weeks** decision horizon.

## Graph

```mermaid
flowchart TD
    A["[1,0,1,1,1] Start / scheduled regime review"]
    B["[1,0,2,1,1] Collect regime-relevant market context"]
    C["[1,0,3,1,1] Multi-day Regime Gate"]
    D["[1,0,4,7,1] REGIME_FAVORABLE"]
    E["[1,0,5,1,1] Hand off to Underlying Allocation"]
    F["[1,0,4,2,1] NO-NEW-SHORT-GAMMA"]
    G["[1,0,5,3,1] Regime Recheck Scheduler"]
    H["[1,0,6,2,1] Wait until next multi-day review condition"]
    I["[1,0,4,2,2] Fail-safe: do not deploy new short gamma"]

    A -->|"[1,0,1,4,1]"| B
    B -->|"[1,0,2,4,1]"| C
    C -->|"[1,0,3,4,1] FAVORABLE"| D
    D -->|"[1,0,4,4,1]"| E
    C -->|"[1,0,3,4,2] UNFAVORABLE"| F
    F -->|"[1,0,4,4,2]"| G
    G -->|"[1,0,5,4,1]"| H
    H -->|"[1,0,6,4,1]"| B
    C -->|"[1,0,3,4,3] UNCERTAIN / INSUFFICIENT"| I
    I -->|"[1,0,4,4,3]"| G
```

## Established decisions

- This is a persistent multi-day / multi-week regime, not an intraday regime.
- A favorable regime permits consideration of short gamma; it does not force a trade.
- Unfavorable or uncertain prohibits new short-gamma deployment.
- `[1,0,5,3,1]` decides when enough new information may justify another regime review.
- Recheck methodology may later be time-based, event/state-change based, or hybrid.
- Underlying Allocation is entered only after `[1,0,4,7,1] REGIME_FAVORABLE`.

## Output contract

```text
[1,0,4,7,1] RegimeDecision / REGIME_FAVORABLE
  state = FAVORABLE | UNFAVORABLE | UNCERTAIN
  assessed_at = ...
  valid_until / next_review_condition = ...
  reasons = ...        # future
  confidence = ...     # future
```

## Still TBD

- exact regime model and variables;
- calibration and validation;
- precise recheck rule;
- what can invalidate a favorable regime before scheduled review;
- whether regime later receives underlying/expiry-specific overlays.
