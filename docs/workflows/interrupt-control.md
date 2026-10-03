# [5,0,6,0,1] Interrupt Control

Status: **active reusable execution design**. The complete pipeline is not yet implemented; see [current contracts/ports](../../execution-engine/README.md). These rules specify required behavior, not a live trading service.

Interrupt Control is an NVIC-inspired supervisory sub-box inside Execution Engine.

It is **not** part of the normal sequential path:

~~~text
Margin Optimization -> Execution Slicing -> Optimal Execution
~~~

Instead, it sits orthogonally above that path and can preempt all three sub-boxes.

Its purpose is to provide deterministic emergency behavior when an authorized upstream component raises an interrupt.

## Core rule

Any active interrupt has higher priority than normal execution.

When an interrupt is accepted:

1. normal order generation for the affected scope is suspended;
2. the active execution algorithm is preempted;
3. Interrupt Control vectors to the handler associated with the interrupt level;
4. authoritative broker facts are used to confirm what actually happened;
5. the interrupt remains latched until its completion/clear rules are satisfied.

Normal convergence must not silently recreate work that an interrupt cancelled.

## [5,0,6,7,1] Interrupt Directive

An interrupt is a broker-neutral control message.

Conceptually:

~~~text
interrupt_id
level
scope
source
reason
issued_at
target_instruments / target_positions / target_registry_items
~~~

The directive describes **what must be interrupted**, not broker-specific order identifiers.

The exact scope vocabulary may grow later, but the first version supports explicit instrument/position/work scopes plus a global managed scope.

## Interrupt vector table

| Level | Name | Meaning | Normal algorithm used? |
|---|---|---|---|
| L1 | CANCEL_WORK | Cancel all currently unfilled/working orders in scope and suppress new work in that scope | No |
| L2 | FLATTEN_SCOPE | Cancel/reconcile working orders in scope, then immediately flatten confirmed positions in that scope with market actions | No |
| L3 | FLATTEN_ALL | Highest priority: cancel/reconcile all controlled working orders, then immediately flatten all controlled confirmed positions with market actions | No |

Higher numeric level means higher priority.

These are the first interrupt levels. More levels may be added later without changing the normal execution workflow.

# [5,0,6,1,1] Interrupt Arbiter

The arbiter is the NVIC-like priority controller.

It:

- receives Interrupt Directives;
- validates level and scope;
- compares the new interrupt with the currently active interrupt;
- preempts a lower-priority handler when a higher-priority interrupt arrives;
- keeps lower-priority interrupts pending when appropriate;
- vectors execution to the correct handler;
- consumes broker facts to determine whether the interrupt action is complete.

Normal Margin Optimization, Execution Slicing and Optimal Execution are lower priority than L1.

## Nested behavior

Conceptually:

~~~text
normal execution
   |
   | L1 arrives
   v
CANCEL_WORK handler
   |
   | L3 arrives
   v
FLATTEN_ALL handler
~~~

L3 immediately supersedes L1.

A lower-level interrupt arriving while a higher-level interrupt is active cannot downgrade the active emergency state.

# [5,0,6,2,1] Latched Interrupt State

Interrupt state is persistent.

Conceptually it tracks:

~~~text
active_interrupt_id
active_level
scope
handler_state
pending_interrupts
completion_state
clear_state
~~~

The latch matters because cancellation alone does not remove the underlying registry requirement.

Without a latch:

~~~text
interrupt cancels order
        |
normal convergence notices registry still outstanding
        |
normal execution places order again
~~~

That is prohibited.

While the interrupt remains latched, normal work for the affected scope is blocked.

## Clearing / resuming

Completion of an interrupt action does **not** automatically mean normal trading resumes.

A separate authorized clear/resume decision is required to release the latched scope back to normal Execution Engine.

The exact upstream clear authority will be designed with the broader strategy/risk control plane.

# L1 — CANCEL_WORK

Purpose: stop unfinished execution without changing already-filled positions.

Handler:

1. preempt Optimal Execution for the affected scope;
2. block new placements/reprices for that scope;
3. cancel all working/unfilled broker orders in scope;
4. reconcile cancellation and any fills that occurred during the race;
5. leave confirmed existing positions unchanged;
6. keep the scope latched so the registry cannot recreate the cancelled work.

