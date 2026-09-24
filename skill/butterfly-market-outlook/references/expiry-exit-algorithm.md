# Expiry Exit Algorithm

Use this reference for every open butterfly review when the position is close to expiry. The objective is to decide whether the **remaining state-conditioned decay harvest** is still worth the short-gamma/path risk. Keep these diagnostics internal unless the user explicitly asks for the exit logic.

## Activation

Activate the expiry-exit layer when either condition is true:

- the butterfly expires within **2 trading sessions**; or
- less than roughly **36 calendar hours** remain to settlement.

On expiry day, always activate it regardless of distance from the body.

This layer supplements the normal live-surface, news, liquidity and geometry workflow. It never replaces them. If the proposed hold crosses market close, run the regime-aware overnight carry gate **before** treating remaining theta as harvestable.

## Required inputs

Prefer live Dhan position/account data and the current full option surface. Derive or collect:

- lower wing, centre/body and upper wing;
- lot size and quantity ratio;
- entry net credit for a short iron butterfly, or equivalent long-fly economics for non-standard structures;
- current executable close cost using bid/ask-aware leg marks;
- current spot and parity-consistent forward;
- current ATM straddle for the expiry;
- current net delta, gamma and theta for the whole position;
- expiry break-evens;
- option-implied median/mode and threatened-wing probabilities;
- current and recent stable ATM straddle/IV when available;
- time remaining to expiry and current IST time;
- liquidity/spread quality at the actual legs.

If exact Greeks or executable marks are unavailable, apply the qualitative gates and reduce confidence rather than inventing them.

## Core quantities

For a standard symmetric **short iron butterfly** with entry credit `C`, wing width `W`, body strike `K`, executable current close cost `M`, and parity-implied forward `F`:

- structural maximum profit per point = `C`;
- maximum loss per point = `W - C`;
- bankable current profit per point = `P = C - M`;
- lower break-even = `K - C`;
- upper break-even = `K + C`.

Keep the traditional `P/C` metric only as a secondary descriptive number. **Do not use a fixed percentage of original structural maximum profit as the primary exit trigger near expiry.** As the forward drifts away from the body, the profit economically available from simply harvesting time decay changes materially.

### Dynamic state-conditioned harvest

Use the parity-implied forward as the primary state anchor. For a symmetric short iron butterfly, the expiry intrinsic liability if the current forward were to remain near its current level is:

`I(F) = min(abs(F - K), W)`

Define the **no-move expiry profit**:

`P* = C - I(F)`

This is deliberately state-conditioned. It is **not** the true maximum profit still possible: the underlying could later return to the body and make the original structural maximum attainable again. `P*` answers a different and more useful exit question: **what profit would this fly produce at expiry if the market stayed around the level currently implied by the forward?**

Define **Dynamic Harvest Saturation (DHS)** when `P* > 0`:

`DHS = P / P*`

Interpret it as the fraction of the presently available no-move expiry profit already bankable now.

Define **Remaining Static Harvest (RSH)**:

`RSH = M - I(F)`

Equivalently, when `P* > 0`, `RSH = P* - P`.

`RSH` is the decay/extrinsic reward still available if the forward stays approximately where it is. This is the quantity that should be compared with gamma/path risk.

If `P* <= 0`, do not force a DHS percentage. A no-move expiry is already at or beyond the profitable tent; treat that as an exit-level state unless another explicit adjustment policy applies.

### Dynamic saturation zones

Use these as defaults, not magical constants:

- **DHS < 70%:** no profit-saturation exit by itself;
- **70-80%:** active monitoring; compare RSH explicitly with gamma/path risk;
- **80-85%:** strong exit zone; continue only when the fly remains exceptionally well aligned and RSH is still large relative to plausible short-horizon gamma loss;
- **DHS >= 85%:** default to **SQUARE OFF** unless the user has explicitly chosen a more aggressive expiry-harvest policy and all risk gates remain unusually benign.

The 80-85% zone is intentionally based on the **state-conditioned** profit ceiling, not the original maximum credit.

### Break-even buffer

Let:

- `B = distance from current forward to nearest break-even`;
- `S = current ATM straddle`.

Use `B / S` as the primary near-expiry safety ratio.

Interpretation:

