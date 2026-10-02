import hashlib
from pathlib import Path

import pytest

from butterfly_lab import observed_controller_v26
from butterfly_lab.baselines import (
    baseline_golden_cases,
    certify_baseline,
    observed_decision,
    policy_decision,
)


@pytest.mark.parametrize("baseline", ["B0-simple", "B-policy", "B-as-observed"])
def test_three_distinct_golden_baselines(baseline):
    assert certify_baseline(baseline, baseline_golden_cases(baseline))["status"] == "PASS"


def test_observed_defaults_preserved_and_source_frozen():
    digest = hashlib.sha256(Path(observed_controller_v26.__file__).read_bytes()).hexdigest()
    assert digest == "d3926a533babca53d022d2b3422fe5cd835e1962c29eb1f01e759b27eb239597"
    result = observed_decision(
        {"mode": "OPEN_POSITION", "branch": "OPEN_INTRADAY"}, "2026-09-30T10:00:00+05:30"
    )
    assert result["action"] == "HOLD"
    assert any("loss budget" in x for x in result["warnings"])
    assert (
        policy_decision({"decision_at": "2026-09-30T10:00:00+05:30", "held": True})["action"]
        == "BLOCKED"
    )


def test_observed_margin_clock_is_reproducible():
    data = {
        "mode": "CANDIDATE",
        "branch": "CANDIDATE_INTRADAY",
        "session_vrp_state": "FAVOURABLE",
        "intraday_rv_state": "FAVOURABLE",
        "candidate_count": 1,
        "candidate_ids": ["c"],
        "candidate_specs": {
            "c": {
                "symbol": "NIFTY",
                "expiry": "2026-10-06",
                "lower": 21000,
                "center": 22000,
                "upper": 23000,
                "lots": 1,
            }
        },
    }
    data["candidate_margin_checks"] = {
        "c": {
            "candidate": data["candidate_specs"]["c"],
            "status": "PASS",
            "scope": "ENTRY_ONLY",
            "blockers": [],
            "asof": "2026-09-30T10:00:00+05:30",
            "validUntil": "2026-09-30T10:00:30+05:30",
            "availableFundsRupees": 11000,
            "peakRequiredRupees": 10000,
            "reserveRupees": 1000,
            "headroomAfterReserveRupees": 0,
        }
    }
    assert observed_decision(data, "2026-09-30T10:00:10+05:30")["action"] == "CANDIDATES"
    assert observed_decision(data, "2026-09-30T10:00:31+05:30")["action"] == "NO_TRADE"


def test_policy_first_terminal_and_loss_required_for_entry():
    base = {
        "decision_at": "2026-09-30T10:00:00+05:30",
        "data_health": "PASS",
        "held": False,
        "loss_inr": 1000,
        "session_vrp": "FAIL",
        "intraday_rv": "FAIL",
        "event_tail": "FAIL",
    }
    assert policy_decision(base)["reason"] == "loss_budget"
    assert policy_decision({**base, "loss_inr": 0})["reason"] == "session_vrp"
    assert policy_decision({**base, "loss_inr": None})["reason"] == "loss_evidence_unavailable"
    assert policy_decision({**base, "data_health": "FAIL"})["reason"] == "data_health"
    assert (
        policy_decision({**base, "loss_inr": 0, "session_vrp": "PASS", "re_entry": True})["reason"]
        == "reentry_requires_fresh_pass"
    )


def test_b0_does_not_silently_construct_asymmetric_wings():
    import pandas as pd
    from butterfly_lab.baselines import select_b0

    rows = [
        {
            "contract_id": str(k) + t,
            "underlying": "NIFTY",
            "expiry": "2027-01-01",
            "strike": k,
            "option_type": t,
            "lot_size": 10,
        }
        for k, t in [(9000, "PE"), (10000, "PE"), (10000, "CE"), (10500, "CE")]
    ]
    with pytest.raises(ValueError, match="symmetric"):
        select_b0(pd.DataFrame(rows), spot=10000, session="2026-01-01", width_floor=500)
