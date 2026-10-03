# [5,0,5,5,1] Passive Chase

**Status:** current default Optimal Execution algorithm.

Passive Chase is a deliberately simple broker-neutral execution plug-in behind `[5,0,4,6,1] Execution Algorithm Port`.

It consumes only the state exposed by Optimal Execution. It does not reason about strategy structure, hedge relationships, margin sequencing, or why an instrument is being traded. Passive Chase receives only the work released by Ordering Constraint Enforcer. In ORDERED mode it cannot reorder, skip, or select a later step. In UNCONSTRAINED mode it may work all released items independently.

## Sequence constraint

Passive Chase is subordinate to the mandatory Execution Ordering Plan produced by Margin Optimization.

If the plan is ORDERED, it can operate only on the currently permitted ordered work released by Ordering Constraint Enforcer.

If the plan is UNCONSTRAINED, it may operate on all released eligible items without any sequencing restriction. The default behavior is to run the same Passive Chase logic independently for each item.

No valid ordering decision means no Passive Chase action.

This rule is algorithm-independent: any future Optimal Execution plug-in must obey ORDERED constraints and may exploit freedom only when the upstream plan is UNCONSTRAINED.

## Slice boundary

Passive Chase operates on execution slices produced by `[5,0,7,0,1] Execution Slicing`.

It does not decide how many slices exist or their sizes.

With the current default slice policy there is one slice, so behavior is identical to executing the full permitted quantity.

If a future Slice Planner creates multiple slices, each released slice receives its own Passive Chase lifecycle.

## Inputs

At each decision point the algorithm receives:

- the current `[5,0,3,7,1] Eligible Execution Work Set`;
- current best bid / best ask and relevant LOB state;
- its own working order state;
- confirmed fills / partial fills;
- remaining slice quantity;
- inherited execution constraints.

### ORDERED mode

Passive Chase follows the supplied precedence exactly and works only currently permitted ordered work.

### UNCONSTRAINED mode

Passive Chase does not invent a sequence. Each released item may be worked independently using the same passive-limit / wait / reprice / fallback logic. Multiple independent items may therefore have simultaneous working orders and independent T/N counters.

## [5,0,5,7,1] Passive Chase Parameters

Two parameters define the passive phase:

```text
T = passive waiting interval between execution evaluations
N = maximum number of passive refresh cycles after initial placement
```

The actual values of `T` and `N` are intentionally TBD.

## Passive quote rule

For a **BUY**:

```text
limit_price = current best bid
```

For a **SELL**:

```text
limit_price = current best ask
```

The passive phase never deliberately crosses the spread.

## [5,0,5,2,1] Passive Chase State

The algorithm maintains only micro-execution state such as:

```text
working_order_reference
remaining_quantity
passive_cycle_count
last_passive_price
last_evaluation_time
```

This state is subordinate to the persistent registry requirement.

## Algorithm

### Initial action

If there is eligible quantity and no working order:

1. read the current LOB;
2. choose the passive touch:
   - BUY -> best bid;
   - SELL -> best ask;
3. place a limit order for the eligible quantity at that price;
4. set the passive-cycle counter to zero;
5. start `[5,0,5,3,1] Passive Reprice Timer`.

### Passive cycle

After waiting `T`:

1. consume authoritative fill/order facts;
2. reduce remaining quantity by confirmed fills;
3. if nothing remains, complete this execution work;
4. refresh the LOB;
5. increment the passive-cycle counter;
6. if the counter is still less than `N`:
   - determine the current passive touch;
   - if the passive touch changed, reprice the remaining order to the new touch;
   - if the passive touch did not change, leave the order resting;
   - wait another `T`;
7. if the counter has reached `N` and quantity still remains, end the passive phase and proceed to market fallback.

Only the unfilled remainder is ever repriced. A passive cycle is consumed even when the best passive quote is unchanged, because another full interval `T` has elapsed without completion.

### Market fallback

If the passive phase is exhausted and confirmed quantity remains:

1. cancel the resting limit order;
2. confirm cancellation or otherwise reconcile authoritative broker state;
3. recompute the exact unfilled remainder;
4. only after the outstanding passive order is known not to be fillable anymore, send a market order for the remaining slice quantity.

If cancellation/reconciliation is ambiguous, the algorithm must **not** immediately submit a market order because that could create a duplicate fill.

The market fallback remains subject to inherited execution constraints and provider mechanical validity.

## Partial fills

Partial fills reduce the remaining slice quantity immediately.

Example:

```text
eligible quantity = 100
limit fill = 35
remaining = 65
```

All subsequent reprice or market actions apply only to the confirmed remaining 65.

## Decision loop

Conceptually:

```text
eligible work
    |
    v
place passive limit at touch
    |
   wait T
    |
filled? ---- yes ---> complete
    |
    no
    |
remaining passive cycles?
    |
   yes
    |
refresh touch
reprice only if touch changed
    |
   wait T
    |
   ...
    |
passive cycles exhausted
    |
cancel + confirm/reconcile
    |
market remaining quantity
    |
authoritative fills
    |
complete when required position effect is realized
```

## Plug-and-play boundary

Passive Chase is only one implementation of the Execution Algorithm Port.

Replacing it with another algorithm must not change:

- Margin Optimization;
- Eligible Execution Work Set;
- Temporal Execution Controller;
- Temporal Execution Decision contract;
- Broker Execution Port;
- broker provider implementations;
- Position Management.

That replacement should require only selecting another algorithm implementation behind `[5,0,4,6,1]`.

## Interrupt preemption

Passive Chase is subordinate to `[5,0,6,0,1] Interrupt Control`.

If an interrupt is accepted for an item or scope currently being worked:

- Passive Chase immediately stops generating new PLACE_LIMIT / REPRICE_LIMIT / PLACE_MARKET decisions for that scope;
- its normal T/N loop is suspended;
- cancellation or flattening is owned by Interrupt Control, not by Passive Chase;
- Passive Chase must not resume merely because emergency broker actions completed;
- normal execution may resume only after the latched interrupt state has been explicitly cleared and fresh eligible work is released again.

This keeps emergency behavior independent of the selected execution algorithm.
