import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import signal

import pytest

from butterfly_lab.codex_provider import CodexAppServerProvider, CodexConfig
from butterfly_lab.providers import ProviderBudgetExceeded, ProviderError

FIXTURE = Path(__file__).parent / "fixtures" / "fake_codex_server.py"
SCHEMA = {
    "type": "object",
    "properties": {"notes": {"type": "array", "items": {"type": "string"}}},
    "required": ["notes"],
    "additionalProperties": False,
}


def config(tmp_path, scenario="normal", **values):
    executable = tmp_path / (scenario + "-codex")
    shutil.copyfile(FIXTURE, executable)
    executable.chmod(0o700)
    return CodexConfig(
        **(
            {
                "command": str(executable),
                "ledger_path": tmp_path / "codex-ledger.json",
                "startup_timeout_seconds": 2,
                "request_timeout_seconds": 2,
            }
            | values
        )
    )


def test_real_stdio_handshake_status_generation_and_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-codex")
    cfg = config(tmp_path)
    provider = CodexAppServerProvider(cfg)
    with provider:
        status = provider.status()
        assert status == {
            "provider": "codex",
            "authentication_mode": "chatgpt",
            "rate_limits": {
                "available": True,
                "primary": {
                    "used_percent": 1,
                    "window_minutes": 300,
                    "resets_at_unix_seconds": 2000000000,
                },
                "secondary": None,
            },
            "installed": True,
            "authenticated": True,
            "reachable": True,
            "model_available": True,
            "usable": True,
            "version": "0.149.1",
            "reason": None,
        }
        assert not cfg.ledger_path.exists()  # diagnostics do not make model calls
        first_pid = provider.process_id
        response = provider.generate("critic", {"question": "bounded"}, schema=SCHEMA)
        assert response.payload == {"notes": ["bounded"]}
        assert response.billing_kind == "subscription"
        assert response.reserved_cost_usd is None
        assert response.source == "real_model"  # fake transport, not live service evidence
        assert response.model == "fixture-model"
        assert response.input_tokens == 100 and response.output_tokens == 10
        assert "OPENAI_API_KEY" not in provider._environment()
        second = provider.generate("synthesis", {}, schema=SCHEMA)
        assert second.metadata["thread_id"] != response.metadata["thread_id"]
        assert provider.process_id == first_pid
    assert provider.process_id is None
    with pytest.raises(ProcessLookupError):
        os.kill(first_pid, 0)
    text = cfg.ledger_path.read_text()
    assert "must-not-reach-codex" not in text and "bounded" not in text
    assert json.loads(text)["calls"] == 2


@pytest.mark.parametrize(
    "scenario,match",
    [
        ("unauthenticated", "ChatGPT"),
        ("apikey", "ChatGPT"),
        ("unsafe", "security"),
        ("stubbornmcp", "MCP"),
    ],
)
def test_auth_and_security_failure_never_falls_back_or_spends(tmp_path, scenario, match):
    cfg = config(tmp_path, scenario)
    with CodexAppServerProvider(cfg) as provider:
        with pytest.raises(ProviderError, match=match):
            provider.generate("critic", {}, schema=SCHEMA)
    assert not cfg.ledger_path.exists()


def test_inherited_mcp_is_explicitly_disabled_before_turn(tmp_path):
    with CodexAppServerProvider(config(tmp_path, "mcp")) as provider:
        assert provider.generate("critic", {}, schema=SCHEMA).payload["notes"]


@pytest.mark.parametrize(
    "scenario,match",
    [
        ("malformed", "malformed JSON"),
        ("timeout", "timed out"),
        ("crash", "crashed"),
        ("tool", "forbidden tool"),
        ("permission", "forbidden tool"),
        ("ratelimit", "usage limit"),
        ("overflow", "output-token"),
        ("oversized", "ceiling"),
    ],
)
def test_failures_reap_and_retain_call_reservation(tmp_path, scenario, match):
    cfg = config(tmp_path, scenario, request_timeout_seconds=0.2, max_calls=1)
    provider = CodexAppServerProvider(cfg)
    with pytest.raises(ProviderError, match=match):
        provider.generate("critic", {}, schema=SCHEMA)
    assert provider.process_id is None
    state = json.loads(cfg.ledger_path.read_text())
    assert state["calls"] == 1
    assert state["reservations"][0]["status"] == "FAILED_OR_AMBIGUOUS_RESERVATION_RETAINED"
    with pytest.raises(ProviderBudgetExceeded):
        provider.generate("critic", {}, schema=SCHEMA)
    provider.close()


