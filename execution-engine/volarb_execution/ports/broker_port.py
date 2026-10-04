"""Provider-neutral broker operation vocabulary."""

from __future__ import annotations

from enum import StrEnum


class BrokerOperationKind(StrEnum):
    QUERY = "QUERY"
    COMMAND = "COMMAND"
    STREAM = "STREAM"


class BrokerOperation(StrEnum):
    GET_CAPABILITIES = "GET_CAPABILITIES"
    GET_READINESS = "GET_READINESS"
    RESOLVE_INSTRUMENT = "RESOLVE_INSTRUMENT"
    GET_ACCOUNT_SNAPSHOT = "GET_ACCOUNT_SNAPSHOT"
    GET_POSITIONS = "GET_POSITIONS"
    GET_FUNDS = "GET_FUNDS"
    GET_ORDERS = "GET_ORDERS"
    GET_ORDER = "GET_ORDER"
    GET_ORDER_BY_CORRELATION = "GET_ORDER_BY_CORRELATION"
    GET_TRADES = "GET_TRADES"
    GET_ORDER_TRADES = "GET_ORDER_TRADES"
    GET_HISTORICAL_TRADES = "GET_HISTORICAL_TRADES"
    GET_MARGIN = "GET_MARGIN"
    GET_BASKET_MARGIN = "GET_BASKET_MARGIN"
    GET_LTP = "GET_LTP"
    GET_QUOTE = "GET_QUOTE"
    PLACE_ORDER = "PLACE_ORDER"
    MODIFY_ORDER = "MODIFY_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    STREAM_MARKET = "STREAM_MARKET"
    STREAM_ORDER_UPDATES = "STREAM_ORDER_UPDATES"


_QUERY = {
    BrokerOperation.GET_CAPABILITIES,
    BrokerOperation.GET_READINESS,
    BrokerOperation.RESOLVE_INSTRUMENT,
    BrokerOperation.GET_ACCOUNT_SNAPSHOT,
    BrokerOperation.GET_POSITIONS,
    BrokerOperation.GET_FUNDS,
    BrokerOperation.GET_ORDERS,
    BrokerOperation.GET_ORDER,
    BrokerOperation.GET_ORDER_BY_CORRELATION,
    BrokerOperation.GET_TRADES,
    BrokerOperation.GET_ORDER_TRADES,
    BrokerOperation.GET_HISTORICAL_TRADES,
    BrokerOperation.GET_MARGIN,
    BrokerOperation.GET_BASKET_MARGIN,
    BrokerOperation.GET_LTP,
    BrokerOperation.GET_QUOTE,
}
_COMMAND = {
    BrokerOperation.PLACE_ORDER,
    BrokerOperation.MODIFY_ORDER,
    BrokerOperation.CANCEL_ORDER,
}
_STREAM = {
    BrokerOperation.STREAM_MARKET,
    BrokerOperation.STREAM_ORDER_UPDATES,
}


def broker_operation_kind(operation: BrokerOperation | str) -> BrokerOperationKind | None:
    try:
        op = BrokerOperation(operation)
    except ValueError:
        return None
    if op in _QUERY:
        return BrokerOperationKind.QUERY
    if op in _COMMAND:
        return BrokerOperationKind.COMMAND
    if op in _STREAM:
        return BrokerOperationKind.STREAM
    return None


def assert_broker_request(*, kind: BrokerOperationKind | str, operation: BrokerOperation | str) -> bool:
    try:
        normalized_kind = BrokerOperationKind(kind)
    except ValueError as exc:
        raise TypeError("Unknown broker operation kind") from exc
    try:
        normalized_operation = BrokerOperation(operation)
    except ValueError as exc:
        raise TypeError(f"Unknown broker operation: {operation}") from exc
    expected = broker_operation_kind(normalized_operation)
    if expected != normalized_kind:
        raise TypeError(
            f"Broker operation {normalized_operation.value} requires {expected.value}, "
            f"received {normalized_kind.value}"
        )
    return True
