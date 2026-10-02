import json

import pytest

from butterfly_lab.providers import (
    FixtureProvider,
    OpenAIConfig,
    OpenAIProvider,
    ProviderBudgetExceeded,
    ProviderError,
    ReplayProvider,
    digest,
)


def config(tmp_path, **kwargs):
    defaults = dict(
        model="operator-selected-model",
        ledger_path=tmp_path / "provider-ledger.json",
        approved=True,
        max_calls=2,
        max_cost_usd=1,
        input_usd_per_million=1,
        output_usd_per_million=2,
    )
    return OpenAIConfig(**(defaults | kwargs))


def response(content=None):
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps(content or {"notes": ["bounded"]})},
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10},
    }


def test_real_adapter_contract_and_persistent_reservation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    calls = []

    def transport(url, headers, body, timeout):
        calls.append((url, headers, json.loads(body), timeout))
        return response()

    cfg = config(tmp_path)
    result = OpenAIProvider(cfg, transport=transport).generate("critic", {"question": "finite"})
    assert result.source == "real_model"  # contract transport, not live service evidence
    assert result.input_tokens == 50
    assert calls[0][2]["response_format"] == {"type": "json_object"}
    assert calls[0][2]["max_completion_tokens"] == cfg.max_output_tokens
    assert calls[0][1]["Authorization"] == "Bearer test-only-key"
    assert "test-only-key" not in cfg.ledger_path.read_text()
    OpenAIProvider(cfg, transport=transport).generate("critic", {})
    with pytest.raises(ProviderBudgetExceeded):
        OpenAIProvider(cfg, transport=transport).generate("critic", {})
    assert len(calls) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"approved": False},
        {"max_cost_usd": 0},
        {"input_usd_per_million": 0},
        {"max_cost_usd": 1e-9},
    ],
)
def test_unapproved_or_insufficient_live_budget_never_calls(tmp_path, monkeypatch, changes):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    called = []
    provider = OpenAIProvider(
        config(tmp_path, **changes), transport=lambda *args: called.append(args)
    )
    with pytest.raises(ProviderBudgetExceeded):
        provider.generate("critic", {})
    assert not called


def test_missing_credentials_blocks_without_reservation(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = config(tmp_path)
    with pytest.raises(ProviderError, match="credential"):
        OpenAIProvider(cfg).generate("critic", {})
    assert not cfg.ledger_path.exists()


def test_failed_or_malformed_response_retains_reservation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    cfg = config(tmp_path, max_calls=1)
    with pytest.raises(ProviderError):
        OpenAIProvider(cfg, transport=lambda *args: {"choices": []}).generate("critic", {})
    with pytest.raises(ProviderBudgetExceeded):
        OpenAIProvider(cfg, transport=lambda *args: response()).generate("critic", {})


def test_refusal_and_token_usage_over_bound_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    refusal = response()
    refusal["choices"][0]["finish_reason"] = "length"
    with pytest.raises(ProviderError, match="Incomplete"):
        OpenAIProvider(config(tmp_path), transport=lambda *args: refusal).generate("critic", {})
    huge = response()
    huge["usage"]["completion_tokens"] = 10**8
    with pytest.raises(ProviderError, match="above reserved"):
        OpenAIProvider(config(tmp_path), transport=lambda *args: huge).generate("critic", {})


def test_protocol_url_cannot_embed_credentials_or_use_plaintext(tmp_path):
    for url in ("http://example.org/v1", "https://user:secret@example.org/v1"):
        with pytest.raises(ValueError):
            config(tmp_path, base_url=url)


def test_replay_and_fixture_are_separately_labelled_and_hash_bound():
    fixture = FixtureProvider({"critic": {"notes": ["synthetic"]}})
    f = fixture.generate("critic", {"x": 1})
    assert f.source == "synthetic_fixture"
    replay = ReplayProvider(
        [
            {
                "prompt_hash": f.prompt_hash,
                "payload": f.payload,
                "response_hash": f.response_hash,
                "model": "recorded-model",
            }
        ]
    )
    assert replay.generate("critic", {"x": 1}).source == "recorded_replay"
    with pytest.raises(ProviderError):
        replay.generate("critic", {"x": 2})
    corrupt = ReplayProvider(
        [{"prompt_hash": f.prompt_hash, "payload": f.payload, "response_hash": digest({})}]
    )
    with pytest.raises(ProviderError, match="hash"):
        corrupt.generate("critic", {"x": 1})


def test_api_campaign_call_ceiling_is_scoped_but_currency_ceiling_is_global(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    provider = OpenAIProvider(config(tmp_path, max_calls=1), transport=lambda *a: response())
    provider.bind_campaign_budget("first", 0.1, 10000)
    provider.generate("steward", {})
    with pytest.raises(ProviderBudgetExceeded):
        provider.generate("steward", {})
    provider.bind_campaign_budget("second", 0.1, 10000)
    assert provider.generate("steward", {}).billing_kind == "api_usd"
    assert json.loads(provider.config.ledger_path.read_text())["calls"] == 2


def test_direct_api_config_rejects_header_injection_without_echoing_secret(tmp_path):
    from pydantic import SecretStr

    secret = "synthetic-private\nheader"
    with pytest.raises(ValueError) as error:
        config(tmp_path, api_key=SecretStr(secret))
    assert secret not in str(error.value)