Example:

~~~text
requested BUY 100
filled 35
remaining passive order 65

L1 arrives

cancel/reconcile remaining 65
keep confirmed +35 position
do not place another order for the remaining 65
~~~

# L2 — FLATTEN_SCOPE

Purpose: exit a specified affected position set immediately.

Handler:

1. preempt normal execution for the affected scope;
2. suppress new normal orders;
3. cancel working orders in scope;
4. reconcile cancellations/fills;
5. refresh authoritative positions;
6. generate market flatten actions for the confirmed net positions in scope;
7. send those actions through Execution Recovery / Command Commit Guard and then the Broker Execution Port;
8. reconcile until the scoped positions are flat or an unresolved broker failure is reported.

Flatten means:

- long position -> SELL the remaining confirmed quantity;
- short position -> BUY the remaining confirmed quantity.

The normal time-based execution algorithm is bypassed.

Execution Engine does not infer strategy meaning here. The interrupt must carry or resolve to an explicit affected economic scope.

# L3 — FLATTEN_ALL

Purpose: emergency escape from all controlled exposure.

This is the highest current priority.

Handler:

1. preempt Margin Optimization, Execution Slicing and Optimal Execution globally;
2. block all new normal order generation;
3. cancel all controlled working orders;
4. reconcile cancellations and race fills;
5. refresh authoritative broker positions;
6. generate market flatten actions for every controlled non-zero position;
7. send those actions through Execution Recovery / Command Commit Guard and then the Broker Execution Port;
8. continue reconciling until all controlled positions are flat or an unresolved emergency is explicitly reported.

The normal execution algorithm, passive waiting, T/N timers, ordering mode, and Passive Chase are bypassed.

The broker boundary itself is **not** bypassed. Authentication, instrument translation, order transport, exchange validity, and authoritative reconciliation remain mandatory.

## Market-order caveat

If a market action cannot be accepted because the venue/broker is unavailable or the instrument is not tradable, Interrupt Control must report an unresolved emergency state.

It must not silently fall back to Passive Chase or pretend the position is flat.

# [5,0,6,7,2] Interrupt Action Plan

Interrupt Control emits a deterministic emergency action plan.

Current action classes are conceptually:

~~~text
CANCEL_SCOPE
FLATTEN_SCOPE_MARKET
FLATTEN_ALL_MARKET
~~~

These actions bypass the plug-in Optimal Execution algorithm, but still pass through Execution Recovery / Command Commit Guard and the write-ahead Execution Ledger before reaching the Broker Execution Port.

They still require authoritative reconciliation.

# Priority invariant

~~~text
L3 FLATTEN_ALL
    >
L2 FLATTEN_SCOPE
    >
L1 CANCEL_WORK
    >
normal Execution Engine
~~~

A higher-priority interrupt may preempt a lower-priority handler.

A lower-priority event may never weaken a higher-priority active interrupt.

# Architectural invariant

Interrupt Control may override:

- Margin Optimization;
- Execution Ordering Plan;
- Execution Slicing;
- Optimal Execution;
- Ordering Constraint Enforcer;
- Passive Chase or any future execution algorithm.

Interrupt Control may **not** bypass:

- Execution Recovery / Command Commit Guard and durable write-ahead recording;
- action-class-specific State Integrity permission;
- the Broker Execution Port;
- broker authentication/transport;
- authoritative order/fill/position reconciliation;
- mechanical venue validity.

This keeps emergency behavior fast while preserving broker-neutral safety and state correctness.

## Recovery boundary

Interrupt Control bypasses normal optimization policy, but it does not bypass durable execution safety.

Every interrupt mutation is wrapped as an Execution Action Envelope and passes through `[5,0,8,1,2] Command Commit Guard`.

Therefore interrupt cancellation and emergency flattening retain:

- durable write-ahead recording;
- unique action/correlation identity;
- authoritative reconciliation;
- restart recovery;
- protection against duplicate mutation after ambiguous timeout.

The guard does not force emergency actions back through Passive Chase or Margin Optimization. It only preserves execution-state correctness.
