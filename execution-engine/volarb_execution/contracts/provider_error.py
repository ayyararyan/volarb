"""Broker/provider error envelope shared by Execution Engine components."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping

PROVIDER_ERROR_CONTRACT_VERSION = "1.0"


class ProviderOperationKind(StrEnum):
    COMMAND = "COMMAND"
    QUERY = "QUERY"
    STREAM = "STREAM"


class ProviderCommandOutcome(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    KNOWN_NOT_APPLIED = "KNOWN_NOT_APPLIED"
    UNKNOWN = "UNKNOWN"


class ProviderErrorCategory(StrEnum):
    CONFIGURATION = "CONFIGURATION"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    ACCOUNT_STATE = "ACCOUNT_STATE"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_REQUEST = "INVALID_REQUEST"
    ORDER_REJECTED = "ORDER_REJECTED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    PROVIDER_INTERNAL = "PROVIDER_INTERNAL"
    NETWORK = "NETWORK"
    TIMEOUT = "TIMEOUT"
    PROTOCOL = "PROTOCOL"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class ProviderErrorCode(StrEnum):
    NOT_CONFIGURED = "PROVIDER.NOT_CONFIGURED"
    MUTATION_NOT_READY = "PROVIDER.MUTATION_NOT_READY"
    AUTHENTICATION_FAILED = "PROVIDER.AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "PROVIDER.AUTHORIZATION_FAILED"
    ACCOUNT_STATE_INVALID = "PROVIDER.ACCOUNT_STATE_INVALID"
    RATE_LIMITED = "PROVIDER.RATE_LIMITED"
    INVALID_REQUEST = "PROVIDER.INVALID_REQUEST"
    ORDER_REJECTED = "PROVIDER.ORDER_REJECTED"
    DATA_UNAVAILABLE = "PROVIDER.DATA_UNAVAILABLE"
    RESOURCE_NOT_FOUND = "PROVIDER.RESOURCE_NOT_FOUND"
    INTERNAL_FAILURE = "PROVIDER.INTERNAL_FAILURE"
    NETWORK_FAILURE = "PROVIDER.NETWORK_FAILURE"
    TIMEOUT = "PROVIDER.TIMEOUT"
    PROTOCOL_FAILURE = "PROVIDER.PROTOCOL_FAILURE"
    UNSUPPORTED = "PROVIDER.UNSUPPORTED"
    UNKNOWN = "PROVIDER.UNKNOWN"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ProviderError(Exception):
    """Normalized provider failure with explicit mutation outcome semantics."""

    def __init__(
        self,
        *,
        category: ProviderErrorCategory | str,
        code: ProviderErrorCode | str,
        message: str | None,
        operation: str,
        kind: ProviderOperationKind | str,
        outcome: ProviderCommandOutcome | str,
        provider: Mapping[str, Any] | None = None,
        observed_at: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.category = ProviderErrorCategory(category)
        self.code = ProviderErrorCode(code)
        self.kind = ProviderOperationKind(kind)
        self.outcome = ProviderCommandOutcome(outcome)
        self.operation = str(operation)
        self.provider = dict(provider or {})
        self.observed_at = observed_at or _utc_now()
        self.contract_version = PROVIDER_ERROR_CONTRACT_VERSION
        super().__init__(message or self.code.value)
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": type(self).__name__,
            "contractVersion": self.contract_version,
            "category": self.category.value,
            "code": self.code.value,
            "message": str(self),
            "operation": self.operation,
            "kind": self.kind.value,
            "outcome": self.outcome.value,
            "provider": dict(self.provider),
            "observedAt": self.observed_at,
        }


def is_provider_error(error: BaseException) -> bool:
    if isinstance(error, ProviderError):
        return True
    return (
        getattr(error, "contract_version", None) == PROVIDER_ERROR_CONTRACT_VERSION
        and getattr(error, "category", None) in set(ProviderErrorCategory)
        and getattr(error, "code", None) in set(ProviderErrorCode)
    )