- `B/S >= 1.0`: comfortable buffer relative to currently priced expiry movement;
- `0.5 <= B/S < 1.0`: tighter buffer; increase review frequency;
- `B/S < 0.5`: ordinary implied movement can consume the remaining safety margin; treat as an exit-level warning, especially when forward is moving toward that break-even.

Do not treat these cutoffs as support/resistance. They are risk-budget thresholds.

### Theta-gamma and remaining-harvest stress

Use the position-level local approximation:

`dPi ~= Delta*dS + 0.5*Gamma*(dS^2) + Theta*dt`

For short-gamma butterflies, stress at minimum:

- `dS = +/- 0.5 * ATM straddle`;
- `dS = +/- 1.0 * ATM straddle`.

Compute the worse directional P&L from delta+gamma and compare it with:

- **RSH**, the remaining state-conditioned decay reward;
- expected theta harvest to the next review / intended exit;
- current accumulated profit.

Define internally:

- `gamma_stress_0_5 = worst loss under +/-0.5S from delta+gamma`;
- `gamma_stress_1_0 = worst loss under +/-1.0S from delta+gamma`;
- `theta_to_next_review = positive theta expected over the planned review interval`;
- `HGR_0_5 = RSH / gamma_stress_0_5` when the denominator is positive;
- `HGR_1_0 = RSH / gamma_stress_1_0` when the denominator is positive.

Use `HGR_0_5` as a compact reward-versus-convexity diagnostic:

- `> 1.5`: remaining harvest is still substantial relative to local gamma stress;
- `1.0-1.5`: monitor tightly;
- `0.5-1.0`: exit bias, especially when DHS is already >=70%;
- `< 0.5`: strong exit bias.

Do not rely on a single ratio mechanically. The decision worsens when gamma stress is large **and** the distribution is migrating away from the body, skew is steepening toward the threatened wing, volatility is expanding, or directional follow-through persists.

## Decision gates

Evaluate these gates in order. A later HOLD condition cannot override a hard risk exit.

### Gate 0 - overnight broker/event feasibility

Before knowingly carrying an expiry-eve fly across market close, apply `overnight-carry-gate.md`. A broker/RMS warning, unvalidated broker feasibility for a new expiry-eve position, or failed next-open joint gap/IV stress blocks carry regardless of headline theta.

### Gate 1 - hard event / market-risk override

Choose **SQUARE OFF** if a new credible event, price-discovery shock, liquidity deterioration or live surface shift makes the normal expiry distribution unreliable or threatens a wing/break-even materially.

This gate overrides harvest logic. Do not stay merely because theta is high.

### Gate 2 - state-conditioned harvest gate

Use DHS and RSH rather than a fixed percentage of original maximum profit:

- `DHS >= 85%`: default **SQUARE OFF**;
- `80% <= DHS < 85%`: strong exit zone; HOLD only when centre alignment is excellent, RSH remains large versus gamma stress, volatility is not expanding and no directional follow-through is present;
- `70% <= DHS < 80%`: monitor closely and compare RSH with 0.5-straddle gamma stress;
- `DHS < 70%`: this gate alone does not require exit.

If `P* <= 0`, choose **SQUARE OFF** unless an explicit, realistically executable recentering policy supersedes it.

### Gate 3 - break-even buffer gate

- If `B/S < 0.5` and forward is moving toward the nearest break-even, choose **SQUARE OFF**.
- If `0.5 <= B/S < 0.75`, require frequent re-evaluation and strong centre alignment to HOLD.
- If `B/S >= 0.75`, this gate alone does not require an exit.

If the range-bound thesis remains intact but the distribution centre has shifted materially and there is still enough time/liquidity to reposition, **RECENTRE** may be preferable before expiry day. Do not use RECENTRE merely to avoid taking a loss.

### Gate 4 - remaining harvest versus gamma/path-risk gate

Choose **SQUARE OFF** when the marginal reward still available is no longer attractive relative to plausible short-horizon gamma/path loss. Evidence includes any combination of:

- DHS is already >=70% and 0.5-straddle adverse delta+gamma stress is comparable to or larger than RSH;
- DHS is >=80% and `HGR_0_5 <= 1.5`;
- `HGR_0_5 < 0.5` even before the formal harvest ceiling is reached;
- 1.0-straddle adverse stress would surrender a large fraction of accumulated profit;
- net gamma is increasing rapidly while forward/median/mode are no longer aligned with the body;
- directional follow-through is persistent rather than mean-reverting/choppy.

