import pytest

from butterfly_lab.accounting import (
    Account,
    Contract,
    dated_spec,
    expiry_payoff,
    fee_for_fill,
    validate_iron_butterfly,
)


def legs(lot=10):
    return [
        (Contract("lp", "NIFTY", "2025-12-30", 9500, "PE", lot), lot),
        (Contract("sp", "NIFTY", "2025-12-30", 10000, "PE", lot), -lot),
        (Contract("sc", "NIFTY", "2025-12-30", 10000, "CE", lot), -lot),
        (Contract("lc", "NIFTY", "2025-12-30", 10500, "CE", lot), lot),
    ]


def test_signed_cash_lot_once_liquidation_and_reconciliation():
    structure = legs()
    validate_iron_butterfly(structure)
    a = Account()
    for contract, qty in structure:
        a.fill(
            contract, qty, 5 if qty > 0 else 50, 1, "2025-01-02T10:00:00+05:30", "entry", "cycle"
        )
    assert a.cash == 896  # 10*(50+50-5-5)-4, no second lot multiplication
    assert a.equity({c.contract_id: {"bid": 4, "ask": 51} for c, _ in structure}) == -44
    assert a.reconcile()["net_pnl"] is None
    for contract, qty in structure:
        a.fill(
            contract, -qty, 4 if qty > 0 else 40, 1, "2025-01-02T10:30:00+05:30", "exit", "cycle"
        )
    assert a.flat
    assert a.reconcile()["net_pnl"] == 172


def test_unknown_fees_and_bad_geometry_rejected():
    c, _ = legs()[0]
    with pytest.raises(ValueError, match="unknown"):
        Account().fill(c, 10, 1, None, "2025-01-02T10:00:00+05:30", "entry", "c")
    with pytest.raises(ValueError, match="four"):
        validate_iron_butterfly(legs()[:3])
    with pytest.raises(ValueError, match="matched"):
        validate_iron_butterfly(legs()[:3] + [(legs()[3][0], 20)])


def test_effective_lots_and_fee_transition():
    c, _ = legs()[0]
    specs = [
        {"effective_from": "2025-01-01", "effective_to": "2025-06-30", "lot_size": 10},
        {"effective_from": "2025-07-01", "lot_size": 20},
    ]
    assert dated_spec(c, "2025-03-01", specs) == 10
    with pytest.raises(ValueError, match="differs"):
        dated_spec(c, "2025-07-01", specs)
    base = {
        "brokerage_per_fill": 1,
        "exchange_rate": 0,
        "regulatory_rate": 0,
        "gst_rate": 0.18,
        "sell_tax_rate": 0.001,
        "buy_stamp_rate": 0.0001,
    }
    fees = [
        {**base, "effective_from": "2025-01-01", "effective_to": "2025-06-30"},
        {**base, "effective_from": "2025-07-01", "sell_tax_rate": 0.002},
    ]
    assert fee_for_fill(fees, "2025-06-30T10:00:00+05:30", -10, 100) == 2.18
    assert fee_for_fill(fees, "2025-07-01T10:00:00+05:30", -10, 100) == 3.18
    assert fee_for_fill(fees, "2025-07-01T10:00:00+05:30", 10, 100) == 1.28
    with pytest.raises(ValueError, match="missing"):
        fee_for_fill(fees, "2024-07-01T10:00:00+05:30", 10, 100)


def test_expiry_payoff_fixture_not_intraday_pricer():
    assert expiry_payoff(legs(), 10000, 900) == 900
    assert expiry_payoff(legs(), 20000, 900) == -4100
    assert expiry_payoff(legs(), 0, 900) == -4100
