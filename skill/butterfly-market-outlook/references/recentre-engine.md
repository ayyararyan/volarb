# Recenter Engine

Use this layer only for an existing butterfly whose body/distribution alignment has moved materially. It prevents the vague rule "spot moved, so recenter."

Run only after all earlier [controller gates](decision-algorithm.md) survive.
Diagnostics do not authorize RECENTRE: the controller additionally requires fresh
verified full-transition margin evidence with scope `RECENTRE`; entry-only margin
is insufficient. The [personal covenant](https://github.com/ayyararyan/volarb/blob/main/docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md)
requires intraday-only exposure, flat by 15:00 IST and no recenter thereafter.

## Core question

Would closing the old fly and opening a new wide fly create a **materially better risk/carry state after friction**, given the remaining time and current event regime?

## Inputs

Prefer:
- current fly centre, width, break-evens, current close cost and live Greeks;
- current RND mapping (`P(loss)`, wing mass, expected loss, CVaR);
- current real-world path centre and stress scenarios;
- best new candidate from the same live surface;
- total estimated close+open slippage/fees in index points;
- time remaining to expiry;
- event/tail regime and data-health state.

## Diagnostics

Calculate:
- `alignment_gain`: reduction in absolute body-to-path-centre distance, normalized by ATM straddle;
- `tail_risk_reduction`: reduction in combined price-implied/path tail score;
- `carry_after_friction`: new candidate carry-to-horizon minus transaction friction;
- `friction_share`: transaction friction / gross new carry;
- `scenario_edge`: candidate expected scenario P&L minus current expected scenario P&L minus friction, only if real-world probabilities exist;
- `time_sufficiency`: whether enough time remains for the new structure to earn carry.

## Guardrails

Do **not** recenter merely because:
- the current trade is losing;
- spot crossed a round number;
- OI moved;
- a new centre has prettier maximum profit;
- the new fly has higher headline theta but worse path/tail risk.

RECENTRE is favored only when:
- the range-bound/choppy thesis survives;
- data health is adequate;
- the new body is materially better aligned **or** an explicitly supplied real-world scenario comparison shows a material positive edge after friction;
- tail/path risk is not worsened;
- friction does not consume a large share of the harvest unless the net scenario edge remains material after that friction;
- enough time remains to monetize the new structure.

Near expiry, require a larger improvement because gamma and transaction costs dominate quickly. On expiry afternoon, repeated recentering should be exceptional.

## Deterministic helper

Run:

```bash
python scripts/evaluate_recentre.py --input recenter_snapshot.json --pretty
```

The helper returns diagnostics and a gate status. It is not allowed to manufacture real-world expected value from risk-neutral probabilities.