def test_missing_binary_model_unavailable_start_timeout(tmp_path):
    with CodexAppServerProvider(
        CodexConfig(command="butterfly-no-such-codex", ledger_path=tmp_path / "absent.json")
    ) as provider:
        assert not provider.status()["installed"]
        with pytest.raises(ProviderError, match="not installed"):
            provider.generate("critic", {})
    with CodexAppServerProvider(config(tmp_path, model="missing")) as provider:
        assert not provider.status()["model_available"]
        with pytest.raises(ProviderError, match="model is unavailable"):
            provider.generate("critic", {})
    with CodexAppServerProvider(
        config(tmp_path, "startup", startup_timeout_seconds=0.1)
    ) as provider:
        assert "timed out" in provider.status()["reason"]
        assert provider.process_id is None


def test_persistent_campaign_scopes_and_no_unbounded_retries(tmp_path):
    cfg = config(tmp_path, max_calls=2)
    with CodexAppServerProvider(cfg) as provider:
        provider.bind_campaign_budget("c1", max_calls=1)
        provider.generate("critic", {}, schema=SCHEMA)
    with CodexAppServerProvider(cfg) as provider:
        provider.bind_campaign_budget("c1", max_calls=1)
        with pytest.raises(ProviderBudgetExceeded):
            provider.generate("critic", {}, schema=SCHEMA)
        provider.bind_campaign_budget("c2", max_calls=2)
        provider.generate("critic", {}, schema=SCHEMA)
        provider.bind_campaign_budget("c3", max_calls=2, max_tokens=1)
        with pytest.raises(ProviderBudgetExceeded, match="token"):
            provider.generate("critic", {}, schema=SCHEMA)
    assert json.loads(cfg.ledger_path.read_text())["calls"] == 2


def test_concurrent_provider_instances_share_fenced_local_slots(tmp_path):
    cfg = config(tmp_path, "slow", max_concurrent_calls=1)
    first, second = CodexAppServerProvider(cfg), CodexAppServerProvider(cfg)
    try:
        with first._slot():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(second.generate, "critic", {}, schema=SCHEMA)
                with pytest.raises(ProviderBudgetExceeded, match="concurrent"):
                    future.result(timeout=5)
        assert not cfg.ledger_path.exists()
        assert second.generate("critic", {}, schema=SCHEMA).output_tokens == 10
    finally:
        first.close()
        second.close()


def test_rerouted_model_and_missing_usage_are_explicit(tmp_path):
    with CodexAppServerProvider(config(tmp_path, "rerouted")) as provider:
        response = provider.generate("critic", {}, schema=SCHEMA)
        assert response.model == "fixture-rerouted"
        assert response.metadata["reroutes"]
    with CodexAppServerProvider(config(tmp_path, "nousage")) as provider:
        response = provider.generate("critic", {}, schema=SCHEMA)
        assert response.input_tokens is None and response.output_tokens is None
        assert response.usage_unknown_reason


def test_server_crash_between_calls_is_not_silently_restarted(tmp_path):
    with CodexAppServerProvider(config(tmp_path)) as provider:
        assert provider.status()["usable"]
        os.kill(provider.process_id, signal.SIGKILL)
        provider._process.wait(timeout=3)
        with pytest.raises(ProviderError, match="crashed"):
            provider.generate("critic", {}, schema=SCHEMA)


def test_input_bound_and_invalid_config(tmp_path):
    with CodexAppServerProvider(config(tmp_path, max_input_bytes=20)) as provider:
        with pytest.raises(ProviderBudgetExceeded, match="prompt bound"):
            provider.generate("critic", {"too_long": "x" * 20})
        assert provider.process_id is None
    for values in (
        {"max_calls": 0},
        {"model": ""},
        {"max_concurrent_calls": 33},
        {"request_timeout_seconds": 0},
    ):
        with pytest.raises(ValueError):
            CodexConfig(ledger_path=tmp_path / "ledger.json", **values)


