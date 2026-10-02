import numpy as np
import pandas as pd
import pytest

from butterfly_lab.data import load_dataset
from butterfly_lab.evaluators import evaluate, exp001_features, exp001_predictions
from butterfly_lab.fixtures import (
    default_ironfly_parameters,
    generate_option_fixture,
    generate_spot_fixture,
)


def exp(kind, params=None):
    return {
        "evaluator": kind,
        "parameters": params or {},
        "baseline_id": "B0-simple",
        "seed": 17,
        "inference": {"bootstrap_samples": 99, "minimum_sessions": 30},
    }


def test_exp001_end_to_end_independent_reconstruction_and_rerun(tmp_path):
    data = generate_spot_fixture(tmp_path / "spot.csv")
    e = exp("exp001")
    first = evaluate(e, data, tmp_path / "first")
    second = evaluate(e, data, tmp_path / "second")
    assert first == second
    assert first["replication"]["status"] == "PASS"
    assert first["metrics"]["n_sessions"] == 40
    assert first["metrics"]["eligible_sessions"] == 135
    assert first["outcome"] in {"REJECTED_FINDING", "INCONCLUSIVE", "EXPLORATORY_SUPPORTED"}
    assert "butterfly" not in first["metrics"]
    predictions = pd.read_parquet(tmp_path / "first/predictions.parquet")
    assert (predictions.training_label_cutoff < predictions.fit_at).all()
    assert (predictions.feature_available_at <= predictions.origin).all()


def test_future_perturbation_cannot_change_earlier_features_or_predictions(tmp_path):
    manifest = generate_spot_fixture(tmp_path / "spot.csv")
    frame = load_dataset(manifest)
    features, _ = exp001_features(frame, manifest)
    predictions = exp001_predictions(features, exp("exp001"))
    changed = frame.copy()
    changed.loc[changed.session >= "2025-03-01", "close"] *= 2
    new_features, _ = exp001_features(changed, manifest)
    new_predictions = exp001_predictions(new_features, exp("exp001"))
    pd.testing.assert_frame_equal(
        features[features.session < "2025-03-01"], new_features[new_features.session < "2025-03-01"]
    )
    pd.testing.assert_frame_equal(
        predictions[predictions.session < "2025-03-01"],
        new_predictions[new_predictions.session < "2025-03-01"],
    )


def test_missing_target_preserved_not_outcome_selected_and_floor(tmp_path):
    manifest = generate_spot_fixture(tmp_path / "spot.csv")
    frame = load_dataset(manifest)
    day = frame.session.iloc[0]
    missing = frame[
        ~(
            frame.session.eq(day)
            & frame.bar_end.dt.tz_convert("Asia/Kolkata").dt.strftime("%H:%M").eq("10:35")
        )
    ]
    features, ledger = exp001_features(missing, manifest)
    assert len(ledger) == 135
    assert ledger[ledger.session.eq(day)].status.iloc[0] == "MISSING_TARGET"
    zero = frame.copy()
    zero.loc[zero.session.eq(day), "close"] = 20000
    features, ledger = exp001_features(zero, manifest)
    first = features[features.session.eq(day)].iloc[0]
    assert first.drift == 0 and first.rv == 0 and first.excursion == 0
    assert np.isfinite(first.log_excursion) and first.degenerate_excursion


def test_frozen_exp001_clock_and_lag_requirements(tmp_path):
    data = generate_spot_fixture(tmp_path / "spot.csv")
    data["timestamp_convention_verified"] = False
    result = evaluate(exp("exp001"), data, tmp_path / "missing")
    assert result["outcome"] == "DATA_LIMITED"
    data["timestamp_convention_verified"] = True
    data["availability_lag_seconds"] = 0
    assert evaluate(exp("exp001"), data, tmp_path / "wrong_lag")["outcome"] == "DATA_LIMITED"


def test_fourleg_recenter_full_cycle_costs_same_opportunities(tmp_path):
    data = generate_option_fixture(tmp_path / "q.parquet", 3)
    result = evaluate(exp("iron_butterfly", default_ironfly_parameters()), data, tmp_path / "out")
    assert result["replication"]["status"] == "PASS"
    fills = pd.read_parquet(tmp_path / "out/fills.parquet")
    opportunities = pd.read_parquet(tmp_path / "out/opportunities.parquet")
    assert len(opportunities) == 9
    assert set(opportunities.policy) == {"hold", "close", "recenter"}
    for _, cycle in fills[fills.policy.eq("recenter")].groupby("cycle_id"):
        assert len(cycle) == 16
        assert cycle.fees.sum() == 16
        assert cycle.groupby("contract_id").units.sum().eq(0).all()
    assert opportunities[opportunities.policy.eq("recenter")].pnl_inr.sum() == pytest.approx(
        fills[fills.policy.eq("recenter")].cashflow.sum()
    )


