"""Bounded research role interfaces; deterministic admission remains authoritative."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .providers import FixtureProvider, OpenAIProvider, Provider, ProviderError, ReplayProvider
from .schemas import HypothesisSpec, digest
from .codex_provider import CodexAppServerProvider


class RoleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    notes: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class CritiqueOutput(RoleOutput):
    concerns: list[str] = Field(default_factory=list)
    recommendation: Literal["ADMIT", "REVISE", "UNSUPPORTED"]


class DesignOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    hypotheses: list[HypothesisSpec] = Field(min_length=1, max_length=12)


class SpecificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    dsl: dict[str, Any]
    notes: list[str] = Field(min_length=1)


ROLE_PROFILES = {
    "designer": "Propose falsifiable, economically motivated hypotheses and counter-hypotheses within verified capabilities.",
    "critic": "Challenge temporal availability, estimands, opportunities, costs, dependence, search and alternative explanations.",
    "specification": "Construct only constrained evaluator DSL; no Python, shell commands or new scientific primitives.",
    "replication": "Specify independent reconstruction checks, blind to unneeded original outputs; never retune frozen claims.",
    "synthesis": "Interpret authoritative estimates with fidelity, precision, exposure and limitations; never change evidence grade.",
    "steward": "Prioritize within an approved finite campaign and report negative/data-limited outcomes without spending authority.",
}


def _safe_context(value: Any) -> None:
    import re

    if isinstance(value, dict):
        if value.get("partition") == "confirmation" or value.get("access_class") == "confirmation":
            raise PermissionError("Agent role cannot inspect protected confirmation evidence")
        if value.get("partition") not in (None, "development") and "diagnostic" in value:
            raise PermissionError("Hypothesis diagnostics must be development-only")
        for key, child in value.items():
            # Match environment-style, snake_case, kebab-case and camelCase
            # keys without forwarding the key/value in an exception or model
            # correction. A redacted settings dump is still not research input.
            normalized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", str(key))
            normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized)
            normalized = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").lower()
            forbidden = {
                "api_key",
                "access_token",
                "refresh_token",
                "oauth_token",
                "oauth",
                "oauth_credentials",
                "authorization",
                "authorization_key",
                "signing_key",
                "env_contents",
                "env",
                "dotenv",
                "environment_variables",
                "environ",
                "settings",
                "runtime_settings",
                "runtime_config",
                "provider_config",
                "config_path",
                "env_path",
                "auth_path",
                "codex_auth",
                "codex_auth_path",
                "credential_path",
                "credentials_path",
                "credentials",
                "confirmation_secret",
                "password",
                "broker_credentials",
                "raw_data",
                "source_path",
            }
            credential_suffixes = (
                "_api_key",
                "_access_token",
                "_refresh_token",
                "_oauth_token",
                "_authorization_key",
                "_signing_key",
                "_password",
                "_secret",
                "_credentials",
                "_auth_path",
            )
            if (
                normalized in forbidden
                or normalized.endswith(credential_suffixes)
                or normalized.startswith("butterfly_")
            ):
                raise PermissionError("Forbidden credential/configuration field in agent context")
            _safe_context(child)
    elif isinstance(value, list):
        for child in value:
            _safe_context(child)


class AgentService:
    def __init__(self, provider: Provider, registry: Any | None = None, *, max_calls: int = 20):
        self.provider, self.registry, self.max_calls = provider, registry, max_calls
        self.calls = 0
        self._lock = threading.Lock()
        self._bound_campaign_id: str | None = None

    def bind_campaign(self, campaign_id: str) -> None:
        if self.registry is None:
            if isinstance(self.provider, (OpenAIProvider, CodexAppServerProvider)):
                raise ProviderError("Live agent calls require an authoritative campaign registry")
            return
        campaign = self.registry.get("campaign", campaign_id)
        if not campaign or not campaign["approved"]:
            raise PermissionError("Agent roles require an approved registered campaign")
        expected = campaign.get("provider", "fixture")
        if isinstance(self.provider, CodexAppServerProvider):
            if expected != "codex":
                raise PermissionError("Campaign does not permit the Codex subscription provider")
            budget = campaign["budget"]
            self.provider.bind_campaign_budget(
                campaign_id, budget.get("llm_calls", 0), budget["llm_tokens"]
            )
        elif isinstance(self.provider, OpenAIProvider):
            if expected != "openai":
                raise PermissionError("Campaign does not permit a live provider")
            budget = campaign["budget"]
            if budget["currency"] != "USD":
                raise ProviderError(
                    "Live USD provider requires an explicit USD campaign budget; no implicit FX conversion"
                )
            self.provider.bind_campaign_budget(
                campaign_id, budget["llm_currency"], budget["llm_tokens"]
            )
        elif expected in ("openai", "codex"):
            raise ProviderError("Live-provider campaign cannot silently use a fixture or replay")
        elif expected == "replay" and not isinstance(self.provider, ReplayProvider):
            raise ProviderError("Replay campaign requires a recorded-response provider")
        self._bound_campaign_id = campaign_id

    def _call(self, role: str, payload: dict[str, Any], output_type: type[BaseModel]) -> Any:
        _safe_context(payload)
        campaign_id = payload.get("campaign_id", self._bound_campaign_id)
        if campaign_id and self.registry is not None:
            self.bind_campaign(campaign_id)
        elif isinstance(self.provider, (OpenAIProvider, CodexAppServerProvider)):
            raise ProviderError("Live role call has no bound registered campaign")
        request = {"profile_version": "1", "profile": ROLE_PROFILES[role], **payload}
        for correction in range(2):
            with self._lock:
                if self.calls >= self.max_calls:
                    raise ProviderError("Agent service call budget exhausted")
                self.calls += 1
            response = self.provider.generate(role, request, schema=output_type.model_json_schema())
            error = None
            try:
                # Model prose cannot override authority; malformed contracts get
                # at most one format correction, never an economic optimization.
                validated = output_type.model_validate(response.payload)
            except ValidationError as exc:
                error = exc
            if self.registry is not None:
                record = response.model_dump(mode="json")
                record.update(
                    campaign_id=campaign_id,
                    correction_attempt=correction,
                    contract_status="INVALID" if error else "VALID",
                )
                self.registry.put("generation", digest(record), record)
            if error is None:
                return validated
            if correction:
                raise error
            request = {
                **request,
                "correction": {
                    "errors": [
                        {"type": issue["type"], "loc": issue["loc"], "msg": issue["msg"]}
                        for issue in error.errors(include_input=False, include_url=False)
                    ],
                    "previous_response_hash": response.response_hash,
                    "instruction": "Return a corrected schema-conforming JSON object; scientific scope is unchanged.",
                },
            }
        raise AssertionError("Bounded provider correction exhausted without terminal response")

    def design(
        self,
        campaign: dict[str, Any],
        capabilities: list[str],
        prior_findings: list[dict[str, Any]] | None = None,
    ) -> list[HypothesisSpec]:
        diagnostics = campaign.get("development_diagnostics", [])
        if self.registry is not None:
            self.bind_campaign(campaign["id"])
        if any(row.get("partition", "development") != "development" for row in diagnostics):
            raise PermissionError("Only development diagnostics may inform generation")
        if any(
            row.get("evidence_grade", {}).get("independence") == "protected_confirmation"
            for row in prior_findings or []
        ):
            raise PermissionError("Generator cannot adapt against protected confirmation feedback")
        cap = min(12, int(campaign.get("max_hypotheses", 12)))
        context = {
            "campaign_id": campaign["id"],
            "objective": campaign["objective"],
            "capabilities": sorted(set(capabilities)),
            "sources": campaign.get("source_records", []),
            "development_diagnostics": diagnostics,
            "prior_findings": prior_findings or [],
            "search_budget": cap,
        }
        result = self._call("designer", context, DesignOutput)
        if len(result.hypotheses) > cap:
            raise ProviderError("Generator exceeded campaign hypothesis budget")
        if len({hyp.id for hyp in result.hypotheses}) != len(result.hypotheses):
            raise ProviderError("Generator repeated a hypothesis identifier")
        if any(hyp.campaign_id != campaign["id"] for hyp in result.hypotheses):
            raise ProviderError("Generated hypothesis escaped campaign scope")
        feedback_ids = [f["id"] for f in (prior_findings or []) if "id" in f]
        parent_ids = [f["hypothesis_id"] for f in (prior_findings or []) if "hypothesis_id" in f]
        return [
            h.model_copy(
                update={
                    "informed_by_result_ids": sorted(set(h.informed_by_result_ids + feedback_ids)),
                    "parent_ids": sorted(set(h.parent_ids + parent_ids)),
                }
            )
            for h in result.hypotheses
        ]

    def critique(self, spec: HypothesisSpec, capabilities: list[str]) -> CritiqueOutput:
        return self._call(
            "critic",
            {
                "campaign_id": spec.campaign_id,
                "hypothesis": spec.model_dump(mode="json"),
                "capabilities": capabilities,
            },
            CritiqueOutput,
        )

    def specify(self, spec: HypothesisSpec) -> SpecificationOutput:
        return self._call(
            "specification",
            {"campaign_id": spec.campaign_id, "hypothesis": spec.model_dump(mode="json")},
            SpecificationOutput,
        )

    def replicate(self, frozen: dict[str, Any]) -> RoleOutput:
        return self._call("replication", {"frozen_specification": frozen}, RoleOutput)

    def synthesize(self, findings: list[dict[str, Any]]) -> RoleOutput:
        return self._call("synthesis", {"authoritative_findings": findings}, RoleOutput)

    def steward(self, campaign_status: dict[str, Any]) -> RoleOutput:
        return self._call("steward", {"campaign_status": campaign_status}, RoleOutput)


def load_seeds(path: Path | str, campaign_id: str = "example-campaign") -> list[HypothesisSpec]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        HypothesisSpec.model_validate(
            {
                **row,
                "id": campaign_id + "-" + row["id"],
                "parent_ids": [campaign_id + "-" + parent for parent in row.get("parent_ids", [])],
                "campaign_id": campaign_id,
            }
        )
        for row in raw
    ]


def fixture_provider(seeds: list[HypothesisSpec]) -> FixtureProvider:
    def designer(context: dict[str, Any]) -> dict[str, Any]:
        selected = seeds[: int(context["search_budget"])]
        return {
            "hypotheses": [
                {
                    **row.model_dump(mode="json"),
                    "campaign_id": context["campaign_id"],
                    "id": context["campaign_id"] + "-" + row.id.removeprefix(row.campaign_id + "-"),
                }
                for row in selected
            ]
        }

    def critic(context: dict[str, Any]) -> dict[str, Any]:
        spec = context["hypothesis"]
        missing = sorted(set(spec["minimum_data"]) - set(context["capabilities"]))
        return {
            "notes": [
                "Synthetic critic fixture; deterministic admission independently enforces capabilities."
            ],
            "concerns": ["Missing capability: " + cap for cap in missing],
            "recommendation": "REVISE" if missing else "ADMIT",
            "evidence_ids": [],
            "recommendations": [],
        }

    return FixtureProvider(
        {
            "designer": designer,
            "critic": critic,
            "specification": lambda context: {
                "dsl": context["hypothesis"]["proposed_dsl"],
                "notes": ["Frozen seed DSL, synthetic fixture."],
            },
            "replication": {
                "notes": [
                    "Reconstruct transformations and metrics independently; compare frozen tolerances."
                ]
            },
            "synthesis": {
                "notes": [
                    "Synthetic narrative fixture; authoritative registry grades and artifacts remain unchanged."
                ]
            },
            "steward": {
                "notes": [
                    "Preserve all registered negative and data-limited outcomes; do not expand budgets."
                ]
            },
        }
    )
