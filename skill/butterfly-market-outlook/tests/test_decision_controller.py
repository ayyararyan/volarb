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


def test_recenter_when_all_higher_gates_pass():
    out = decide({
        "mode": "OPEN_POSITION",
        "branch": "OPEN_INTRADAY",
        "hard_risk_gate": "PASS",
        "expiry_exit_gate": "PASS",
        "recenter_gate": "PASS",
    })
    assert out["action"] == "RECENTRE"


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
        "hard_risk_gate": "PASS",
        "candidate_count": 3,
    })
    assert out["action"] == "CANDIDATES"
