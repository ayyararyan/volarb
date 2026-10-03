import copy
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_session_vrp.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures_session_vrp_state_20260930.json"
spec = importlib.util.spec_from_file_location("evaluate_session_vrp", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
evaluate = mod.evaluate


def state():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_real_30_september_dashboard_had_no_premium():
    out = evaluate(state())
    assert out["session_vrp_state"] == "UNFAVOURABLE"
    assert out["iv_minus_rv_vol_points"] < 0
    assert out["iv_over_rv_ratio"] < 1


def test_premium_above_margin_is_favourable():
    s = state()
    s["atm"]["front"]["implied_volatility"] = 0.145
    out = evaluate(s)
    assert out["session_vrp_state"] == "FAVOURABLE"
    assert out["iv_minus_rv_vol_points"] > 1.0


def test_premium_below_margin_or_ratio_is_unfavourable():
    s = state()
    s["atm"]["front"]["implied_volatility"] = s["forecast"]["annualized_volatility"] + 0.005
    assert evaluate(s)["session_vrp_state"] == "UNFAVOURABLE"
    s["atm"]["front"]["implied_volatility"] = 0.145
    assert evaluate(s, {"min_margin_vol_points": 3.0})["session_vrp_state"] == "UNFAVOURABLE"


def test_stale_unfitted_or_arbitrage_violating_surface_is_unknown():
    for mutate in (
        lambda s: s["verdict"].update(status="stale"),
        lambda s: s["verdict"].update(surface_is_stale=True),
        lambda s: s.update(fit_ok=False),
        lambda s: s.update(fit_age_seconds=999),
        lambda s: s["arbitrage"].update(passed=False),
        lambda s: s["atm"]["front"].update(status="unsupported"),
        lambda s: s["forecast"].update(status="error"),
        lambda s: s["forecast"].update(age_calendar_days=4),
        lambda s: s["atm"]["front"].pop("implied_volatility"),
    ):
        s = copy.deepcopy(state())
        s["atm"]["front"]["implied_volatility"] = 0.145  # would be favourable if healthy
        mutate(s)
        out = evaluate(s)
        assert out["session_vrp_state"] == "UNKNOWN", out
        assert out["reasons"]


def test_empty_state_is_unknown_not_favourable():
    out = evaluate({})
    assert out["session_vrp_state"] == "UNKNOWN"


def test_missing_or_nonboolean_fit_and_arbitrage_proof_is_unknown():
    mutations = [
        lambda s: s.pop("fit_ok"),
        lambda s: s.pop("arbitrage"),
        lambda s: s["arbitrage"].pop("checked"),
        lambda s: s["arbitrage"].pop("passed"),
    ]
    for value in (None, False, 1, "true"):
        mutations.extend((
            lambda s, value=value: s.update(fit_ok=value),
            lambda s, value=value: s["arbitrage"].update(checked=value),
            lambda s, value=value: s["arbitrage"].update(passed=value),
        ))
    for mutate in mutations:
        s = state()
        s["atm"]["front"]["implied_volatility"] = 0.145
        mutate(s)
        out = evaluate(s)
        assert out["session_vrp_state"] == "UNKNOWN", out
        assert out["reasons"]


def test_malformed_state_and_nested_objects_return_unknown_without_crashing():
    for malformed in (None, [], "invalid", 1, False):
        assert evaluate(malformed)["session_vrp_state"] == "UNKNOWN"
        for key in ("verdict", "health", "forecast", "atm", "arbitrage"):
            s = state()
            s["atm"]["front"]["implied_volatility"] = 0.145
            s[key] = malformed
            assert evaluate(s)["session_vrp_state"] == "UNKNOWN"
        s = state()
        s["atm"]["front"] = malformed
        assert evaluate(s)["session_vrp_state"] == "UNKNOWN"
