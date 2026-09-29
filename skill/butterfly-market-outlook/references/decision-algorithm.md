# Canonical Agent Decision Algorithm — v2.5

This file is the **only control plane** for the butterfly workflow.

Start here, evaluate one gate at a time, and load only the reference required for the current gate. **The first terminal gate wins.** A later attractive metric, high theta, or prettier candidate must never override an earlier hard failure.

## 0. Determine the branch

Set exactly one branch:

- `OPEN_INTRADAY`: live butterfly, before 14:45 IST, next intended review/exit is before market close.
- `OPEN_CARRY_GATE`: live butterfly, 14:45 IST or later while actionable, or any earlier review explicitly considering overnight hold.
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
7. One normalized `market-news-signal-filter` packet for the current decision horizon whenever event/news state can affect the trade.
8. For intraday candidate work, a fresh approximately five-minute HF price/futures block for the `intraday-realized-volatility-forecast` child skill.

Read `references/news-signal-integration.md` before interpreting current news. Invoke the news child skill once and reuse the packet.

Use `references/dhan-mcp-workflow.md` for Dhan acquisition and `references/exchange-surface-workflow.md` only when exchange validation/fallback is needed.

If essential position truth cannot be reconstructed after one fallback attempt, stop rather than inventing geometry or fills.

## 2. Data-health gate

Run the surface diagnostics from `references/analysis-framework.md` and `scripts/analyze_option_surface.py` when structured chain data permit.

Classify `HEALTHY / DEGRADED / STALE / INVALID`.

- Candidate branch: `INVALID` -> **NO TRADE**. `STALE` -> no executable candidate.
- Existing position: continue only if actual position/executable leg data remain reliable enough for risk management.

If this gate terminates, do not evaluate HF RV, theta, regime, recentering, or optimization.

## 3. Post-close terminal gate

If branch = `LOCKED_OVERNIGHT` -> **LOCKED_OVERNIGHT**.

Do not issue a fresh executable decision after the local market is closed. Stop.

## 4. Intraday HF realized-volatility / drift gate

Run this step for `CANDIDATE_INTRADAY`. Also run it for `OPEN_INTRADAY` on scheduled reviews when a fresh HF block is available, and especially after material path/surface change.

Invoke `intraday-realized-volatility-forecast` for the exact next-review horizon, normally 15-30 minutes.

The child skill must:

- observe a fresh approximately five-minute HF futures/price block;
- estimate fast/slow local continuous variance;
- separate recent jump pressure from continuous volatility;
- diagnose directional/centre drift from price, futures, parity forward and RND median migration; treat a discrete RND-mode bucket shift as corroborative only, never as an independent hard drift trigger;
- apply the same normalized near-horizon news/event packet;
- compare jump-adjusted physical RV with same-horizon implied variance only after the physical forecast is built.

### New intraday candidate

Require `short_gamma_state = FAVOURABLE` with actionable HF data.

- `FAVOURABLE` -> continue.
- `MARGINAL` -> **NO TRADE**.
- `UNFAVOURABLE` -> **NO TRADE**.
- `INSUFFICIENT_DATA` -> **NO TRADE**.

Session OHLC or sparse snapshots alone may never pass this gate.

### Existing intraday position

- medium/high-confidence `UNFAVOURABLE` -> **SQUARE OFF**;
- low-confidence `UNFAVOURABLE` -> this gate alone does **not** force an exit; continue to the remaining risk gates, without treating low confidence as evidence of safety;
- `MARGINAL` -> warning, continue to later risk/expiry/recenter gates and shorten next review;
- `INSUFFICIENT_DATA` -> degraded evidence only; do not force an exit solely from missing HF data;
- `FAVOURABLE` -> continue.

When available, pass `upper_forecast_sigma_move_points` to candidate width/stress construction as the real-world next-review move scale.

If this gate terminates, do not let high theta override it.

### How drift changes an exit check

