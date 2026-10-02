import pandas as pd

from butterfly_lab.replication import replicate_accounting, replicate_controlled


def test_replication_detects_double_lot_and_missing_cash():
    fills = pd.DataFrame(
        [
            {
                "policy": "hold",
                "cycle_id": "c",
                "contract_id": "x",
                "units": 10,
                "price": 10,
                "fees": 1,
            },
            {
                "policy": "hold",
                "cycle_id": "c",
                "contract_id": "x",
                "units": -10,
                "price": 11,
                "fees": 1,
            },
        ]
    )
    ledger = pd.DataFrame([{"policy": "hold", "opportunity_id": "c", "pnl_inr": 8}])
    assert replicate_accounting(fills, ledger)["status"] == "PASS"
    ledger["pnl_inr"] = 80
    assert replicate_accounting(fills, ledger)["status"] == "FAIL"
    assert replicate_accounting(fills.iloc[:1], ledger)["status"] == "FAIL"


def test_replication_detects_changed_reported_metric():
    rows = pd.DataFrame({"baseline_loss": [1, 2, 3], "candidate_loss": [1, 2, 3]})
    assert replicate_controlled(rows, 0)["status"] == "PASS"
    assert replicate_controlled(rows, 0.1)["status"] == "FAIL"
