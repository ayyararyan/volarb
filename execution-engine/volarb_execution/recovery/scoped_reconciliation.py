"""[5,0,8,1,1] conservative read-only reconciliation of account mutations."""

from __future__ import annotations

import asyncio
import math
from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping

from ..ports.runtime_ports import assert_admission_ledger_port, assert_broker_port, assert_clock_port
from .command_commit_guard import _maybe_await
from .execution_scope import ExecutionScope

_TERMINAL = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
_ORDER_STATES = _TERMINAL | {"PENDING", "PARTIALLY_FILLED"}
_STABLE_FIELDS = ("brokerOrderRef", "brokerCorrelationRef", "instrument", "side", "productType",
                  "orderType", "status", "requestedQuantity", "filledQuantity", "remainingQuantity",
                  "limitPrice", "triggerPrice")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {field}")
    return value


def _integer(value: Any, field: str, *, minimum: int | None = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or (minimum is not None and value < minimum):
        raise ValueError(f"invalid {field}")
    return value


def _instrument(value: Any) -> tuple[str, str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("missing normalized instrument")
    return tuple(_text(value.get(k), k) for k in ("provider", "providerInstrumentId", "exchangeSegment"))


class ScopedReconciler:
    """Queries the injected broker; never sends a COMMAND or retries a mutation.

    CLEAN means no unresolved mutation in this account, not target completion or
    a flat account. An empty lookup cannot prove non-application. Without a
    provider command receipt, an uncertain modification stays blocked until its
    target order is terminal; matching price/quantity alone is insufficient.
    """

    def __init__(self, *, ledger: Any, broker_port: Any, clock: Any,
                 max_observation_age_ms: float, query_timeout_s: float) -> None:
        self.ledger = assert_admission_ledger_port(ledger)
        self.broker_port = assert_broker_port(broker_port)
        self.clock = assert_clock_port(clock)
        self.scope = getattr(broker_port, "scope", None)
        if not isinstance(self.scope, ExecutionScope):
            raise TypeError("broker_port must have a trusted ExecutionScope account binding")
        for name, value in (("max_observation_age_ms", max_observation_age_ms), ("query_timeout_s", query_timeout_s)):
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        self.max_age_ms = max_observation_age_ms
        self.query_timeout_s = query_timeout_s

    async def _query(self, operation: str, payload: dict[str, Any], dispatched_at_ms: float,
                     evidence: list[dict[str, Any]]) -> Any:
        async with asyncio.timeout(self.query_timeout_s):
            result = await _maybe_await(self.broker_port.call({"kind": "QUERY", "operation": operation, "payload": payload}))
        if (not isinstance(result, Mapping) or result.get("contractVersion") != "1.0"
                or result.get("provider") != self.scope.provider or result.get("kind") != "QUERY"
                or result.get("operation") != operation):
            raise ValueError("invalid reconciliation response envelope")
        try:
            timestamp = datetime.fromisoformat(result["observedAt"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("observation timestamp needs a timezone")
            observed_ms = timestamp.timestamp() * 1000
        except (KeyError, TypeError, AttributeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid observation timestamp") from exc
        now = float(self.clock.now())
        if not math.isfinite(now) or observed_ms < dispatched_at_ms or observed_ms > now or now - observed_ms > self.max_age_ms:
            raise ValueError("stale, pre-dispatch or future broker observation")
        evidence.append({"operation": operation, "observedAtMs": observed_ms, "data": deepcopy(result.get("data"))})
        return deepcopy(result.get("data"))

    def _order(self, data: Any, expected_id: str | None = None) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("order lookup returned no authoritative order")
        order_id = _text(data.get("brokerOrderRef"), "brokerOrderRef")
        if expected_id is not None and order_id != expected_id:
            raise ValueError("order lookup returned a different order")
        if _instrument(data.get("instrument"))[0] != self.scope.provider:
            raise ValueError("order instrument provider mismatch")
        if data.get("side") not in {"BUY", "SELL"} or data.get("status") not in _ORDER_STATES:
            raise ValueError("unknown order side/status")
        _text(data.get("productType"), "productType")
        requested = _integer(data.get("requestedQuantity"), "requestedQuantity", minimum=1)
        filled = _integer(data.get("filledQuantity"), "filledQuantity")
        remaining = _integer(data.get("remainingQuantity"), "remainingQuantity")
        if filled > requested or remaining > requested - filled:
            raise ValueError("inconsistent order quantities")
        if data["status"] not in _TERMINAL and remaining != requested - filled:
            raise ValueError("working order quantities do not conserve quantity")
        if data["status"] == "FILLED" and filled != requested:
            raise ValueError("filled order has an unfilled remainder")
        if data["status"] == "REJECTED" and filled != 0:
            raise ValueError("rejected order reports fills")
        return data

    def _trades(self, data: Any, order: Mapping[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(data, list):
            raise ValueError("missing order trade observations")
        unique: dict[str, dict[str, Any]] = {}
        for trade in data:
            if not isinstance(trade, dict) or trade.get("brokerOrderRef") != order["brokerOrderRef"]:
                raise ValueError("trade belongs to a different order")
            identity = _text(trade.get("exchangeTradeRef"), "exchangeTradeRef")
            if _instrument(trade.get("instrument")) != _instrument(order["instrument"]) or trade.get("side") != order["side"] or trade.get("productType") != order["productType"]:
                raise ValueError("trade identity does not match order")
            _integer(trade.get("quantity"), "trade quantity", minimum=1)
            price = trade.get("price")
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                raise ValueError("invalid trade price")
            if identity in unique and unique[identity] != trade:
                raise ValueError("conflicting duplicate trade identity")
            unique[identity] = trade
        trades = list(unique.values())
        if sum(t["quantity"] for t in trades) != order["filledQuantity"]:
            raise ValueError("order/trade filled quantities disagree or trade history is incomplete")
        return trades

    def _positions(self, data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, list):
            raise ValueError("missing position observations")
        seen = set()
        for row in data:
            if not isinstance(row, dict):
                raise ValueError("invalid position")
            instrument = _instrument(row.get("instrument"))
            if instrument[0] != self.scope.provider:
                raise ValueError("position provider mismatch")
            identity = (instrument, _text(row.get("productType"), "productType"))
            if identity in seen:
                raise ValueError("duplicate position identity")
            seen.add(identity)
            _integer(row.get("netQuantity"), "netQuantity", minimum=None)
        return data

    async def reconcile(self) -> dict[str, Any]:
        with self.ledger.lock_scope(self.scope) as lease:
            pending = self.ledger.pending(self.scope)
            if pending is None:
                return {"state": "CLEAN", "scopeKey": self.scope.key, "actionId": None}
            action_id = pending["action_id"]
            if pending["status"] == "INTENDED":
                self.ledger.abort_before_dispatch(lease, action_id, "recovered before durable dispatch marker")
                return {"state": "CLEAN", "scopeKey": self.scope.key, "actionId": action_id, "resolution": "NOT_SENT"}
            action = pending["action"]
            evidence: list[dict[str, Any]] = []
            try:
                dispatched_at_ms = pending["dispatched_at_ms"]
                if not isinstance(dispatched_at_ms, (float, int)) or not math.isfinite(dispatched_at_ms):
                    raise ValueError("missing durable dispatch timestamp")
                operation = action["operation"]
                if operation == "PLACE_ORDER":
                    order = self._order(await self._query("GET_ORDER_BY_CORRELATION", {"correlationId": action["correlation_id"]}, dispatched_at_ms, evidence))
                    acknowledgement = (pending.get("outcome") or {}).get("brokerResult", {})
                    acknowledged_id = acknowledgement.get("data", {}).get("brokerOrderRef")
                    if acknowledged_id and acknowledged_id != order["brokerOrderRef"]:
                        raise ValueError("correlated order contradicts acknowledged order identity")
                    if (order.get("coreCorrelationId") != action["correlation_id"]
                            or not order.get("providerCorrelationRef")
                            or order.get("providerCorrelationRef") != order.get("brokerCorrelationRef")):
                        raise ValueError("placement correlation is not authoritatively linked")
                    expected = action["payload"]["order"]
                    if (_instrument(expected.get("providerInstrumentRef")) != _instrument(order["instrument"])
                            or any(order.get(actual) != expected.get(wanted) for actual, wanted in (
                                ("side", "side"), ("productType", "productType"),
                                ("requestedQuantity", "quantity"), ("orderType", "orderType")))):
                        raise ValueError("correlated order does not match admitted placement")
                else:
                    target = _text(action["payload"].get("orderId"), "target orderId")
                    order = self._order(await self._query("GET_ORDER", {"orderId": target}, dispatched_at_ms, evidence), target)
                    if operation not in {"MODIFY_ORDER", "CANCEL_ORDER"}:
                        raise ValueError("unsupported reconciliation operation")
                    if order["status"] not in _TERMINAL:
                        raise ValueError("target remains live; no terminal order or command-specific final receipt")
                target = order["brokerOrderRef"]
                trades = self._trades(await self._query("GET_ORDER_TRADES", {"orderId": target}, dispatched_at_ms, evidence), order)
                positions = self._positions(await self._query("GET_POSITIONS", {}, dispatched_at_ms, evidence))
                final = self._order(await self._query("GET_ORDER", {"orderId": target}, dispatched_at_ms, evidence), target)
                if any(order.get(field) != final.get(field) for field in _STABLE_FIELDS):
                    raise ValueError("order changed while reconciling; obtain a fresh observation set")
                if any(float(self.clock.now()) - e["observedAtMs"] > self.max_age_ms for e in evidence):
                    raise ValueError("observation set expired before reconciliation completed")
                result = {"state": "CLEAN", "scopeKey": self.scope.key, "actionId": action_id,
                          "resolution": "PLACEMENT_IDENTIFIED" if operation == "PLACE_ORDER" else "TARGET_ORDER_TERMINAL",
                          "brokerOrderRef": target, "orderStatus": final["status"],
                          "confirmedFilledQuantity": final["filledQuantity"],
                          "confirmedUnfilledQuantity": final["requestedQuantity"] - final["filledQuantity"],
                          "orderStillFillable": final["status"] not in _TERMINAL,
                          "trades": trades, "positions": positions, "evidence": evidence}
            except Exception as error:
                result = {"state": "AMBIGUOUS", "scopeKey": self.scope.key, "actionId": action_id,
                          "reason": str(error), "errorType": type(error).__name__, "evidence": evidence}
            self.ledger.record_reconciliation(lease, action_id, pending["revision"], resolved=result["state"] == "CLEAN", details=result)
            return result
