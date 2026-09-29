import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "decision_controller.py"
spec = importlib.util.spec_from_file_location("decision_controller", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
decide = mod.decide


def test_candidate_invalid_data_is_no_trade():
    out = decide({"mode": "CANDIDATE", "branch": "CANDIDATE_INTRADAY", "data_health": "INVALID"})
    assert out["action"] == "NO_TRADE"
    assert out["terminal_gate"] == "DATA_HEALTH"


def test_post_close_is_locked():
    out = decide({"mode": "OPEN_POSITION", "branch": "LOCKED_OVERNIGHT"})
    assert out["action"] == "LOCKED_OVERNIGHT"


def test_new_overnight_latent_jump_is_blocked():
    out = decide({
        "mode": "CANDIDATE",
        "branch": "CANDIDATE_OVERNIGHT",
        "data_health": "HEALTHY",
        "market_regime": "LATENT_JUMP_RISK",
        "proposed_new_structure": True,
    })
    assert out["action"] == "NO_TRADE"
    assert out["terminal_gate"] == "MARKET_REGIME"


def test_candidate_requires_broker_pass():
    out = decide({
        "mode": "CANDIDATE",
        "branch": "CANDIDATE_OVERNIGHT",
        "data_health": "HEALTHY",
        "market_regime": "CALM_CARRY",
        "recent_gap_gate": "PASS",
        "broker_rms_gate": "UNKNOWN",
    })
    assert out["action"] == "NO_TRADE"
    assert out["terminal_gate"] == "BROKER_RMS"


def test_existing_broker_warning_exits():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_CARRY_GATE",
        "market_regime": "CALM_CARRY",
        "recent_gap_gate": "PASS",
        "broker_rms_gate": "WARN",
    })
    assert out["action"] == "SQUARE_OFF"
    assert out["terminal_gate"] == "BROKER_RMS"


def test_hard_risk_precedes_expiry_and_recenter():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_INTRADAY",
        "hard_risk_gate": "BLOCK",
        "expiry_exit_gate": "PASS",
        "recenter_gate": "PASS",
    })
    assert out["action"] == "SQUARE_OFF"
    assert out["terminal_gate"] == "HARD_EVENT_TAIL_LIQUIDITY"


def test_expiry_exit_precedes_recenter():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_INTRADAY",
        "hard_risk_gate": "PASS",
        "expiry_exit_gate": "EXIT",
        "recenter_gate": "PASS",
    })
    assert out["action"] == "SQUARE_OFF"
    assert out["terminal_gate"] == "EXPIRY_EXIT"


def test_recenter_requires_verified_transition_not_entry_only_margin():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_INTRADAY",
        "hard_risk_gate": "PASS",
        "expiry_exit_gate": "PASS",
        "recenter_gate": "PASS",
    })
    assert out["action"] == "HOLD"
    assert any("recenter blocked" in w for w in out["warnings"])


def test_default_open_intraday_is_hold():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_INTRADAY",
        "hard_risk_gate": "PASS",
        "expiry_exit_gate": "PASS",
        "recenter_gate": "FAIL",
    })
    assert out["action"] == "HOLD"


def test_default_open_carry_is_carry():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_CARRY_GATE",
        "market_regime": "CALM_CARRY",
        "recent_gap_gate": "PASS",
        "broker_rms_gate": "PASS",
        "event_latency_gate": "PASS",
        "joint_stress_gate": "PASS",
        "hard_risk_gate": "PASS",
        "expiry_exit_gate": "PASS",
        "recenter_gate": "FAIL",
    })
    assert out["action"] == "CARRY"


def test_candidate_survivors_return_candidates():
    out = decide({
        "mode": "CANDIDATE",
        "branch": "CANDIDATE_INTRADAY",
        "data_health": "HEALTHY",
        "intraday_rv_state": "FAVOURABLE",
        "intraday_rv_confidence": "high",
        "hard_risk_gate": "PASS",
        "candidate_count": 3,
        "candidate_ids": ["a", "b", "c"],
        "candidate_margin_checks": {"a": fresh_margin()},
        "candidate_specs": {"a": fresh_margin()["candidate"]},
    })
    assert out["action"] == "CANDIDATES"
    assert out["margin_eligible_candidate_ids"] == ["a"]


