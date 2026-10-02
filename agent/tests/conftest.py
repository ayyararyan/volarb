"""Each test is a new configuration-loading process in production semantics."""

import pytest

from butterfly_lab.settings import clear_settings_cache


@pytest.fixture(autouse=True)
def isolated_settings_cache():
    clear_settings_cache()
    yield
    clear_settings_cache()
