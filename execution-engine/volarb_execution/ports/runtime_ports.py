"""Structural validation for injected Execution Engine dependencies."""

from __future__ import annotations

from typing import Any


def _need_method(value: Any, name: str, method: str) -> Any:
    if value is None or not callable(getattr(value, method, None)):
        raise TypeError(f"{name} must implement {method}()")
    return value


def assert_broker_port(value: Any) -> Any:
    return _need_method(value, "broker_port", "call")


def assert_clock_port(value: Any) -> Any:
    _need_method(value, "clock", "now")
    _need_method(value, "clock", "schedule")
    return value


def assert_ledger_port(value: Any) -> Any:
    _need_method(value, "ledger", "append")
    _need_method(value, "ledger", "entries")
    return value


def assert_market_port(value: Any) -> Any:
    return _need_method(value, "market", "snapshot")