def test_required_news_filter_blocks_new_overnight_candidate():
    out = decide({
        "mode": "CANDIDATE",
        "branch": "CANDIDATE_OVERNIGHT",
        "data_health": "HEALTHY",
        "news_filter_required": True,
        "news_filter_status": "UNAVAILABLE",
        "market_regime": "CALM_CARRY",
        "recent_gap_gate": "PASS",
        "broker_rms_gate": "PASS",
    })
    assert out["action"] == "NO_TRADE"
    assert out["terminal_gate"] == "NEWS_FILTER"


def test_stale_news_filter_is_warning_not_terminal_by_itself():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_CARRY_GATE",
        "news_filter_required": True,
        "news_filter_status": "STALE_CALIBRATION",
        "market_regime": "CALM_CARRY",
        "recent_gap_gate": "PASS",
        "broker_rms_gate": "PASS",
        "event_latency_gate": "PASS",
        "joint_stress_gate": "PASS",
        "hard_risk_gate": "PASS",
        "expiry_exit_gate": "PASS",
        "recenter_gate": "FAIL",
    })
    assert out["action"] == "CARRY"
    assert any("STALE_CALIBRATION" in w for w in out["warnings"])


def test_intraday_candidate_requires_favourable_hf_rv():
    out = decide({
        "mode": "CANDIDATE",
        "branch": "CANDIDATE_INTRADAY",
        "data_health": "HEALTHY",
        "intraday_rv_state": "MARGINAL",
        "intraday_rv_confidence": "high",
        "candidate_count": 3,
    })
    assert out["action"] == "NO_TRADE"
    assert out["terminal_gate"] == "INTRADAY_RV_DRIFT"


def test_intraday_existing_unfavourable_hf_rv_exits():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_INTRADAY",
        "intraday_rv_state": "UNFAVOURABLE",
        "intraday_rv_confidence": "medium",
        "hard_risk_gate": "PASS",
        "expiry_exit_gate": "PASS",
    })
    assert out["action"] == "SQUARE_OFF"
    assert out["terminal_gate"] == "INTRADAY_RV_DRIFT"


def test_intraday_existing_marginal_warns_but_can_hold():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_INTRADAY",
        "intraday_rv_state": "MARGINAL",
        "intraday_rv_confidence": "high",
        "hard_risk_gate": "PASS",
        "expiry_exit_gate": "PASS",
        "recenter_gate": "FAIL",
    })
    assert out["action"] == "HOLD"
    assert any("MARGINAL" in w for w in out["warnings"])


def test_unfavourable_rv_exits_before_expiry_and_recenter():
    for confidence in ("medium", "high"):
        out = decide({
            "mode": "OPEN_POSITION", "branch": "OPEN_INTRADAY",
            "intraday_rv_state": "UNFAVOURABLE",
            "intraday_rv_confidence": confidence,
            "expiry_exit_gate": "EXIT", "recenter_gate": "PASS",
            "recenter_margin_check": {**fresh_margin(), "scope": "RECENTRE"},
        })
        assert out["action"] == "SQUARE_OFF"
        assert out["terminal_gate"] == "INTRADAY_RV_DRIFT"


def test_low_confidence_unfavourable_rv_continues_to_other_risk_gates():
    base = {
        "mode": "OPEN_POSITION", "branch": "OPEN_INTRADAY",
        "intraday_rv_state": "UNFAVOURABLE", "intraday_rv_confidence": "low",
        "hard_risk_gate": "PASS", "expiry_exit_gate": "PASS", "recenter_gate": "FAIL",
    }
    assert decide(base)["action"] == "HOLD"
    out = decide({**base, "hard_risk_gate": "FAIL"})
    assert out["action"] == "SQUARE_OFF"
    assert out["terminal_gate"] == "HARD_EVENT_TAIL_LIQUIDITY"