A high theta number is **not** a HOLD signal by itself. Near expiry, high theta and high gamma arrive together. RSH is the relevant reward pool, not headline theta in isolation.

### Gate 5 - volatility-expansion gate

When a recent stable reference is available, treat an approximately **20%+ expansion in the ATM straddle** as material.

Choose **SQUARE OFF** when the straddle/IV expands materially **and** forward is moving away from the body or skew is steepening toward the threatened wing.

Do not exit merely because IV rises while the body remains well aligned and position-level risk stays contained.

### Gate 6 - expiry-day time gate

On expiry day, tighten the process automatically:

- **Open to 12:00 IST:** normal expiry-exit gates; re-check every 30-60 minutes when benign.
- **12:00-13:30 IST:** increase emphasis on live gamma stress and centre migration; typical review interval 20-30 minutes.
- **13:30-14:45 IST:** treat the position as a short-horizon gamma trade; typical review interval 10-20 minutes when still open.
- **At/after 14:45 IST:** default to **SQUARE OFF** for an expiring butterfly. Do not use CARRY on expiry day. Only deviate if the user explicitly instructs a settlement-hold policy and execution/settlement mechanics are fully understood.

The time gate is not a claim that 14:45 is mathematically optimal. It is a default risk-control boundary that prevents the final minutes from dominating the entire trade outcome.

## Distribution-centre cross-check

Use the parity-implied forward for the DHS denominator because it gives the cleanest no-move expiry reference. Then cross-check the option-implied median and mode:

- if forward, median and mode remain clustered near the body, the state-conditioned ceiling is credible as a local harvest reference;
- if median/mode migrate farther toward a threatened break-even than the forward, treat DHS based on the forward as potentially optimistic and tighten the decision;
- if the surface is unstable or multimodal because of an event/jump regime, do not rely on DHS alone.

## RECENTRE restrictions near expiry

Use **RECENTRE** only when all are true:

- the market remains broadly range-bound/choppy rather than persistently directional;
- the distribution centre has moved materially away from the old body;
- the nearest break-even/wing is not already under acute threat;
- the new centre materially improves distribution alignment;
- bid/ask spreads and leg liquidity make the adjustment realistically executable;
- enough time remains for the new fly to earn carry after transaction friction.

On expiry day, RECENTRE should be exceptional rather than routine. As the afternoon progresses, prefer taking the result over repeatedly resetting short gamma.

## HOLD conditions near expiry

HOLD is appropriate only when all material conditions remain acceptable:

- body remains reasonably close to forward / option-implied median / modal region;
- no hard event or tail-risk override is active;
- break-even buffer remains adequate relative to the current straddle;
- DHS has not reached the default harvest ceiling, or the incremental RSH still clearly compensates for gamma risk;
- volatility/skew are not expanding adversely toward a wing;
- liquidity remains usable;
- the next review time is short enough for the current gamma regime.

When HOLD is chosen near expiry, set the next review using the expiry-day time gate rather than a generic long interval.

## Deterministic helper

When the required inputs are available, run:

```bash
python scripts/evaluate_expiry_exit.py --input exit_snapshot.json --pretty
```

Pass `forward` when a parity-consistent forward is available; otherwise the helper falls back to spot. Use the script to compute original-max capture for reference, DHS, RSH, break-even buffer, theta-to-review, local delta/gamma stresses and harvest/gamma ratios. The script is a diagnostic helper, not an autonomous trading rule: combine its flags with the live surface, market regime, news and liquidity before producing the final action.

## Output integration

Do not add a second table or an "exit score" to the user-facing response.

The existing one-row table remains unchanged:

`Decision | Why | Next review`

When the expiry-exit layer materially determines the action, make the `Why` cell name the dominant reason briefly, for example:

- `85% of the current no-move expiry profit is already bankable; remaining harvest is too small for the gamma risk.`
- `Dynamic harvest saturation is 82% and a half-straddle move can erase more than the remaining decay reward.`
- `Only 64% of the current no-move expiry profit is captured; remaining harvest still compensates for local gamma risk.`
