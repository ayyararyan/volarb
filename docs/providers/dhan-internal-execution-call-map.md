# Dhan <-> Internal Execution call map

Status: **implementation contract active**.

Dhan implements the mounted broker-provider boundary. Internal Execution remains broker-neutral and calls Dhan only through the Broker Execution Port.

## Where Internal Execution needs Dhan

| Internal Execution area | Dhan operations required | Purpose |
|---|---|---|
| State Integrity | GET_READINESS, GET_ACCOUNT_SNAPSHOT, GET_QUOTE, GET_ORDERS, GET_TRADES | establish whether broker/account/market/order truth is usable |
| Margin Optimization | GET_POSITIONS, GET_FUNDS, GET_ORDERS, GET_MARGIN, GET_BASKET_MARGIN | obtain authoritative account and hypothetical margin facts; Dhan does not decide affordability |
| Execution Slicing | **none** | slicing is core-owned; Dhan native slicing is not used |
| Optimal Execution | GET_QUOTE / GET_LTP, PLACE_ORDER, MODIFY_ORDER, CANCEL_ORDER, GET_ORDER, GET_ORDER_TRADES | observe current state and transmit the exact upstream-selected action |
| Execution Recovery | GET_ORDER, GET_ORDER_BY_CORRELATION, GET_ORDER_TRADES, GET_ORDERS, GET_TRADES, GET_HISTORICAL_TRADES, GET_POSITIONS | reconstruct broker truth after ambiguity or restart |
| Interrupt Control | GET_ORDERS, CANCEL_ORDER, GET_POSITIONS, PLACE_ORDER | cancel controlled work and submit explicit upstream-selected market flatten orders |

A strategy "leg" has no Dhan semantic. If Internal Execution asks to execute a leg, Dhan receives an ordinary broker order for the already-selected instrument, side, quantity and order type.

## Connector

The implemented connector is:

~~~text
DhanBrokerPort.call({
  kind: QUERY | COMMAND,
  operation: <broker-neutral operation>,
  payload: {...}
})
~~~

Successful replies use one fact envelope:

~~~text
{
  contractVersion,
  provider: "dhan",
  kind,
  operation,
  observedAt,
  providerOverheadMicros,
  data
}
~~~

Failures use the global Provider Error Envelope. No Dhan-native error crosses this connector.

## Configuration boundary

Minimum query configuration:

~~~text
DHAN_CLIENT_ID
DHAN_ACCESS_TOKEN or injected tokenProvider
~~~

Additional mutation configuration:

~~~text
DHAN_PROVIDER_COMMANDS_ENABLED=true
DHAN_PROVIDER_EGRESS_IP=<static outbound IP>
DHAN_PROVIDER_STATIC_IP_CONFIRMED=true
~~~

Legacy `DHAN_EXECUTION_*` variables remain accepted as migration fallbacks.

Missing minimum configuration yields:

~~~text
category = CONFIGURATION
code = PROVIDER.NOT_CONFIGURED
~~~

Commands that are disabled or fail static-IP/account readiness yield:

~~~text
category = CONFIGURATION
code = PROVIDER.MUTATION_NOT_READY
outcome = KNOWN_NOT_APPLIED
~~~

Successful command readiness is cached for a short configurable TTL so profile/IP/whitelist checks do not sit on every order call.

## Margin rule

Margin calculation is information, not a provider decision.

For example, a margin response with a positive `insufficientBalance` is returned normally to Margin Optimization. Dhan does not convert it into PASS/FAIL. If an actual order is rejected by the broker/RMS, that rejection goes through the global error contract.

## Speed rules

- runtime constructed once and kept warm;
- instrument master cached/indexed;
- command readiness cached;
- account snapshot fetches positions, funds and orders concurrently;
- no strategy logic, ledger fsync, repricing loop, waits, MCP or LLM in the connector;
- provider-call elapsed microseconds recorded for later p50/p95/p99 benchmarking.

## Remaining transport work

The Broker Port reserves STREAM, but live market-feed and live order-update WebSockets are not yet advertised as implemented. Until that transport is wired, GET_QUOTE / GET_LTP remain the synchronous market-data surface.
