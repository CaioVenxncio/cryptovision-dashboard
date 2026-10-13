"""Application configuration loaded from environment variables.

Values are read from the process environment. For local development a `.env`
file in the project root is loaded first; variables already present in the
environment take precedence over the file.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

DEFAULT_COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigurationError(Exception):
    """Raised when configuration values are missing or invalid."""


class Settings(BaseModel):
    """Validated runtime settings.

    The API key is stored as a `SecretStr`, so it is masked in `repr()`, `str()`
    and validation errors.
    """

    model_config = ConfigDict(frozen=True)

    coingecko_api_key: SecretStr | None = None
    coingecko_base_url: str = DEFAULT_COINGECKO_BASE_URL
    cache_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    http_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    http_max_retries: int = Field(default=3, ge=0, le=5)
    # Local historical datasets (see docs/data-methodology.md).
    data_dir: Path = PROJECT_ROOT / "data"
    # Research Lab result bundles (see docs/research-reproducibility.md).
    results_dir: Path = PROJECT_ROOT / "research" / "results"

    @field_validator("coingecko_api_key", mode="before")
    @classmethod
    def _blank_key_is_missing(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("coingecko_base_url")
    @classmethod
    def _require_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("must use https://")
        return value.rstrip("/")

    @property
    def has_api_key(self) -> bool:
        return self.coingecko_api_key is not None


_ENV_TO_FIELD = {
    "COINGECKO_API_KEY": "coingecko_api_key",
    "COINGECKO_BASE_URL": "coingecko_base_url",
    "CACHE_TTL_SECONDS": "cache_ttl_seconds",
    "HTTP_TIMEOUT_SECONDS": "http_timeout_seconds",
    "HTTP_MAX_RETRIES": "http_max_retries",
    "CRYPTOVISION_DATA_DIR": "data_dir",
    "CRYPTOVISION_RESULTS_DIR": "results_dir",
}


def settings_from_mapping(env: Mapping[str, str]) -> Settings:
    """Build settings from an environment-like mapping.

    Raises:
        ConfigurationError: if a value is invalid. The message names the
            offending variables but never includes their values.
    """
    values = {field: env[name] for name, field in _ENV_TO_FIELD.items() if name in env}
    try:
        return Settings(**values)
    except ValidationError as exc:
        field_to_env = {field: name for name, field in _ENV_TO_FIELD.items()}
        problems = [
            f"{field_to_env.get(str(error['loc'][0]), error['loc'][0])}: {error['msg']}"
            for error in exc.errors(include_input=False)
        ]
        raise ConfigurationError("Invalid configuration. " + "; ".join(problems)) from None


def load_settings(dotenv_path: Path | None = None) -> Settings:
    """Load `.env` (without overriding existing variables) and return settings."""
    load_dotenv(dotenv_path or PROJECT_ROOT / ".env", override=False)
    return settings_from_mapping(os.environ)
