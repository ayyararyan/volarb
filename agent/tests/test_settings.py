from __future__ import annotations

import json
from pathlib import Path

import pytest

from butterfly_lab.settings import (
    ConfigurationError,
    ENV_FIELDS,
    clear_settings_cache,
    get_settings,
    load_settings,
)


def config(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text)
    return path


def test_dotenv_quotes_comments_types_and_shell_precedence(tmp_path):
    path = config(
        tmp_path,
        "# comments\nexport BUTTERFLY_LLM_PROVIDER='fixture'\n"
        'BUTTERFLY_CODEX_MODEL="test-model" # comment\n'
        "BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN=7\n"
        "BUTTERFLY_LAB_HOME=private-runtime\n"
        "OPENAI_API_KEY='synthetic-$VALUE-$(no-execution)#literal'\n",
    )
    value = load_settings(path, environ={"BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN": "9"})
    assert value.llm_provider == "fixture"
    assert value.llm_max_calls_per_campaign == 9
    assert value.codex_model == "test-model"
    assert value.lab_home == tmp_path / "private-runtime"
    assert value.openai_api_key.get_secret_value() == "synthetic-$VALUE-$(no-execution)#literal"
    assert not value.lab_home.exists()  # Config inspection cannot create runtime state.


def test_safe_defaults_and_empty_fields(tmp_path):
    value = load_settings(
        config(tmp_path, "BUTTERFLY_LAB_HOME=\nBUTTERFLY_CODEX_MODEL=\n"), environ={}
    )
    assert value.llm_provider == "codex"
    assert value.codex_model is None
    assert value.openai_api_key is None
    assert value.openai_max_cost_usd == 0
    assert value.numerical_workers == 2
    assert value.llm_max_calls_per_campaign == 40


def test_all_template_fields_load_without_a_key():
    path = Path(__file__).parents[1] / ".env.example"
    value = load_settings(path, environ={})
    assert value.llm_provider == "codex"
    assert value.openai_api_key is None
    assigned = {
        line.split("=", 1)[0]
        for line in path.read_text().splitlines()
        if line and not line.startswith("#")
    }
    assert assigned == set(ENV_FIELDS)


def test_shell_blank_explicitly_clears_file_secret(tmp_path):
    value = load_settings(
        config(tmp_path, "OPENAI_API_KEY='synthetic-value'\n"), environ={"OPENAI_API_KEY": ""}
    )
    assert value.openai_api_key is None


def test_explicit_override_and_project_location(tmp_path):
    project = tmp_path / "agent"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname="butterfly-research-lab"\n')
    selected = config(project, "BUTTERFLY_LLM_PROVIDER=fixture\n")
    child = project / "tests"
    child.mkdir()
    assert load_settings(environ={}, cwd=child).config_path == selected
    alternate = tmp_path / "alternate.env"
    alternate.write_text("BUTTERFLY_LLM_PROVIDER=codex\n")
    assert (
        load_settings(environ={"BUTTERFLY_ENV_FILE": str(alternate)}, cwd=child).llm_provider
        == "codex"
    )
    assert (
        load_settings(selected, environ={"BUTTERFLY_ENV_FILE": str(alternate)}).llm_provider
        == "fixture"
    )


def test_unrelated_parent_dotenv_is_not_loaded(tmp_path):
    config(tmp_path, "OPENAI_API_KEY=unrelated-parent-secret\n")
    child = tmp_path / "elsewhere"
    child.mkdir()
    value = load_settings(environ={}, cwd=child)
    assert value.config_path != tmp_path / ".env"
    assert value.openai_api_key is None


def test_missing_explicit_file_fails_without_path_disclosure(tmp_path):
    path = tmp_path / "private-auth-secret-name.env"
    with pytest.raises(ConfigurationError) as error:
        load_settings(path, environ={})
    assert str(path) not in str(error.value)
    assert "does not exist" in str(error.value)


