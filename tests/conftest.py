from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import responses
from pydantic import SecretStr

from cryptovision.providers.coingecko import CoinGeckoClient
from cryptovision.providers.http_client import RetryPolicy

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = "https://api.coingecko.com/api/v3"
# Obviously fake value used only to check header handling; not a real credential.
FAKE_KEY = "test-demo-key-not-real"
FIXED_NOW = datetime(2026, 10, 13, 12, 5, 0, tzinfo=UTC)


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def mocked_api():
    """Activate `responses`; any request without a registered mock fails."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(sleeps) -> CoinGeckoClient:
    return CoinGeckoClient(
        SecretStr(FAKE_KEY),
        base_url=BASE_URL,
        timeout_seconds=5,
        retry_policy=RetryPolicy(max_retries=2, backoff_base_seconds=1, backoff_max_seconds=8),
        sleep=sleeps.append,
        clock=lambda: FIXED_NOW,
    )


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    """Keep the developer's real `.env` key out of every test.

    `load_dotenv` never overrides an existing variable, so presetting an empty
    value guarantees the local credential is not loaded into the test process.
    """
    for name in (
        "CACHE_TTL_SECONDS",
        "HTTP_TIMEOUT_SECONDS",
        "HTTP_MAX_RETRIES",
        "COINGECKO_BASE_URL",
        "CRYPTOVISION_DATA_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COINGECKO_API_KEY", "")
