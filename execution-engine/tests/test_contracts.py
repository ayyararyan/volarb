"""Parity tests for the canonical Python Execution Engine contracts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from volarb_execution.contracts.provider_error import (  # noqa: E402
    PROVIDER_ERROR_CONTRACT_VERSION,
    ProviderCommandOutcome,
    ProviderError,
    ProviderErrorCategory,
    ProviderErrorCode,
    ProviderOperationKind,
    is_provider_error,
)
from volarb_execution.ports.broker_port import (  # noqa: E402
    BrokerOperation,
    BrokerOperationKind,
    assert_broker_request,
    broker_operation_kind,
)
from volarb_execution.ports.runtime_ports import (  # noqa: E402
    assert_broker_port,
    assert_clock_port,
    assert_ledger_port,
    assert_market_port,
)


class BrokerContractTests(unittest.TestCase):
    def test_every_broker_operation_has_exactly_one_kind(self) -> None:
        query = {
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
        command = {
            BrokerOperation.PLACE_ORDER,
            BrokerOperation.MODIFY_ORDER,
            BrokerOperation.CANCEL_ORDER,
        }
        stream = {
            BrokerOperation.STREAM_MARKET,
            BrokerOperation.STREAM_ORDER_UPDATES,
        }

        self.assertEqual(query | command | stream, set(BrokerOperation))
        self.assertTrue(query.isdisjoint(command))
        self.assertTrue(query.isdisjoint(stream))
        self.assertTrue(command.isdisjoint(stream))

        for operation in query:
            self.assertEqual(broker_operation_kind(operation), BrokerOperationKind.QUERY)
        for operation in command:
            self.assertEqual(broker_operation_kind(operation), BrokerOperationKind.COMMAND)
        for operation in stream:
            self.assertEqual(broker_operation_kind(operation), BrokerOperationKind.STREAM)

    def test_broker_request_validation_rejects_unknown_or_wrong_kind(self) -> None:
        self.assertTrue(
            assert_broker_request(
                kind=BrokerOperationKind.COMMAND,
                operation=BrokerOperation.PLACE_ORDER,
            )
        )
        with self.assertRaises(TypeError):
            assert_broker_request(
                kind=BrokerOperationKind.QUERY,
                operation=BrokerOperation.PLACE_ORDER,
            )
        with self.assertRaises(TypeError):
            assert_broker_request(kind="COMMAND", operation="NOT_A_REAL_OPERATION")


class ProviderErrorContractTests(unittest.TestCase):
    def test_provider_error_serialization_preserves_global_wire_contract(self) -> None:
        error = ProviderError(
            category=ProviderErrorCategory.NETWORK,
            code=ProviderErrorCode.NETWORK_FAILURE,
            message="acknowledgement lost",
            operation=BrokerOperation.PLACE_ORDER.value,
            kind=ProviderOperationKind.COMMAND,
            outcome=ProviderCommandOutcome.UNKNOWN,
            provider={"key": "simulated", "nativeCode": "X"},
            observed_at="2026-10-04T00:00:00Z",
        )

        payload = error.to_dict()
        self.assertTrue(is_provider_error(error))
        self.assertEqual(payload["contractVersion"], PROVIDER_ERROR_CONTRACT_VERSION)
        self.assertEqual(payload["category"], "NETWORK")
        self.assertEqual(payload["code"], "PROVIDER.NETWORK_FAILURE")
        self.assertEqual(payload["kind"], "COMMAND")
        self.assertEqual(payload["outcome"], "UNKNOWN")
        self.assertEqual(payload["provider"]["nativeCode"], "X")
        self.assertEqual(payload["observedAt"], "2026-10-04T00:00:00Z")


class RuntimePortContractTests(unittest.TestCase):
    def test_structural_port_validation_matches_required_methods(self) -> None:
        class Broker:
            async def call(self, request):
                return request

        class Clock:
            def now(self):
                return 0

            def schedule(self, delay, callback):
                return delay, callback

        class Ledger:
            async def append(self, entry):
                return entry

            async def entries(self):
                return []

        class Market:
            def snapshot(self):
                return {}

        broker, clock, ledger, market = Broker(), Clock(), Ledger(), Market()
        self.assertIs(assert_broker_port(broker), broker)
        self.assertIs(assert_clock_port(clock), clock)
        self.assertIs(assert_ledger_port(ledger), ledger)
        self.assertIs(assert_market_port(market), market)

        with self.assertRaises(TypeError):
            assert_broker_port(object())
        with self.assertRaises(TypeError):
            assert_clock_port(object())
        with self.assertRaises(TypeError):
            assert_ledger_port(object())
        with self.assertRaises(TypeError):
            assert_market_port(object())


if __name__ == "__main__":
    unittest.main()