def test_stalled_server_input_write_has_bounded_timeout(tmp_path):
    import time

    cfg = config(tmp_path, "stallinput", max_input_bytes=2_000_000, request_timeout_seconds=0.2)
    started = time.monotonic()
    with CodexAppServerProvider(cfg) as provider:
        with pytest.raises(ProviderError, match="timed out"):
            provider.generate("critic", {"large": "x" * 1_000_000}, schema=SCHEMA)
        assert provider.process_id is None
    assert time.monotonic() - started < 4
    assert json.loads(cfg.ledger_path.read_text())["calls"] == 1


def test_logs_and_rate_snapshots_never_contain_prompt_or_account_data(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="butterfly_lab.codex_provider")
    with CodexAppServerProvider(config(tmp_path)) as provider:
        status = provider.status()
        response = provider.generate("critic", {"evidence": "never-log-this-input"}, schema=SCHEMA)
        assert status["rate_limits"]["primary"]["used_percent"] == 1
        assert "email" not in json.dumps(response.metadata)
    assert "never-log-this-input" not in caplog.text
    assert "completed" in caplog.text and "reaped" in caplog.text


@pytest.mark.parametrize(
    "scenario,match",
    [
        ("wireextra", "wire envelope"),
        ("wiremissing", "wire envelope"),
        ("wiretype", "wire envelope"),
        ("wiremalformed", "wire envelope is malformed JSON"),
        ("innerarray", "must be a JSON object"),
    ],
)
def test_closed_wire_envelope_is_locally_enforced(tmp_path, scenario, match):
    cfg = config(tmp_path, scenario)
    with CodexAppServerProvider(cfg) as provider:
        with pytest.raises(ProviderError, match=match):
            provider.generate("critic", {}, schema=SCHEMA)
    state = json.loads(cfg.ledger_path.read_text())
    assert state["calls"] == 1
    assert state["reservations"][0]["status"] == "FAILED_OR_AMBIGUOUS_RESERVATION_RETAINED"


def test_role_schemas_with_defaults_and_open_dsl_use_closed_wire_transport(tmp_path):
    from butterfly_lab.agents import RoleOutput, SpecificationOutput

    cfg = config(tmp_path)
    Path(cfg.command + ".responses.json").write_text(
        json.dumps(
            {
                "critic": {"notes": ["bounded"]},
                "specification": {
                    "dsl": {"evaluator": "controlled", "nested": {"arbitrary_approved_key": 3}},
                    "notes": ["fixture"],
                },
            }
        )
    )
    assert set(RoleOutput.model_json_schema()["required"]) != set(
        RoleOutput.model_json_schema()["properties"]
    )
    assert (
        SpecificationOutput.model_json_schema()["properties"]["dsl"]["additionalProperties"] is True
    )
    with CodexAppServerProvider(cfg) as provider:
        role = provider.generate("critic", {}, schema=RoleOutput.model_json_schema())
        specification = provider.generate(
            "specification", {}, schema=SpecificationOutput.model_json_schema()
        )
    assert RoleOutput.model_validate(role.payload).recommendations == []
    assert (
        SpecificationOutput.model_validate(specification.payload).dsl["nested"][
            "arbitrary_approved_key"
        ]
        == 3
    )
    assert role.metadata["wire_contract_version"] == 1
    assert specification.metadata["wire_contract_version"] == 1


@pytest.mark.parametrize(
    "bad_schema",
    [
        {
            "type": "object",
            "properties": {"optional": {"type": "string"}},
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"open": {"type": "object", "additionalProperties": True}},
            "required": ["open"],
            "additionalProperties": False,
        },
    ],
)
def test_fake_server_rejects_unsupported_strict_wire_schemas(tmp_path, monkeypatch, bad_schema):
    import butterfly_lab.codex_provider as module

    monkeypatch.setattr(module, "_WIRE_SCHEMA", bad_schema)
    cfg = config(tmp_path)
    with CodexAppServerProvider(cfg) as provider:
        with pytest.raises(ProviderError, match="rejected turn/start"):
            provider.generate("critic", {}, schema=SCHEMA)
    assert json.loads(cfg.ledger_path.read_text())["calls"] == 1