The child maps `HIGH` drift to `UNFAVOURABLE` when its HF data and IV anchor are available. Pass the child's `short_gamma_state` and `confidence` as the controller's `intraday_rv_state` and `intraday_rv_confidence`. The exact drift diagnostics and thresholds are in the [RV methodology](../../intraday-realized-volatility-forecast/references/methodology.md#6-drift--centre-stability).

For `OPEN_INTRADAY`, a medium/high-confidence unfavourable state terminates at `INTRADAY_RV_DRIFT`, before expiry-harvest or recenter evaluation. Current profit, positive theta, being inside expiry break-evens, or a proposed replacement cannot overturn that exit. For example, an otherwise profitable position still receives `SQUARE_OFF` at this gate; no loss or break-even breach is required first.

`MARGINAL`, `FAVOURABLE`, missing HF data, or a low-confidence unfavourable state does not itself establish HOLD. Complete all applicable later gates with validated inputs. The controller consumes normalized evidence, not raw account/market data; its defaults are not proof that omitted checks passed. A marginal state normally means a 10-20 minute next review only if continued holding survives the other checks.

This is a conservative rule-based exit, not a calibrated proof that closing has higher expected P&L. Drift measures absolute market/centre movement, not signed movement relative to the held body: movement back toward the body may initially help the position and still fail the market-wide drift rule. Low drift likewise cannot guarantee profitable holding. The actual-leg Greeks, costs, liquidity and remaining reward belong to the later position-specific checks.

The [personal covenant](../../../docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md) remains stricter than generic branch outputs: intraday only, flat by 15:00 IST, no entry/recenter thereafter. Apply it even when the generic controller changes to `OPEN_CARRY_GATE` at 14:45. Recommendations are for Aryan to execute; this gate neither places orders nor configures monitoring or review reminders.

## 5. Overnight branch: normalize news, then classify regime

Run only for `OPEN_CARRY_GATE` or `CANDIDATE_OVERNIGHT`.

Set `news_filter_required=true`. If the child news packet is `UNAVAILABLE` or `INVALID`, the regime must be `UNKNOWN` for a new overnight structure.

Read `references/regime-engine.md` and run `scripts/classify_market_regime.py`.

Use exactly one state:

`CALM_CARRY / TRANSITION / LATENT_JUMP_RISK / ACTIVE_STRESS / UNKNOWN`

For a new entry/recenter/rotation:

- `LATENT_JUMP_RISK`, `ACTIVE_STRESS`, or `UNKNOWN` -> **NO TRADE**;
- `TRANSITION` -> continue with tighter thresholds;
- `CALM_CARRY` -> continue.

Existing positions continue conservatively to Step 6.

## 6. Overnight branch: run carry gates in fixed order

Read `references/overnight-carry-gate.md` and run `scripts/evaluate_overnight_carry.py`.

Evaluate in this exact order:

1. recent-gap gate;
2. broker/RMS gate;
3. event-latency gate;
4. joint gap/IV stress gate.

Use the existing v2.4 terminal rules and regime-adjusted thresholds. If any gate terminates, stop. Do not proceed to theta or recenter optimization.

## 7. Hard event / tail / liquidity override

Evaluate normalized news state, current path state, threatened break-even/wing, actual-leg execution quality and surface instability.

If a credible shock, materially threatened wing/break-even, or unusable execution makes the short-gamma state unacceptable:

- existing position -> **SQUARE OFF**;
- candidate -> **NO TRADE**.

Stop.

## 8. Expiry-exit gate for existing positions

Run when <=2 trading sessions remain, <=36 calendar hours remain, or it is expiry day.

Read `references/expiry-exit-algorithm.md` and run `scripts/evaluate_expiry_exit.py`.

Terminal rules include:

- expiry day at/after 14:45 IST -> **SQUARE OFF** unless explicit settlement-hold policy;
- `P* <= 0` -> **SQUARE OFF** unless a valid recenter clearly supersedes it;
- `DHS >= 85%` -> default **SQUARE OFF**;
- `B/S < 0.5` while forward moves toward the nearest break-even -> **SQUARE OFF**;
- remaining harvest no longer compensates for gamma/path risk -> **SQUARE OFF**;
- material IV/straddle expansion plus adverse centre/wing migration -> **SQUARE OFF**.

If exit is terminal, stop.

## 9. Recenter gate for existing positions

Only evaluate if body/path alignment materially changed and Steps 2-8 did not terminate.

Read `references/recentre-engine.md` and run `scripts/evaluate_recentre.py`.

RECENTRE only if all existing recenter conditions pass. For intraday recentering, the new centre must also remain consistent with the HF RV/drift state; do not recenter into `UNFAVOURABLE`/insufficient short-gamma conditions.

If strategic recenter conditions pass, also require a fresh margin packet covering the **entire close/reopen transition**, not only the final new fly. Set `recenter_margin_check` with scope `RECENTRE` only from verified transition evidence. The current MCP preflight is ENTRY_ONLY and cannot produce this packet. Without transition verification, block RECENTRE, retain a warning and assess exit/hold independently; do not force HOLD against an earlier exit gate. After verified closure, evaluate any permitted re-entry as a new candidate.

## 10. Candidate optimization gate

Run only for candidate branches after all earlier hard gates pass.

Read `references/butterfly-optimizer.md` and run `scripts/optimize_butterflies.py`.

For intraday candidates:

- the HF RV gate has already passed;
- use actual four-leg quotes/Greeks;
- use `upper_forecast_sigma_move_points` as the real-world next-review move scale when available;
- theta efficiency ranks only among candidates that survived the RV/drift/path gates.

If zero candidates survive -> **NO TRADE**.

Before returning executable candidates, read `references/margin-affordability.md` and run the Dhan preflight for each exact-sized finalist. Retain only fresh PASS packets; never reuse one fly's margin for another geometry or lot count. Bind packets to unique candidate IDs in `candidate_margin_checks`, supply `candidate_ids` in ranking order, and set `candidate_count` to the screened count. The controller returns only `margin_eligible_candidate_ids`. No fresh passes -> **NO TRADE**, terminal gate `MARGIN_AFFORDABILITY`.

Otherwise return up to three margin-verified ranked candidates and stop. Missing reserve policy permits an indicative research result only, not an executable candidate.

## 11. Default action

- `OPEN_INTRADAY` -> **HOLD**.
- `OPEN_CARRY_GATE` -> **CARRY**.
- Candidate branch -> ranked candidates from Step 10.

There is no discretionary final overall judgment.

## 12. Review timing

For HOLD/CARRY choose the earliest meaningful next review from event timing, expiry gamma cadence, 14:45 carry gate/close and state-change urgency.

A `MARGINAL` intraday RV state should normally shorten review cadence to about 10-20 minutes when actionable.

## 13. Persist, then answer

After the action is fixed:

1. persist the review/trade event using `references/repo-logging.md`, including the compact HF RV packet when it was used;
2. emit the minimal user-facing table.

Logging may never alter the decision.

---

## Canonical pseudocode

```text
branch = classify_branch(clock, open_position, intended_horizon)
state  = acquire_minimum_state()
news   = normalize_market_news_signal_filter_once()

if candidate and data_health in {INVALID, STALE}:
    return NO_TRADE

if branch == LOCKED_OVERNIGHT:
    return LOCKED_OVERNIGHT

if branch in {CANDIDATE_INTRADAY, OPEN_INTRADAY}:
    rv = intraday_realized_volatility_forecast(hf_5m_block, news)
    if candidate and rv.short_gamma_state != FAVOURABLE:
        return NO_TRADE
    if open_position and rv.short_gamma_state == UNFAVOURABLE and rv.confidence in {medium, high}:
        return SQUARE_OFF

if branch crosses market close:
    regime = classify_regime(news)
    run overnight gates in fixed order

if hard_event_tail_or_liquidity_override():
    return SQUARE_OFF if open_position else NO_TRADE

if open_position and near_expiry and expiry_exit_gate_fails():
    return SQUARE_OFF

if open_position and recenter_is_relevant() and recenter_gate_passes() and transition_margin_passes():
    return RECENTRE

if not open_position:
    candidates = optimize_survivors(real_world_move_scale=rv.upper_forecast_sigma_move_points)
    candidates = keep_fresh_margin_passes(candidates)
    return top_3(candidates) if candidates else NO_TRADE

return CARRY if branch == OPEN_CARRY_GATE else HOLD
```

## Conflict rule

If any other reference suggests a different order, **this file controls the order**.

Exact candidate binding: supply `candidate_specs[id]` with exactly `symbol`, `expiry`, `lower`, `center`, `upper`, `lots`; it must equal the MCP packet's `candidate` object. A missing or mismatched binding is not eligible, even if the packet says PASS.
