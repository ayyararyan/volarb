"""Offline regression checks for the bundled high-frequency RV scenarios.

Positive fixtures pin the expected short-gamma/drift states. Negative cases
prove that stale HF data, a missing news packet, a missing IV anchor and a
missing decision clock can never produce FAVOURABLE.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
scripts = root / 'skill/intraday-realized-volatility-forecast/scripts'
expected = {
    'stable': ('FAVOURABLE', 'LOW', False),
    'trend': ('UNFAVOURABLE', 'HIGH', True),
    'jump': ('MARGINAL', 'LOW', False),
    'mode_bucket_jump': ('FAVOURABLE', 'LOW', True),
}


def run(payload):
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as handle:
        json.dump(payload, handle)
        path = handle.name
    return json.loads(subprocess.check_output([
        sys.executable, str(scripts / 'forecast_intraday_rv.py'), '--input', path,
    ], text=True))


for name, states in expected.items():
    result = run(json.loads((scripts / f'test_{name}.json').read_text()))
    actual = tuple(result[key] for key in ('short_gamma_state', 'drift_risk', 'mode_bucket_warning'))
    assert actual == states, (name, actual, states)
    assert result['hf_quality'] == 'PASS', name
    assert result['news_packet_status'] == 'PRESENT', name
    assert result['upper_forecast_horizon_variance'] >= result['forecast_horizon_variance'] >= 0, name
    if name == 'jump':
        assert result['jump_count'] > 0
    print(f'{name}: PASS')

stable = json.loads((scripts / 'test_stable.json').read_text())

stale = copy.deepcopy(stable)
stale['asof'] = '2026-09-30T13:50:05+05:30'
result = run(stale)
assert result['short_gamma_state'] == 'INSUFFICIENT_DATA' and result['confidence'] == 'low', result
assert result['diagnostics']['freshness']['reason'] == 'HF_BLOCK_STALE', result['diagnostics']['freshness']
print('stale block rejected: PASS')

no_asof = copy.deepcopy(stable)
no_asof.pop('asof')
result = run(no_asof)
assert result['short_gamma_state'] == 'INSUFFICIENT_DATA', result
print('missing decision clock rejected against wall clock: PASS')

no_news = copy.deepcopy(stable)
no_news.pop('news_filter')
result = run(no_news)
assert result['short_gamma_state'] == 'MARGINAL' and result['news_packet_status'] == 'MISSING', result
print('missing news packet capped at MARGINAL: PASS')

no_iv = copy.deepcopy(stable)
no_iv['current'].pop('atm_iv')
result = run(no_iv)
assert result['status'] == 'INSUFFICIENT_DATA' and result['confidence'] == 'low', result
print('missing IV anchor is low-confidence insufficient data: PASS')

future = copy.deepcopy(stable)
future['asof'] = '2026-09-29T13:40:00+05:30'
result = run(future)
assert result['short_gamma_state'] == 'INSUFFICIENT_DATA', result
assert result['diagnostics']['freshness']['reason'] == 'HF_TIMESTAMPS_AHEAD_OF_ASOF', result['diagnostics']['freshness']
print('HF timestamps ahead of decision clock rejected: PASS')
