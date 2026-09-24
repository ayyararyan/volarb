# Canonical Agent Decision Algorithm

This file is the **only control plane** for the butterfly workflow.

Do not open all references at once. Start here, evaluate one gate at a time, and load only the reference required for the current gate. **The first terminal gate wins.** A later attractive metric, high theta, or prettier candidate must never override an earlier hard failure.

## 0. Determine the branch

Set exactly one branch:

- `OPEN_INTRADAY`: live butterfly, before 14:45 IST, next intended review/exit is before market close.
- `OPEN_CARRY_GATE`: live butterfly, 14:45 IST or later while the option market is actionable, or any earlier review explicitly considering an overnight hold.
- `LOCKED_OVERNIGHT`: live butterfly after the home option market has closed.
- `CANDIDATE_INTRADAY`: no live butterfly; proposed trade will be closed the same session.
- `CANDIDATE_OVERNIGHT`: no live butterfly; proposed trade crosses the home-market close.

If Dhan shows no open position, do not infer one from an old screenshot or prior conversation state.

## 1. Acquire only the minimum state needed

Always establish:

1. IST clock/session.
2. Symbol and exact expiry.
3. Open position truth from Dhan when connected.
4. One coherent relevant-expiry option-chain snapshot.
5. Actual four-leg liquidity for an existing or proposed iron fly.
6. Intended holding horizon and next actionable exit.

Use `references/dhan-mcp-workflow.md` for Dhan acquisition and `references/exchange-surface-workflow.md` only when exchange validation/fallback is needed.

If essential position truth cannot be reconstructed after one fallback attempt, stop rather than inventing geometry or fills.

## 2. Data-health gate

Run the surface diagnostics from `references/analysis-framework.md` and `scripts/analyze_option_surface.py` when structured chain data permit.

Classify `HEALTHY / DEGRADED / STALE / INVALID`.

- Candidate branch: `INVALID` -> **NO TRADE**. `STALE` -> no executable candidate; at most a clearly labelled watchlist.
- Existing position: do not manufacture surface probabilities from `INVALID/STALE` data. Continue only if actual position and executable leg data remain reliable enough for risk management; otherwise stop the analysis as data-limited.

If this gate terminates, do not evaluate theta, regime, recentering, or optimization.

## 3. Post-close terminal gate

If branch = `LOCKED_OVERNIGHT` -> **LOCKED OVERNIGHT**.

Do not issue a fresh CARRY/HOLD/RECENTRE/SQUARE OFF decision after the local market is already non-actionable. Build only the next-open contingency map.

Stop.

## 4. Overnight branch: classify regime first

Run this step only for `OPEN_CARRY_GATE` or `CANDIDATE_OVERNIGHT`.

Read `references/regime-engine.md`, build the regime snapshot, and run:

```bash
python scripts/classify_market_regime.py --input regime_snapshot.json --pretty
```

Use exactly one state:

`CALM_CARRY / TRANSITION / LATENT_JUMP_RISK / ACTIVE_STRESS / UNKNOWN`

For a **new entry, recenter, or rotation**:

- `LATENT_JUMP_RISK` -> **NO TRADE** / do not recenter overnight.
- `ACTIVE_STRESS` -> **NO TRADE** / do not recenter overnight.
- `UNKNOWN` -> **NO TRADE** / do not recenter overnight.
- `TRANSITION` -> continue, but use the tighter overnight thresholds.
- `CALM_CARRY` -> continue.

For an **existing position**, severe regimes do not automatically force an exit. They tighten the thresholds supplied to the overnight gate. Continue to Step 5.

## 5. Overnight branch: run the carry gates in fixed order

Read `references/overnight-carry-gate.md` and run `scripts/evaluate_overnight_carry.py` when inputs permit.

Evaluate in this exact order:

1. **Recent-gap gate**
   - New entry/recenter/rotation with <15 usable opens -> terminal **NO TRADE**.
   - New entry/recenter/rotation with p90 absolute gap >= current-spot-to-nearest-break-even buffer -> terminal **NO TRADE**.
   - New entry/recenter/rotation with expected gap-gamma drag >= same-state next-open harvest -> terminal **NO TRADE**.
   - Existing position: a hard failure -> **SQUARE OFF** while the market is actionable; warnings alone continue.

2. **Broker/RMS gate**
   - New entry/recenter/rotation requires `PASS`; `UNKNOWN/WARN/FAIL` -> terminal **NO TRADE**.
   - Existing position with an explicit unresolved auto-squareoff/RMS warning or `FAIL` -> **SQUARE OFF**.
   - Existing `UNKNOWN` is degraded, not an automatic pass; continue only with that uncertainty explicit internally.

3. **Event-latency gate**
   - High/critical event with no full next-open repricing -> terminal **NO TRADE** for new/recenter/rotation; **SQUARE OFF** for an existing actionable carry.
   - High/critical event with `OCR_1_5 < 1.0` -> same terminal action.
   - Medium event with `OCR_1_5 < 0.5` -> same terminal action.

