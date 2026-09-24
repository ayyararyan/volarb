#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from evaluate_overnight_carry import evaluate


def stress(same, p15, p20=-600.0):
    return {
        'same_state_open_pnl_points': same,
        'full_reprice': True,
        'stress_scenarios': [
            {'straddle_multiple': 1.0, 'direction': 'down', 'pnl_points': -100.0},
            {'straddle_multiple': 1.0, 'direction': 'up', 'pnl_points': -90.0},
            {'straddle_multiple': 1.5, 'direction': 'down', 'pnl_points': p15},
            {'straddle_multiple': 1.5, 'direction': 'up', 'pnl_points': p15 + 20.0},
            {'straddle_multiple': 2.0, 'direction': 'down', 'pnl_points': p20},
            {'straddle_multiple': 2.0, 'direction': 'up', 'pnl_points': p20 + 30.0},
        ],
    }


def benign_gap_gate():
    return {
        'required': True,
        'source': 'synthetic benign regime',
        'reference_spot': 23000.0,
        'net_gamma': -0.0005,
        'nearest_break_even_buffer_points': 400.0,
        'gap_pct': [
            -0.12, 0.08, -0.18, 0.15, -0.05, 0.20, -0.10, 0.16, -0.07, 0.11,
            -0.14, 0.09, -0.22, 0.17, -0.06, 0.13, -0.19, 0.04, 0.10, -0.15,
        ],
    }


def base():
    return {
        'mode': 'rotation_entry',
        'crosses_market_close': True,
        'expiry_sessions_remaining': 1,
        'market_actionable': True,
        'events': [{'severity': 'medium', 'inside_untradeable_window': True}],
        'market_regime': {'state': 'CALM_CARRY'},
        'empirical_gap_gate': benign_gap_gate(),
    }


def test_sensex_20260923_rotation_blocked_without_broker_validation():
    x = base() | stress(250.0, -300.0)
    x['broker'] = {'status': 'UNKNOWN', 'auto_squareoff_warning': False}
    out = evaluate(x)
    assert out['operational_state'] == 'BLOCK'
    assert 'new_expiry_eve_entry_requires_broker_pass' in out['hard_failures']


def test_high_latency_event_requires_stronger_stress_efficiency():
    x = base() | stress(200.0, -300.0)
    x['broker'] = {'status': 'PASS'}
    x['events'] = [{'severity': 'high', 'inside_untradeable_window': True}]
    out = evaluate(x)
    assert out['operational_state'] == 'BLOCK'
    assert 'high_latency_event_stress_efficiency_fail' in out['hard_failures']


def test_benign_validated_case_can_remain_eligible():
    x = base() | stress(240.0, -300.0)
    x['broker'] = {'status': 'PASS'}
    x['events'] = [{'severity': 'low', 'inside_untradeable_window': True}]
    out = evaluate(x)
    assert out['operational_state'] == 'CARRY_ELIGIBLE'
    assert not out['hard_failures']


def test_auto_squareoff_warning_blocks_actionable_carry():
    x = base() | stress(300.0, -250.0)
    x['broker'] = {'status': 'WARN', 'auto_squareoff_warning': True}
    out = evaluate(x)
    assert out['operational_state'] == 'BLOCK'
    assert 'broker_rms_warning' in out['hard_failures']


def test_postclose_is_locked_not_fresh_carry_decision():
    x = base() | stress(300.0, -250.0)
    x['market_actionable'] = False
    x['broker'] = {'status': 'UNKNOWN'}
    out = evaluate(x)
    assert out['operational_state'] == 'LOCKED_OVERNIGHT'



def test_recent_nifty_gap_regime_blocks_tight_break_even_buffer():
    x = base() | stress(240.0, -200.0)
    x['broker'] = {'status': 'PASS'}
    x['events'] = [{'severity': 'low', 'inside_untradeable_window': True}]
    x['empirical_gap_gate'] = {
        'required': True,
        'source': 'NIFTY opens 2026-08-25 through 2026-09-24',
        'reference_spot': 23200.0,
        'net_gamma': -0.00109,
        'nearest_break_even_buffer_points': 181.5,
        'gap_pct': [
            -0.1788, 0.0304, 0.2885, 0.1318, -0.2403, -0.0118, -0.8223,
            0.3492, 0.1569, -0.0609, -0.1516, -0.4783, 0.0644, -0.8838,
            0.7610, 0.3590, -0.0963, 0.2755, -0.0694, 0.1698, 0.0992, -0.9596,
        ],
    }
    out = evaluate(x)
    assert out['operational_state'] == 'BLOCK'
    assert 'recent_q90_gap_exceeds_break_even_buffer' in out['hard_failures']
    assert out['empirical_gap']['sample_size'] == 22
    assert out['empirical_gap']['p90_abs_gap_pct'] > 0.80


def test_empirical_gap_gamma_can_block_even_when_stress_ocr_passes():
    x = base() | stress(3.0, -2.0, -3.0)
    x['broker'] = {'status': 'PASS'}
    x['events'] = [{'severity': 'low', 'inside_untradeable_window': True}]
    x['empirical_gap_gate'] = {
        'required': True,
        'reference_spot': 23000.0,
        'net_gamma': -0.0015,
        'nearest_break_even_buffer_points': 500.0,
        'gap_pct': [
            -0.45, 0.50, -0.40, 0.55, -0.48, 0.44, -0.52, 0.46, -0.43, 0.51,
            -0.49, 0.47, -0.54, 0.42, -0.50, 0.45, -0.41, 0.53, -0.46, 0.48,
        ],
    }
    out = evaluate(x)
    assert out['operational_state'] == 'BLOCK'
    assert 'empirical_gap_gamma_exceeds_same_state_harvest' in out['hard_failures']


def test_new_overnight_entry_requires_recent_gap_history():
    x = base() | stress(240.0, -200.0)
    x['broker'] = {'status': 'PASS'}
    x['events'] = [{'severity': 'low', 'inside_untradeable_window': True}]
    x['empirical_gap_gate'] = {'required': True, 'gap_pct': [0.1, -0.1]}
    out = evaluate(x)
    assert out['operational_state'] == 'BLOCK'
    assert 'insufficient_recent_gap_history' in out['hard_failures']

def run():
    tests = [v for k, v in globals().items() if k.startswith('test_') and callable(v)]
    for t in tests:
        t()
        print('PASS', t.__name__)
    print(f'{len(tests)} tests passed')


if __name__ == '__main__':
    run()
