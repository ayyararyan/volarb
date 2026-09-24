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


def base():
    return {
        'mode': 'rotation_entry',
        'crosses_market_close': True,
        'expiry_sessions_remaining': 1,
        'market_actionable': True,
        'events': [{'severity': 'medium', 'inside_untradeable_window': True}],
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


def run():
    tests = [v for k, v in globals().items() if k.startswith('test_') and callable(v)]
    for t in tests:
        t()
        print('PASS', t.__name__)
    print(f'{len(tests)} tests passed')


if __name__ == '__main__':
    run()
