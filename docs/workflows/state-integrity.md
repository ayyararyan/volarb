# [5,0,9,0,1] State Integrity

Status: **active reusable execution design**. The complete pipeline is not yet implemented; see [current contracts/ports](../../execution-engine/README.md). These rules specify required behavior, not a live trading service.

State Integrity is the broker-neutral readiness guard for Execution Engine.

Its job is not to decide strategy or execution quality. Its job is to decide whether the state being used is trustworthy enough for the requested action.

## [5,0,9,1,1] State Integrity Guard

It evaluates:

- market-data freshness;
- quote/LOB completeness where required;
- account-state freshness;
- position/order consistency;
- broker-feed continuity;
- recovery state;
- unresolved ambiguity;
- other provider-normalized validity flags.

## [5,0,9,7,1] Integrity Assessment

Possible state labels include:

~~~text
VALID
STALE
INCOMPLETE
INCONSISTENT
UNKNOWN
~~~

The assessment is **action-class aware**.

A single blanket boolean is insufficient because an emergency cancellation may still be valid when market quotes are stale, while a new passive risk-adding order should not be.

Conceptually:

~~~text
status = STALE

permissions:
  NORMAL_RISK_ADD = DENY
  NORMAL_RISK_REDUCE = conditional
  CANCEL = ALLOW
  EMERGENCY_FLATTEN = conditional_on_authoritative_positions_and_broker_connectivity
~~~

## Normal execution rule

Unknown or stale broker truth must not create new exposure.

Margin Optimization and Optimal Execution therefore require the relevant state-integrity permission before normal action.

Passive Chase must not use a stale best bid/ask merely because one exists locally.

## Emergency rule

Interrupt Control has different minimum integrity requirements.

Examples:

- L1 CANCEL_WORK does not require fresh LOB data, but it does require enough broker/order identity to issue and reconcile cancellations.
- L3 FLATTEN_ALL does not require Passive Chase-quality LOB freshness, but it does require authoritative position/order reconciliation and broker connectivity sufficient to attempt market flattening.

If the required emergency state cannot be established, Interrupt Control reports an unresolved emergency. It must not silently downgrade to normal execution.

## Recovery relationship

Recovery State feeds State Integrity.

An unresolved AMBIGUOUS or RECOVERY_REQUIRED scope denies normal new mutations until reconciliation establishes broker truth.
