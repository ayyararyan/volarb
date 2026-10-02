"""Central provider construction from runtime settings, never private JSON config."""

from __future__ import annotations

from pathlib import Path
import uuid

from .settings import Settings, get_settings
from .providers import OpenAIConfig, OpenAIProvider, ProviderError, ReplayProvider
from .codex_provider import CodexConfig, CodexAppServerProvider


def make_provider(root: Path, kind: str | None = None, settings: Settings | None = None):
    cfg = settings or get_settings()
    selected = kind or cfg.llm_provider
    if selected == "codex":
        return CodexAppServerProvider(
            CodexConfig(
                command=cfg.codex_command,
                model=cfg.codex_model,
                ledger_path=root / "codex-usage.json",
                startup_timeout_seconds=cfg.codex_startup_timeout_seconds,
                request_timeout_seconds=cfg.codex_request_timeout_seconds,
                max_calls=cfg.llm_max_calls_per_campaign,
                max_concurrent_calls=cfg.llm_max_concurrent_calls,
                max_output_tokens=cfg.llm_max_output_tokens,
                max_input_bytes=cfg.llm_max_input_bytes,
            )
        )
    if selected == "openai":
        # Validation applies even when the immutable campaign explicitly selects
        # an API provider different from the machine's default provider.
        Settings.model_validate({**cfg.model_dump(), "llm_provider": "openai"})
        return OpenAIProvider(
            OpenAIConfig(
                model=cfg.openai_model or "",
                api_key=cfg.openai_api_key,
                ledger_path=root / "provider-budget.json",
                base_url=cfg.openai_base_url,
                approved=True,
                max_calls=cfg.llm_max_calls_per_campaign,
                max_cost_usd=cfg.openai_max_cost_usd,
                input_usd_per_million=cfg.openai_input_usd_per_million,
                output_usd_per_million=cfg.openai_output_usd_per_million,
                max_output_tokens=cfg.llm_max_output_tokens,
                max_input_bytes=cfg.llm_max_input_bytes,
                timeout_seconds=cfg.codex_request_timeout_seconds,
            )
        )
    if selected == "replay":
        import json

        if cfg.replay_path is None:
            raise ProviderError("Replay requires BUTTERFLY_REPLAY_PATH in agent/.env")
        return ReplayProvider(json.loads(cfg.replay_path.read_text()))
    if selected in {"fixture", "deterministic"}:
        from .agents import fixture_provider, load_seeds

        return fixture_provider(load_seeds(Path(__file__).parent / "resources" / "seeds.json"))
    raise ProviderError("Unknown provider identifier")


def service_for(root: Path, campaign: dict | None = None, settings: Settings | None = None):
    from .agents import AgentService
    from .registry import Registry

    cfg = settings or get_settings()
    if campaign is not None and hasattr(campaign, "model_dump"):
        campaign = campaign.model_dump(mode="json")
    selected = campaign.get("provider", cfg.llm_provider) if campaign else cfg.llm_provider
    # Offline campaigns retain their existing finite research contract. The
    # machine's model-call ceiling is only a ceiling on actual provider calls.
    maximum = cfg.llm_max_calls_per_campaign if selected in {"codex", "openai"} else 4000
    return AgentService(make_provider(root, selected, cfg), Registry(root), max_calls=maximum)


def provider_status(root: Path, settings: Settings | None = None):
    cfg = settings or get_settings()
    if cfg.llm_provider == "codex":
        provider = make_provider(root, settings=cfg)
        try:
            return {"provider": "codex", "model_request_performed": False, **provider.status()}
        finally:
            provider.close()
    if cfg.llm_provider == "openai":
        return {
            "provider": "openai",
            "credential_configured": cfg.openai_api_key is not None,
            "authenticated": None,
            "app_server_reachable": None,
            "model_available": None,
            "usable": None,
            "model_request_performed": False,
            "reason": "API credential/network/model not verified; no request made",
        }
    # Replay inspection reads evidence only and fails if it cannot be loaded;
    # it does not assert that an arbitrary future prompt has a matching record.
    make_provider(root, settings=cfg)
    return {
        "provider": cfg.llm_provider,
        "usable": True,
        "model_request_performed": False,
        "source": "synthetic_fixture" if cfg.llm_provider == "fixture" else "recorded_replay",
    }


def provider_test(root: Path, settings: Settings | None = None):
    """Explicit operator action: exactly one request, no correction or fallback."""
    from .agents import RoleOutput

    cfg = settings or get_settings()
    bounded = cfg.model_copy(
        update={
            "llm_max_output_tokens": min(cfg.llm_max_output_tokens, 512),
            "codex_request_timeout_seconds": min(cfg.codex_request_timeout_seconds, 30),
        }
    )
    provider = make_provider(root, settings=bounded)
    try:
        if isinstance(provider, CodexAppServerProvider):
            provider.bind_campaign_budget("explicit-auth-test-" + uuid.uuid4().hex, 1, 0)
        elif isinstance(provider, OpenAIProvider):
            provider.bind_campaign_budget(
                "explicit-auth-test-" + uuid.uuid4().hex,
                cfg.openai_max_cost_usd,
                cfg.llm_max_input_bytes + cfg.llm_max_output_tokens + 4096,
            )
        result = provider.generate(
            "steward",
            {
                "profile": "Connectivity test only. Return JSON with notes ['connection verified'], evidence_ids [], recommendations []. Do not use tools.",
            },
            schema=RoleOutput.model_json_schema(),
        )
        RoleOutput.model_validate(result.payload)
        # Persist only hashes/usage/model, not configuration or auth/account data.
        from .registry import Registry

        receipt = result.model_dump(mode="json", exclude={"payload"})
        Registry(root).add_event("EXPLICIT_PROVIDER_TEST", "provider", receipt)
        return {
            "usable": True,
            "typed_response_validated": True,
            "model_request_performed": result.source == "real_model",
            **receipt,
        }
    finally:
        close = getattr(provider, "close", None)
        if close:
            close()
