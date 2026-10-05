"""Trusted account binding; strategy/mount/intent IDs do not split broker risk."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionScope:
    provider: str
    account_id: str

    def __post_init__(self) -> None:
        for name in ("provider", "account_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{name} must be non-empty canonical text")

    @property
    def key(self) -> str:
        value = json.dumps([self.provider, self.account_id], separators=(",", ":"))
        return hashlib.sha256(value.encode()).hexdigest()


class AccountBrokerPort:
    """Bind one configured provider connection to its verified account.

    The production driver must verify this binding against its credentials/readiness.
    It cannot be supplied by an execution action or by an LLM proposal.
    """

    def __init__(self, scope: ExecutionScope, delegate: Any) -> None:
        if not isinstance(scope, ExecutionScope) or not callable(getattr(delegate, "call", None)):
            raise TypeError("AccountBrokerPort requires a scope and broker call port")
        if getattr(delegate, "scope", scope) != scope:
            raise ValueError("delegate is already bound to a different broker account")
        self._scope = scope
        self._delegate = delegate

    @property
    def scope(self) -> ExecutionScope:
        return self._scope

    def call(self, request: dict[str, Any]) -> Any:
        return self._delegate.call(request)