def test_missing_hf_data_neither_forces_exit_nor_overrides_expiry_exit():
    base = {
        "mode": "OPEN_POSITION", "branch": "OPEN_INTRADAY",
        "hard_risk_gate": "PASS", "expiry_exit_gate": "PASS", "recenter_gate": "FAIL",
    }
    out = decide(base)
    assert out["action"] == "HOLD"
    assert any("INSUFFICIENT_DATA" in warning for warning in out["warnings"])
    out = decide({**base, "expiry_exit_gate": "EXIT"})
    assert out["action"] == "SQUARE_OFF"
    assert out["terminal_gate"] == "EXPIRY_EXIT"


def fresh_margin():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    return {"candidate": {"symbol": "NIFTY", "expiry": "2026-10-06", "lower": 24000, "center": 25000, "upper": 26000, "lots": 1},
            "status": "PASS", "scope": "ENTRY_ONLY", "blockers": [], "asof": now.isoformat(),
            "validUntil": (now + timedelta(seconds=30)).isoformat(),
            "availableFundsRupees": 100000, "peakRequiredRupees": 50000,
            "reserveRupees": 1000, "headroomAfterReserveRupees": 49000}


def test_missing_failed_stale_or_inconsistent_margin_cannot_approve():
    base = {"mode": "CANDIDATE", "branch": "CANDIDATE_INTRADAY", "data_health": "HEALTHY",
            "intraday_rv_state": "FAVOURABLE", "candidate_count": 1, "candidate_ids": ["a"],
            "candidate_specs": {"a": fresh_margin()["candidate"]}}
    for changes in ({"status": "FAIL"}, {"status": "UNVERIFIED"},
                    {"asof": "2020-01-01T00:00:00Z"}, {"headroomAfterReserveRupees": 1},
                    {"reserveRupees": -1}, {"peakRequiredRupees": float("nan")}, {"blockers": ["stale"]}):
        out = decide({**base, "candidate_margin_checks": {"a": {**fresh_margin(), **changes}}})
        assert out["action"] == "NO_TRADE"
        assert out["terminal_gate"] == "MARGIN_AFFORDABILITY"
    assert decide(base)["terminal_gate"] == "MARGIN_AFFORDABILITY"


def test_margin_never_overrides_earlier_risk_gate_or_blocks_exit():
    assert decide({"mode":"CANDIDATE", "branch":"CANDIDATE_INTRADAY", "data_health":"INVALID",
                   "candidate_margin_checks":{"a":fresh_margin()}})["terminal_gate"] == "DATA_HEALTH"
    assert decide({"mode":"OPEN_POSITION", "branch":"OPEN_INTRADAY", "expiry_exit_gate":"EXIT"})["action"] == "SQUARE_OFF"


def test_recenter_accepts_only_transition_scoped_fresh_evidence():
    base = {"mode": "OPEN_POSITION", "branch": "OPEN_INTRADAY", "recenter_gate": "PASS"}
    assert decide({**base, "recenter_margin_check": fresh_margin()})["action"] == "HOLD"
    assert decide({**base, "recenter_margin_check": {**fresh_margin(), "scope": "RECENTRE"}})["action"] == "RECENTRE"


def test_margin_packet_must_match_exact_candidate_geometry_and_lots():
    p = fresh_margin()
    base = {"mode":"CANDIDATE", "branch":"CANDIDATE_INTRADAY", "data_health":"HEALTHY",
            "intraday_rv_state":"FAVOURABLE", "candidate_count":1, "candidate_ids":["a"],
            "candidate_margin_checks":{"a":p}, "candidate_specs":{"a":{**p["candidate"], "lots":2}}}
    assert decide(base)["terminal_gate"] == "MARGIN_AFFORDABILITY"