def test_missing_exit_withholds_metrics_never_complete_case(tmp_path):
    data = generate_option_fixture(tmp_path / "q.parquet", 3)
    rows = pd.read_parquet(tmp_path / "q.parquet")
    # All quotes after 10:29 on the final session are absent; session persists.
    last = rows.event_at.str[:10].max()
    keep = ~((rows.event_at.str[:10] == last) & (rows.event_at.str[11:16] >= "10:30"))
    rows[keep].to_parquet(tmp_path / "missing.parquet")
    data.update(source_path=str(tmp_path / "missing.parquet"), source_sha256=None)
    parameters = {**default_ironfly_parameters(), "management": "hold"}
    result = evaluate(exp("iron_butterfly", parameters), data, tmp_path / "out")
    assert result["outcome"] == "DATA_LIMITED"
    assert result["metrics"]["unresolved_opportunities"] == 1
    ledger = pd.read_parquet(tmp_path / "out/opportunities.parquet")
    assert len(ledger) == 3 and ledger.pnl_inr.isna().sum() == 1
    assert "baseline_mean_pnl_inr" not in result["metrics"]


def test_non_b0_uses_recorded_selection_not_simple_atm_substitution(tmp_path):
    from butterfly_lab.baselines import baseline_golden_cases

    data = generate_option_fixture(tmp_path / "q.parquet", 1)
    packet = baseline_golden_cases("B-policy")[-1]["packet"]
    legs = [
        {"contract_id": f"FIXTURE:NIFTY:2025-12-30:{strike}:{kind}", "signed_lots": sign}
        for strike, kind, sign in [
            (10000, "PE", 1),
            (10500, "PE", -1),
            (10500, "CE", -1),
            (11000, "CE", 1),
        ]
    ]
    packet["entry_selection"] = {
        "selection_policy_id": "recorded-wide-overlay-fixture",
        "available_at": "2025-01-02T09:59:00+05:30",
        "legs": legs,
    }
    data["metadata"]["policy_packets"] = {"2025-01-02": packet}
    experiment = {
        **exp("iron_butterfly", {**default_ironfly_parameters(), "management": "hold"}),
        "baseline_id": "B-policy",
    }
    result = evaluate(experiment, data, tmp_path / "observed")
    assert result["replication"]["status"] == "PASS"
    fills = pd.read_parquet(tmp_path / "observed/fills.parquet")
    assert set(fills[fills.reason.eq("entry")].contract_id) == {x["contract_id"] for x in legs}
    packet["entry_selection"]["available_at"] = "2025-01-02T10:01:00+05:30"
    assert evaluate(experiment, data, tmp_path / "future")["outcome"] == "DATA_LIMITED"
    del packet["entry_selection"]
    assert evaluate(experiment, data, tmp_path / "absent")["outcome"] == "DATA_LIMITED"


@pytest.mark.parametrize("baseline_id", ["B-policy", "B-as-observed"])
def test_missing_historical_gate_packets_are_not_zero_pnl(baseline_id, tmp_path):
    data = generate_option_fixture(tmp_path / "q.parquet", 1)
    experiment = {
        **exp("iron_butterfly", {**default_ironfly_parameters(), "management": "hold"}),
        "baseline_id": baseline_id,
    }
    result = evaluate(experiment, data, tmp_path / "out")
    assert result["outcome"] == "DATA_LIMITED"
    assert "baseline_mean_pnl_inr" not in result.get("metrics", {})


def test_partial_protective_fill_aborts_before_short_sale(tmp_path):
    data = generate_option_fixture(tmp_path / "q.parquet", 1)
    rows = pd.read_parquet(tmp_path / "q.parquet")
    rows.loc[rows.event_at.str[11:16].eq("10:00"), "ask_size"] = 3
    rows.to_parquet(tmp_path / "partial.parquet")
    data.update(source_path=str(tmp_path / "partial.parquet"), source_sha256=None)
    result = evaluate(
        exp("iron_butterfly", {**default_ironfly_parameters(), "management": "hold"}),
        data,
        tmp_path / "out",
    )
    assert result["replication"]["status"] == "PASS"
    fills = pd.read_parquet(tmp_path / "out/fills.parquet")
    assert len(fills) == 2 and fills.units.tolist() == [3, -3]
    assert fills.reason.tolist() == ["entry", "abort_partial_entry"]
    assert result["metrics"]["candidate_mean_pnl_inr"] < 0