4. **Joint gap/IV stress gate**
   - Full-reprice +/-1.0, +/-1.5 and +/-2.0 ATM-straddle spot gaps with IV expansion.
   - New/recenter/rotation with `OCR_1_5 < 0.5` -> terminal **NO TRADE**.
   - Existing position with a failed overnight stress gate -> **SQUARE OFF**.
   - Apply regime-adjusted OCR and break-even-buffer thresholds from `regime-engine.md`.

If any gate terminates, stop. Do not proceed to theta or recenter optimization.

## 6. Hard event / tail / liquidity override

Evaluate current event/path state, threatened break-even/wing, actual-leg execution quality, and surface instability.

If a credible shock, materially threatened wing/break-even, or unusable execution makes the short-gamma state unacceptable:

- existing position -> **SQUARE OFF**;
- candidate -> **NO TRADE**.

Stop.

## 7. Expiry-exit gate for existing positions

Run only when <=2 trading sessions remain, <=36 calendar hours remain, or it is expiry day.

Read `references/expiry-exit-algorithm.md` and run:

```bash
python scripts/evaluate_expiry_exit.py --input exit_snapshot.json --pretty
```

Terminal rules include:

- expiry day at/after 14:45 IST -> **SQUARE OFF** unless the user explicitly chose a settlement-hold policy;
- `P* <= 0` -> **SQUARE OFF** unless a valid recenter policy clearly supersedes it;
- `DHS >= 85%` -> default **SQUARE OFF**;
- `B/S < 0.5` while forward is moving toward the nearest break-even -> **SQUARE OFF**;
- remaining harvest no longer compensates for gamma/path risk -> **SQUARE OFF**;
- material IV/straddle expansion plus adverse centre/wing migration -> **SQUARE OFF**.

If the expiry-exit engine says exit, stop.

## 8. Recenter gate for existing positions

Only evaluate RECENTRE if the current body/path alignment has materially changed and Steps 2-7 did not terminate.

Read `references/recentre-engine.md` and run:

```bash
python scripts/evaluate_recentre.py --input recenter_snapshot.json --pretty
```

RECENTRE only if all are true:

1. range-bound/choppy thesis survives;
2. data and execution are adequate;
3. new body materially improves alignment and/or tail/path risk;
4. close+reopen friction is acceptable;
5. enough time remains to re-harvest carry;
6. event/path state is not worse;
7. if the recenter crosses market close, the overnight gates for the **new** structure also pass.

If the recenter gate passes -> **RECENTRE** and stop.

Otherwise continue.

## 9. Candidate optimization gate

Run only for candidate branches after all earlier hard gates pass.

Read `references/butterfly-optimizer.md` and run:

```bash
python scripts/optimize_butterflies.py --input snapshot.json --pretty
```

Rules:

- wide symmetric iron butterflies by default;
- use actual four-leg execution quotes and live Greeks when available;
- remove hard-gate failures before ranking;
- remove Pareto-dominated candidates;
- rank survivors on theta efficiency, low carry burden, low combined tail/path risk, and usable liquidity.

If zero candidates survive -> **NO TRADE**.

Otherwise return up to three ranked candidates and stop.

## 10. Default action if no earlier gate terminated

- `OPEN_INTRADAY` -> **HOLD**.
- `OPEN_CARRY_GATE` -> **CARRY**.
- Candidate branch -> ranked candidates from Step 9.

There is no discretionary final "overall judgment" after this step. The controller is the judgment policy.

## 11. Review timing

For HOLD/CARRY, choose the earliest meaningful next review from:

1. next scheduled decision-relevant event;
2. next price-discovery session;
3. expiry-gamma cadence;
4. 14:45 carry gate / market close;
5. material state-change urgency.

Use `references/output-template.md` for exact formatting.

## 12. Persist, then answer

After the final action is fixed:

1. persist the review/trade event using `references/repo-logging.md`;
2. then emit the minimal one-table user-facing answer.

Logging is a side effect and may never change the decision.

---

## Canonical pseudocode

```text
branch = classify_branch(clock, open_position, intended_horizon)
state  = acquire_minimum_state()

if candidate and data_health in {INVALID, STALE}:
    return NO_TRADE

if branch == LOCKED_OVERNIGHT:
    return LOCKED_OVERNIGHT

if branch crosses market close:
    regime = classify_regime()

    if proposed_structure_is_new_or_recentered and regime in {LATENT_JUMP_RISK, ACTIVE_STRESS, UNKNOWN}:
        return NO_TRADE

    for gate in [RECENT_GAP, BROKER_RMS, EVENT_LATENCY, JOINT_GAP_IV_STRESS]:
        result = evaluate(gate)
        if result is terminal:
            return terminal_action_for(branch, result)

if hard_event_tail_or_liquidity_override():
    return SQUARE_OFF if open_position else NO_TRADE

if open_position and near_expiry and expiry_exit_gate_fails():
    return SQUARE_OFF

if open_position and recenter_is_relevant() and recenter_gate_passes():
    return RECENTRE

if not open_position:
    candidates = optimize_survivors()
    return top_3(candidates) if candidates else NO_TRADE

return CARRY if branch == OPEN_CARRY_GATE else HOLD
```

## Conflict rule

If any other reference appears to suggest a different order, **this file controls the order**. Other references define calculations and thresholds; they do not override controller precedence.
