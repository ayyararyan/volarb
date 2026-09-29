"""Offline regression checks for the bundled high-frequency RV scenarios."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
scripts = root / 'skill/intraday-realized-volatility-forecast/scripts'
expected = {
    'stable': ('FAVOURABLE', 'LOW', False),
    'trend': ('UNFAVOURABLE', 'HIGH', True),
    'jump': ('MARGINAL', 'LOW', False),
    'mode_bucket_jump': ('FAVOURABLE', 'LOW', True),
}
for name, states in expected.items():
    result = json.loads(subprocess.check_output([
        sys.executable, str(scripts / 'forecast_intraday_rv.py'),
        '--input', str(scripts / f'test_{name}.json'),
    ], text=True))
    actual = tuple(result[key] for key in ('short_gamma_state', 'drift_risk', 'mode_bucket_warning'))
    assert actual == states, (name, actual, states)
    assert result['hf_quality'] == 'PASS', name
    assert result['upper_forecast_horizon_variance'] >= result['forecast_horizon_variance'] >= 0, name
    if name == 'jump':
        assert result['jump_count'] > 0
    print(f'{name}: PASS')
