"""Provider-neutral prevention of accidental configuration/credential prompt inputs."""

import pytest

from butterfly_lab.agents import _safe_context
from butterfly_lab.settings import Settings


@pytest.mark.parametrize(
    "key",
    [
        "OPENAI_API_KEY",
        "apiKey",
        "authorization",
        "Authorization-Key",
        "signing_key",
        "CODEx_AUTH_PATH",
        "accessToken",
        "refreshToken",
        "oauthCredentials",
        "provider-config",
        "runtimeSettings",
        "environment_variables",
        "env_contents",
        "BUTTERFLY_CODEX_COMMAND",
        "config_path",
        "credentials_path",
    ],
)
def test_secret_aliases_and_runtime_configuration_are_not_provider_inputs(key):
    secret = "synthetic-sensitive-test-string"
    with pytest.raises(PermissionError) as error:
        _safe_context({"source_records": [{key: secret}]})
    assert secret not in str(error.value)


def test_even_redacted_settings_do_not_enter_role_context():
    with pytest.raises(PermissionError):
        _safe_context({"nested": Settings().redacted()})


def test_scientific_definitions_and_token_budgets_remain_valid_inputs():
    _safe_context(
        {
            "campaign_id": "controlled",
            "budget": {"llm_tokens": 0, "llm_calls": 20},
            "config_hash": "scientific-content-hash",
            "capabilities": ["identified_contracts"],
            "source_records": [{"citation": "approved source", "partition": "development"}],
            "experiment": {"seed": 17, "costs": {"currency": "INR", "fee_per_contract": 1}},
        }
    )