@pytest.mark.parametrize(
    "text,reason",
    [
        ("BUTTERFLY_LLM_PROVIDER=wrong\n", "llm_provider"),
        ("BUTTERFLY_CODEX_MODE=external\n", "codex_mode"),
        ("BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN=0\n", "llm_max_calls_per_campaign"),
        ("BUTTERFLY_CODEX_REQUEST_TIMEOUT_SECONDS=nan\n", "codex_request_timeout_seconds"),
        ("BUTTERFLY_PENDING_JOB_LIMIT=1\n", "pending_job_limit"),
        ("BUTTERFLY_LLM_PROVIDER=replay\n", "BUTTERFLY_REPLAY_PATH"),
        ("BUTTERFLY_LLM_PROVIDER=openai\n", "OPENAI_API_KEY"),
        ("BUTTERFLY_NUMERICAL_WORKERS=20\n", "numerical_workers"),
        ("BUTTERFLY_OPENAI_BASE_URL=https://synthetic:secret@example.invalid\n", "openai_base_url"),
        ("BUTTERFLY_UNKNOWN=hidden\n", "Unsupported"),
        ("OPENAI_API_KEY=first\nOPENAI_API_KEY=second\n", "Duplicate"),
        ("OPENAI_API_KEY='unterminated\n", "Unterminated"),
        ("OPENAI_API_KEY='value' trailing\n", "quoted value"),
        ("not an assignment\n", "assignment"),
        ("DHAN_CLIENT_ID=wrong-system\n", "Unsupported"),
        ('OPENAI_API_KEY="synthetic\\nsecret"\n', "control characters"),
    ],
)
def test_invalid_configuration_fails_closed(tmp_path, text, reason):
    with pytest.raises(ConfigurationError, match=reason):
        load_settings(config(tmp_path, text), environ={})


def test_api_provider_requires_explicit_prices_budget_and_model(tmp_path):
    path = config(
        tmp_path,
        "BUTTERFLY_LLM_PROVIDER=openai\nOPENAI_API_KEY=synthetic-test-only\n"
        "BUTTERFLY_OPENAI_MODEL=test-model\n",
    )
    with pytest.raises(ConfigurationError, match="budget"):
        load_settings(path, environ={})
    value = load_settings(
        path,
        environ={
            "BUTTERFLY_OPENAI_MAX_COST_USD": "0.05",
            "BUTTERFLY_OPENAI_INPUT_USD_PER_MILLION": "1.0",
            "BUTTERFLY_OPENAI_OUTPUT_USD_PER_MILLION": "2.0",
        },
    )
    assert value.openai_max_cost_usd == 0.05


def test_unknown_double_quoted_escapes_are_not_silently_removed(tmp_path):
    value = load_settings(config(tmp_path, 'OPENAI_API_KEY="synthetic\\qtest"\n'), environ={})
    assert value.openai_api_key.get_secret_value() == "synthetic\\qtest"


def test_secrets_are_redacted_in_repr_json_and_errors(tmp_path):
    secret = "synthetic-sensitive-test-value"
    path = config(tmp_path, f"OPENAI_API_KEY={secret}\n")
    value = load_settings(path, environ={})
    assert secret not in repr(value)
    assert secret not in value.model_dump_json()
    assert secret not in json.dumps(value.redacted())
    assert value.redacted()["openai_api_key"] == "[REDACTED]"
    with pytest.raises(ConfigurationError) as error:
        load_settings(path, environ={"BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN": secret})
    assert secret not in str(error.value)
    with pytest.raises(ConfigurationError) as error:
        load_settings(path, environ={"BUTTERFLY_" + secret: secret})
    assert secret not in str(error.value)


def test_configuration_is_loaded_once_until_explicit_reload(tmp_path, monkeypatch):
    clear_settings_cache()
    for key in list(__import__("os").environ):
        if key.startswith("BUTTERFLY_") or key == "OPENAI_API_KEY":
            monkeypatch.delenv(key)
    path = config(tmp_path, "BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN=7\n")
    first = get_settings(path)
    path.write_text("BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN=8\n")
    assert get_settings(path) is first
    assert first.llm_max_calls_per_campaign == 7
    clear_settings_cache()
    assert get_settings(path).llm_max_calls_per_campaign == 8
    clear_settings_cache()