def test_latency_uses_later_observation_and_capital_shared(tmp_path):
    data = generate_option_fixture(tmp_path / "q.parquet", 1)
    params = {
        **default_ironfly_parameters(),
        "management": "hold",
        "latency_seconds": 1,
        "opportunities": [
            {"session": "2025-01-02", "entry": "10:00:00", "id": "one"},
            {"session": "2025-01-02", "entry": "10:01:00", "id": "overlap"},
        ],
    }
    evaluate(exp("iron_butterfly", params), data, tmp_path / "out")
    fills = pd.read_parquet(tmp_path / "out/fills.parquet")
    assert fills.timestamp.str[11:16].iloc[0] == "04:31"  # UTC; 10:01 IST
    ledger = pd.read_parquet(tmp_path / "out/opportunities.parquet")
    assert ledger.reason.tolist()[1] == "deadline_or_overlapping_exposure"
    params.update(capital_inr=9999, opportunities=None)
    evaluate(exp("iron_butterfly", params), data, tmp_path / "no_capital")
    assert (
        pd.read_parquet(tmp_path / "no_capital/opportunities.parquet").reason.iloc[0]
        == "capital_or_peak_margin"
    )


@pytest.mark.parametrize(
    "kind,fidelity,provenance",
    [("option_quotes", "F3", "REPLAY"), ("option_bars", "F2", "HISTORICAL")],
)
def test_real_contract_input_paths_exercised_on_explicit_test_fixtures(
    tmp_path, kind, fidelity, provenance
):
    data = generate_option_fixture(tmp_path / "q.parquet", 1)
    data.update(kind=kind, fidelity=fidelity, provenance=provenance)
    params = {**default_ironfly_parameters(), "management": "hold"}
    if kind == "option_bars":
        rows = pd.read_parquet(tmp_path / "q.parquet")
        rows["close"] = (rows.bid + rows.ask) / 2
        rows["open"] = rows["high"] = rows["low"] = rows.close
        rows = rows.drop(columns=["bid", "ask", "bid_size", "ask_size"])
        rows.to_parquet(tmp_path / "bars.parquet")
        data.update(source_path=str(tmp_path / "bars.parquet"), source_sha256=None, bar_label="end")
        params.update(
            bar_fill="available_close_adverse_spread",
            assumed_spread_points=0.5,
            assumed_size_units=100,
        )
    result = evaluate(
        {**exp("iron_butterfly", params), "fidelity": fidelity}, data, tmp_path / "out"
    )
    assert result["outcome"] != "DATA_LIMITED", result
    assert result["fidelity"] == fidelity
    assert result["replication"]["status"] == "PASS"


def test_model_f1_fourleg_path_is_real_calculation(tmp_path):
    dates = pd.date_range("2025-01-02T10:00:00+05:30", periods=32, freq="min")
    contracts = [
        {
            "contract_id": f"MODEL-{strike}-{typ}",
            "underlying": "NIFTY",
            "expiry": "2025-01-30",
            "strike": strike,
            "option_type": typ,
            "lot_size": 10,
        }
        for strike in [9500, 10000, 10500]
        for typ in ["CE", "PE"]
    ]
    prototype = generate_option_fixture(tmp_path / "q.parquet", 1)
    data = {
        "id": "model",
        "kind": "model",
        "fidelity": "F1",
        "provenance": "MODEL",
        "availability_lag_seconds": 0,
        "metadata": {
            **prototype["metadata"],
            "rows": [{"event_at": x.isoformat(), "spot": 10000, "iv": 0.15} for x in dates],
            "contracts": contracts,
            "model_spread": 0.5,
        },
    }
    result = evaluate(
        {
            **exp("iron_butterfly", {**default_ironfly_parameters(), "management": "hold"}),
            "fidelity": "F1",
        },
        data,
        tmp_path / "out",
    )
    assert result["outcome"] != "DATA_LIMITED", result
    assert result["provenance"] == "MODEL"
    assert result["replication"]["status"] == "PASS"


def test_unknown_fees_and_lots_block_before_economics(tmp_path):
    data = generate_option_fixture(tmp_path / "q.parquet", 1)
    data["metadata"].pop("fee_schedule")
    result = evaluate(exp("iron_butterfly", default_ironfly_parameters()), data, tmp_path / "out")
    assert result["outcome"] == "DATA_LIMITED"
    assert result["metrics"] == {}


def test_controlled_negative_and_planted_positive_terminate(tmp_path):
    dataset = {
        "kind": "synthetic",
        "fidelity": "F0",
        "provenance": "SYNTHETIC",
        "metadata": {"generator": "controlled_session_panel_v1"},
    }
    null = evaluate(
        exp("controlled", {"noise": 0, "effect": 0, "n_sessions": 100}), dataset, tmp_path / "null"
    )
    positive = evaluate(
        exp("controlled", {"noise": 0.01, "effect": 0.1, "n_sessions": 100}),
        dataset,
        tmp_path / "positive",
    )
    assert null["outcome"] == "REJECTED_FINDING"
    assert positive["outcome"] == "EXPLORATORY_SUPPORTED"
    assert null["replication"]["status"] == positive["replication"]["status"] == "PASS"
