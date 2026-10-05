"""Canonical broker-neutral envelope for mutating execution actions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from ..ports.broker_port import BrokerOperation, BrokerOperationKind, assert_broker_request

CorrelationIdFactory = Callable[[str, Mapping[str, Any]], str]


def _get(mapping: Mapping[str, Any], snake: str, camel: str, default: Any = None) -> Any:
    if snake in mapping:
        return mapping[snake]
    if camel in mapping:
        return mapping[camel]
    return default


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value.strip()


def _iso_utc(value: Any, now_ms: float) -> str:
    if value is None:
        parsed = datetime.fromtimestamp(now_ms / 1000, tz=UTC)
    elif isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise TypeError("created_at must be a valid timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _default_correlation_id(action_id: str, _: Mapping[str, Any]) -> str:
    return f"exec:{action_id}"


@dataclass(frozen=True, slots=True)
class ExecutionAction:
    action_id: str
    action_class: str
    origin_type: str
    origin_id: str
    intent_id: str | None
    intent_version: int | None
    slice_id: str | None
    correlation_id: str
    operation: BrokerOperation
    payload: dict[str, Any]
    created_at: str


def normalize_execution_action(
    action: Mapping[str, Any],
    *,
    now_ms: float,
    correlation_id_factory: CorrelationIdFactory | None = None,
) -> ExecutionAction:
    if not isinstance(action, Mapping):
        raise TypeError("execution action must be a mapping")

    action_id = _required_text(_get(action, "action_id", "actionId"), "action_id")
    action_class = _required_text(_get(action, "action_class", "actionClass"), "action_class")
    origin_type = _required_text(_get(action, "origin_type", "originType"), "origin_type").upper()
    origin_id = _required_text(_get(action, "origin_id", "originId"), "origin_id")
    operation_text = _required_text(
        _get(action, "operation", "requestedOperation"),
        "operation",
    ).upper()

    assert_broker_request(kind=BrokerOperationKind.COMMAND, operation=operation_text)
    operation = BrokerOperation(operation_text)

    raw_intent_id = _get(action, "intent_id", "intentId")
    raw_intent_version = _get(action, "intent_version", "intentVersion")
    has_intent_id = raw_intent_id not in (None, "")
    has_intent_version = raw_intent_version is not None
    if has_intent_id != has_intent_version:
        raise TypeError("intent_id and intent_version must either both be present or both be absent")
    if origin_type != "INTERRUPT" and not has_intent_id:
        raise TypeError("non-interrupt execution actions require intent_id and intent_version")

    intent_id = _required_text(str(raw_intent_id), "intent_id") if has_intent_id else None
    intent_version = None
    if has_intent_version:
        if isinstance(raw_intent_version, bool):
            raise TypeError("intent_version must be a positive integer")
        try:
            numeric_version = float(raw_intent_version)
            intent_version = int(numeric_version)
        except (TypeError, ValueError, OverflowError) as exc:
            raise TypeError("intent_version must be a positive integer") from exc
        if not numeric_version.is_integer() or intent_version < 1:
            raise TypeError("intent_version must be a positive integer")

    raw_slice_id = _get(action, "slice_id", "sliceId")
    slice_id = None if raw_slice_id is None else _required_text(str(raw_slice_id), "slice_id")

    factory = correlation_id_factory or _default_correlation_id
    raw_correlation_id = _get(action, "correlation_id", "correlationId")
    if raw_correlation_id in (None, ""):
        raw_correlation_id = factory(action_id, action)
    correlation_id = _required_text(str(raw_correlation_id), "correlation_id")

    raw_payload = action.get("payload", {})
    if not isinstance(raw_payload, Mapping):
        raise TypeError("payload must be a mapping")
    payload = deepcopy(dict(raw_payload))

    return ExecutionAction(
        action_id=action_id,
        action_class=action_class,
        origin_type=origin_type,
        origin_id=origin_id,
        intent_id=intent_id,
        intent_version=intent_version,
        slice_id=slice_id,
        correlation_id=correlation_id,
        operation=operation,
        payload=payload,
        created_at=_iso_utc(_get(action, "created_at", "createdAt"), now_ms),
    )


def broker_request_for_execution_action(action: ExecutionAction) -> dict[str, Any]:
    payload = deepcopy(action.payload)
    identity = {
        "actionId": action.action_id,
        "correlationId": action.correlation_id,
        "intentId": action.intent_id,
        "intentVersion": action.intent_version,
        "sliceId": action.slice_id,
    }
    if action.operation is BrokerOperation.PLACE_ORDER:
        order = dict(payload.get("order") or {})
        order.update(identity)
        payload["order"] = order
    else:
        payload.update(identity)

    return {
        "kind": BrokerOperationKind.COMMAND.value,
        "operation": action.operation.value,
        "payload": payload,
    }
