from __future__ import annotations

import pytest

from cryptovision.config import ConfigurationError, Settings, load_settings, settings_from_mapping
from tests.conftest import FAKE_KEY


def test_defaults_when_environment_is_empty():
    settings = settings_from_mapping({})
    assert settings.coingecko_api_key is None
    assert not settings.has_api_key
    assert settings.coingecko_base_url == "https://api.coingecko.com/api/v3"
    assert settings.cache_ttl_seconds == 900
    assert settings.http_timeout_seconds == 10
    assert settings.http_max_retries == 3


def test_values_are_parsed_from_strings():
    settings = settings_from_mapping(
        {
            "COINGECKO_API_KEY": f"  {FAKE_KEY}  ",
            "CACHE_TTL_SECONDS": "600",
            "HTTP_TIMEOUT_SECONDS": "2.5",
            "HTTP_MAX_RETRIES": "1",
            "COINGECKO_BASE_URL": "https://example.invalid/api/v3/",
        }
    )
    assert settings.coingecko_api_key.get_secret_value() == FAKE_KEY
    assert settings.cache_ttl_seconds == 600
    assert settings.http_timeout_seconds == 2.5
    assert settings.http_max_retries == 1
    assert settings.coingecko_base_url == "https://example.invalid/api/v3"


def test_blank_key_counts_as_missing():
    assert settings_from_mapping({"COINGECKO_API_KEY": "   "}).coingecko_api_key is None


def test_key_is_masked_in_repr():
    settings = settings_from_mapping({"COINGECKO_API_KEY": FAKE_KEY})
    assert FAKE_KEY not in repr(settings)
    assert FAKE_KEY not in str(settings)


@pytest.mark.parametrize(
    ("env", "variable"),
    [
        ({"CACHE_TTL_SECONDS": "10"}, "CACHE_TTL_SECONDS"),
        ({"CACHE_TTL_SECONDS": "abc"}, "CACHE_TTL_SECONDS"),
        ({"HTTP_TIMEOUT_SECONDS": "0"}, "HTTP_TIMEOUT_SECONDS"),
        ({"HTTP_TIMEOUT_SECONDS": "120"}, "HTTP_TIMEOUT_SECONDS"),
        ({"HTTP_MAX_RETRIES": "10"}, "HTTP_MAX_RETRIES"),
        ({"COINGECKO_BASE_URL": "http://api.coingecko.com/api/v3"}, "COINGECKO_BASE_URL"),
    ],
)
def test_invalid_values_raise_configuration_error(env, variable):
    with pytest.raises(ConfigurationError, match=variable) as excinfo:
        settings_from_mapping({"COINGECKO_API_KEY": FAKE_KEY, **env})
    assert FAKE_KEY not in str(excinfo.value)


def test_invalid_value_is_not_echoed():
    with pytest.raises(ConfigurationError) as excinfo:
        settings_from_mapping({"CACHE_TTL_SECONDS": "secret-looking-value"})
    assert "secret-looking-value" not in str(excinfo.value)


def test_load_settings_reads_dotenv_without_overriding_environment(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"COINGECKO_API_KEY={FAKE_KEY}\nCACHE_TTL_SECONDS=300\n", encoding="utf-8")
    monkeypatch.delenv("COINGECKO_API_KEY")
    monkeypatch.setenv("CACHE_TTL_SECONDS", "1200")

    settings = load_settings(dotenv)

    assert settings.coingecko_api_key.get_secret_value() == FAKE_KEY
    assert settings.cache_ttl_seconds == 1200


def test_settings_are_immutable():
    settings = Settings()
    with pytest.raises(ValueError):
        settings.cache_ttl_seconds = 1  # type: ignore[misc]
