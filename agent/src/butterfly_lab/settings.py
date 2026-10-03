"""One typed, non-executing source of user-editable runtime configuration.

The checkout's ``agent/.env`` is authoritative; an explicit path or
``BUTTERFLY_ENV_FILE`` selects an alternative single file. Shell values override
that file. Codex authentication is deliberately not a Butterfly Lab setting.
"""

from __future__ import annotations

import os
import re
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Mapping
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic import model_validator


class ConfigurationError(ValueError):
    """Safe operator-facing error; never includes configuration values."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    config_path: Path | None = None
    lab_home: Path = Field(default_factory=lambda: Path.home() / ".local/share/butterfly-lab")
    llm_provider: Literal["codex", "openai", "fixture", "replay"] = "codex"
    codex_mode: Literal["managed"] = "managed"
    codex_command: str = "codex"
    codex_model: str | None = None
    codex_startup_timeout_seconds: float = Field(default=30, gt=0, le=300, allow_inf_nan=False)
    codex_request_timeout_seconds: float = Field(default=120, gt=0, le=3600, allow_inf_nan=False)
    llm_max_concurrent_calls: int = Field(default=2, ge=1, le=16)
    llm_max_calls_per_campaign: int = Field(default=40, ge=1, le=10000)
    llm_max_output_tokens: int = Field(default=4096, ge=1, le=131072)
    llm_max_input_bytes: int = Field(default=65536, ge=1, le=4194304)
    numerical_workers: int = Field(default=2, ge=1, le=2)
    pending_job_limit: int = Field(default=20, ge=1, le=100000)
    run_cpu_seconds: float = Field(default=30, gt=0, le=3600, allow_inf_nan=False)
    run_wall_seconds: float = Field(default=60, gt=0, le=7200, allow_inf_nan=False)
    run_memory_mb: int = Field(default=1024, ge=128, le=65536)
    run_storage_bytes: int = Field(default=10_000_000, ge=1, le=1_000_000_000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    replay_path: Path | None = None
    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    openai_model: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_max_cost_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    openai_input_usd_per_million: float = Field(default=0, ge=0, allow_inf_nan=False)
    openai_output_usd_per_million: float = Field(default=0, ge=0, allow_inf_nan=False)

    @field_validator("codex_command")
    @classmethod
    def command_is_one_executable(cls, value: str) -> str:
        if not value.strip() or any(c in value for c in ("\x00", "\n", "\r")):
            raise ValueError("must name one executable; arguments belong to the managed adapter")
        return value

    @field_validator("codex_model", "openai_model")
    @classmethod
    def model_identifier(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", value):
            raise ValueError("must be a model identifier, not a command or URL query")
        return value

    @field_validator("openai_api_key")
    @classmethod
    def safe_api_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and any(c.isspace() or ord(c) < 32 for c in value.get_secret_value()):
            raise ValueError("API key must not contain whitespace or control characters")
        return value

    @field_validator("openai_base_url")
    @classmethod
    def safe_endpoint(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("must be a credential-free HTTPS endpoint")
        return value.rstrip("/")

    @model_validator(mode="after")
    def compatible(self) -> Settings:
        if self.pending_job_limit < self.numerical_workers:
            raise ValueError("pending_job_limit must be at least numerical_workers")
        if self.llm_provider == "replay" and self.replay_path is None:
            raise ValueError("replay requires BUTTERFLY_REPLAY_PATH")
        if self.llm_provider == "openai":
            if self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip():
                raise ValueError("openai requires OPENAI_API_KEY")
            if not self.openai_model:
                raise ValueError("openai requires BUTTERFLY_OPENAI_MODEL")
            if (
                min(
                    self.openai_max_cost_usd,
                    self.openai_input_usd_per_million,
                    self.openai_output_usd_per_million,
                )
                <= 0
            ):
                raise ValueError(
                    "openai requires positive API budget and configured price ceilings"
                )
        return self

    def redacted(self) -> dict[str, Any]:
        result = self.model_dump(mode="json")
        result["openai_api_key"] = "[REDACTED]" if self.openai_api_key is not None else None
        return result


ENV_FIELDS = {
    ("OPENAI_API_KEY" if field == "openai_api_key" else "BUTTERFLY_" + field.upper()): field
    for field in Settings.model_fields
    if field != "config_path"
}
_OPTIONAL = {"codex_model", "openai_model", "openai_api_key", "replay_path"}


def _dotenv(path: Path) -> dict[str, str]:
    """Small deliberate dotenv grammar: no interpolation, execution, or multiline values."""
    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        raise ConfigurationError("Cannot read the selected Butterfly Lab .env file") from None
    if len(content.encode()) > 131072:
        raise ConfigurationError("Butterfly Lab .env exceeds the 128 KiB configuration limit")
    result: dict[str, str] = {}
    for number, raw in enumerate(content.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if not match:
            raise ConfigurationError(f"Invalid .env assignment on line {number}")
        key, value = match.groups()
        if key not in ENV_FIELDS:
            raise ConfigurationError(f"Unsupported .env field on line {number}")
        if key in result:
            raise ConfigurationError(f"Duplicate .env field on line {number}")
        if value.startswith(("'", '"')):
            quote = value[0]
            characters: list[str] = []
            index = 1
            while index < len(value):
                char = value[index]
                if char == quote:
                    trailing = value[index + 1 :].strip()
                    if trailing and not trailing.startswith("#"):
                        raise ConfigurationError(f"Invalid quoted value on line {number}")
                    value = "".join(characters)
                    break
                if char == "\\" and quote == '"' and index + 1 < len(value):
                    escapes = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
                    if value[index + 1] in escapes:
                        index += 1
                        char = escapes[value[index]]
                characters.append(char)
                index += 1
            else:
                raise ConfigurationError(f"Unterminated quoted value on line {number}")
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if "\x00" in value:
            raise ConfigurationError(f"Invalid null byte in .env on line {number}")
        result[key] = value
    return result


def _is_lab_directory(directory: Path) -> bool:
    try:
        with (directory / "pyproject.toml").open("rb") as handle:
            return tomllib.load(handle).get("project", {}).get("name") == "butterfly-research-lab"
    except (OSError, tomllib.TOMLDecodeError):
        return False


def _locate_file(explicit: str | Path | None, environ: Mapping[str, str], cwd: Path) -> Path | None:
    chosen = explicit if explicit is not None else environ.get("BUTTERFLY_ENV_FILE")
    if chosen:
        path = Path(chosen).expanduser()
        path = (cwd / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_file():
            raise ConfigurationError(
                "The explicitly selected Butterfly Lab .env file does not exist"
            )
        return path
    for directory in (cwd, *cwd.parents):
        if _is_lab_directory(directory):
            return directory / ".env"
    # An editable checkout may be invoked from elsewhere. A wheel installation
    # has no matching project manifest here and never loads an unrelated .env.
    checkout = Path(__file__).resolve().parents[2]
    return checkout / ".env" if _is_lab_directory(checkout) else None


def load_settings(
    env_file: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Settings:
    """Uncached loader for diagnostics/tests; callers normally use get_settings()."""
    shell = os.environ if environ is None else environ
    base = (cwd or Path.cwd()).resolve()
    path = _locate_file(env_file, shell, base)
    values = _dotenv(path) if path is not None and path.exists() else {}
    unknown = sorted(
        key
        for key in shell
        if key.startswith("BUTTERFLY_") and key not in ENV_FIELDS and key != "BUTTERFLY_ENV_FILE"
    )
    if unknown:
        raise ConfigurationError("Unknown BUTTERFLY_* shell configuration field; check spelling")
    values.update({key: shell[key] for key in ENV_FIELDS if key in shell})
    typed: dict[str, Any] = {"config_path": path}
    for key, value in values.items():
        field = ENV_FIELDS[key]
        if not value.strip():
            if field in _OPTIONAL:
                typed[field] = None
            continue
        typed[field] = value
    for field in ("lab_home", "replay_path"):
        if field in typed and typed[field] is not None:
            resolved = Path(typed[field]).expanduser()
            # Relative file values follow the selected .env, not the caller's cwd.
            origin = path.parent if path is not None else base
            typed[field] = (
                (origin / resolved).resolve() if not resolved.is_absolute() else resolved.resolve()
            )
    try:
        return Settings.model_validate(typed)
    except ValidationError as exc:
        errors = []
        for error in exc.errors(include_input=False, include_context=False, include_url=False):
            location = ".".join(str(part) for part in error["loc"]) or "configuration"
            # Validator messages are fixed strings under application control.
            errors.append(f"{location}: {error['msg']}")
        raise ConfigurationError("Invalid Butterfly Lab settings: " + "; ".join(errors)) from None


@lru_cache(maxsize=8)
def get_settings(env_file: str | Path | None = None) -> Settings:
    """Load each explicitly selected configuration once per process."""
    return load_settings(env_file)


def clear_settings_cache() -> None:
    """Explicit reload hook for a new operator invocation or isolated test."""
    get_settings.cache_clear()
