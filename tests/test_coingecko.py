from __future__ import annotations

from datetime import UTC, datetime

import pytest
import requests
import responses
from pydantic import SecretStr
from responses import matchers

from cryptovision.config import Settings
from cryptovision.providers.coingecko import API_KEY_HEADER, CoinGeckoClient
from cryptovision.providers.errors import (
    AuthenticationError,
    MissingApiKeyError,
    ProviderRequestError,
    ProviderUnavailableError,
    RateLimitError,
    ResponseSchemaError,
)
from tests.conftest import BASE_URL, FAKE_KEY, FIXED_NOW, load_fixture

MARKETS_URL = f"{BASE_URL}/coins/markets"
SIMPLE_URL = f"{BASE_URL}/simple/price"


# --- Authentication and request construction -------------------------------------------


def test_markets_request_sends_key_in_header_only(client, mocked_api):
    mocked_api.get(
        MARKETS_URL,
        json=load_fixture("coins_markets.json"),
        match=[
            matchers.header_matcher({API_KEY_HEADER: FAKE_KEY}),
            matchers.query_param_matcher(
                {
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": "100",
                    "page": "1",
                    "sparkline": "false",
                }
            ),
        ],
    )

    client.get_markets("usd", per_page=100)

    request = mocked_api.calls[0].request
    assert FAKE_KEY not in request.url
    assert "api_key" not in request.url
    assert request.headers[API_KEY_HEADER] == FAKE_KEY


def test_simple_price_request_parameters(client, mocked_api):
    mocked_api.get(
        SIMPLE_URL,
        json=load_fixture("simple_price.json"),
        match=[
            matchers.query_param_matcher(
                {
                    "ids": "bitcoin,ethereum",
                    "vs_currencies": "usd",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true",
                    "include_24hr_change": "true",
                    "include_last_updated_at": "true",
                }
            )
        ],
    )

    client.get_simple_price(["bitcoin", " Ethereum ", "bitcoin"])

    assert FAKE_KEY not in mocked_api.calls[0].request.url


@pytest.mark.parametrize("key", [None, SecretStr(""), SecretStr("   ")])
def test_missing_api_key_is_rejected_before_any_request(key, mocked_api):
    with pytest.raises(MissingApiKeyError):
        CoinGeckoClient(key)
    assert len(mocked_api.calls) == 0


def test_from_settings_uses_configured_timeout(mocked_api):
    settings = Settings(coingecko_api_key=FAKE_KEY, http_timeout_seconds=7)
    client = CoinGeckoClient.from_settings(settings, sleep=lambda _: None)
    mocked_api.get(MARKETS_URL, json=[])

    client.get_markets()

    assert mocked_api.calls[0].request.req_kwargs["timeout"] == 7


def test_repr_does_not_expose_key():
    client = CoinGeckoClient(SecretStr(FAKE_KEY))
    assert FAKE_KEY not in repr(client)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_is_not_retried(client, mocked_api, sleeps, status):
    mocked_api.get(MARKETS_URL, status=status, json={"error": "invalid key"})

    with pytest.raises(AuthenticationError) as excinfo:
        client.get_markets()

    assert len(mocked_api.calls) == 1
    assert sleeps == []
    assert FAKE_KEY not in str(excinfo.value)


def test_other_client_error_is_not_retried(client, mocked_api):
    mocked_api.get(MARKETS_URL, status=400, json={"error": "bad request"})

    with pytest.raises(ProviderRequestError):
        client.get_markets()

    assert len(mocked_api.calls) == 1


# --- Retries --------------------------------------------------------------------------


def test_rate_limit_then_success_honours_retry_after(client, mocked_api, sleeps):
    mocked_api.get(MARKETS_URL, status=429, headers={"Retry-After": "3"})
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))

    snapshot = client.get_markets()

    assert len(snapshot.coins) == 3
    assert sleeps == [3.0]


def test_rate_limit_exhausts_bounded_retries(client, mocked_api, sleeps):
    mocked_api.get(MARKETS_URL, status=429)

    with pytest.raises(RateLimitError):
        client.get_markets()

    assert len(mocked_api.calls) == 3  # 1 attempt + 2 retries
    assert len(sleeps) == 2


def test_long_retry_after_fails_fast(client, mocked_api, sleeps):
    mocked_api.get(MARKETS_URL, status=429, headers={"Retry-After": "3600"})

    with pytest.raises(RateLimitError) as excinfo:
        client.get_markets()

    assert len(mocked_api.calls) == 1
    assert sleeps == []
    assert excinfo.value.retry_after_seconds == 3600


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_retry_with_exponential_backoff(client, mocked_api, sleeps, status):
    mocked_api.get(MARKETS_URL, status=status)

    with pytest.raises(ProviderUnavailableError):
        client.get_markets()

    assert len(mocked_api.calls) == 3
    # base 1s, doubled per attempt, jitter factor within [0.5, 1.0]
    assert 0.5 <= sleeps[0] <= 1.0
    assert 1.0 <= sleeps[1] <= 2.0


def test_server_error_then_success(client, mocked_api):
    mocked_api.get(MARKETS_URL, status=503)
    mocked_api.get(MARKETS_URL, json=[])

    assert client.get_markets().coins == ()


def test_timeout_is_retried_then_reported(client, mocked_api, sleeps):
    mocked_api.get(MARKETS_URL, body=requests.Timeout("read timed out"))

    with pytest.raises(ProviderUnavailableError, match="timed out"):
        client.get_markets()

    assert len(mocked_api.calls) == 3


def test_connection_error_is_reported(client, mocked_api):
    mocked_api.get(MARKETS_URL, body=requests.ConnectionError("dns failure"))

    with pytest.raises(ProviderUnavailableError, match="Could not connect"):
        client.get_markets()


def test_zero_retries_makes_exactly_one_request(mocked_api):
    settings = Settings(coingecko_api_key=FAKE_KEY, http_max_retries=0)
    client = CoinGeckoClient.from_settings(settings, sleep=lambda _: None)
    mocked_api.get(MARKETS_URL, status=500)

    with pytest.raises(ProviderUnavailableError):
        client.get_markets()

    assert len(mocked_api.calls) == 1


# --- Response validation --------------------------------------------------------------


def test_malformed_json_raises_schema_error(client, mocked_api):
    mocked_api.get(MARKETS_URL, body="<html>not json</html>", content_type="text/html")

    with pytest.raises(ResponseSchemaError, match="not valid JSON"):
        client.get_markets()

    assert len(mocked_api.calls) == 1


def test_unexpected_top_level_structure(client, mocked_api):
    mocked_api.get(MARKETS_URL, json={"status": {"error_message": "oops"}})

    with pytest.raises(ResponseSchemaError):
        client.get_markets()


def test_invalid_records_are_dropped_and_counted(client, mocked_api):
    payload = load_fixture("coins_markets.json")
    payload.append({"symbol": "x", "name": "No Id"})
    payload.append({"id": "bad", "symbol": "b", "name": "Bad", "current_price": "abc"})
    mocked_api.get(MARKETS_URL, json=payload)

    snapshot = client.get_markets()

    assert [coin.id for coin in snapshot.coins] == ["bitcoin", "ethereum", "tiny-token"]
    assert snapshot.dropped_records == 2


def test_all_records_invalid_raises(client, mocked_api):
    mocked_api.get(MARKETS_URL, json=[{"foo": 1}, {"bar": 2}])

    with pytest.raises(ResponseSchemaError, match="no valid records"):
        client.get_markets()


def test_markets_snapshot_metadata_and_nulls(client, mocked_api):
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))

    snapshot = client.get_markets()

    assert snapshot.provider == "CoinGecko"
    assert snapshot.endpoint == "/coins/markets"
    assert snapshot.fetched_at == FIXED_NOW
    assert snapshot.data_last_updated == datetime(2026, 10, 13, 12, 1, 0, tzinfo=UTC)
    tiny = snapshot.coins[2]
    assert tiny.market_cap is None
    assert tiny.market_cap_rank is None
    assert tiny.current_price == pytest.approx(0.00001234)


def test_simple_price_parses_quotes_and_missing_ids(client, mocked_api):
    mocked_api.get(SIMPLE_URL, json=load_fixture("simple_price.json"))

    result = client.get_simple_price(["bitcoin", "ethereum", "unknown-coin"])

    assert result.missing_ids == ("unknown-coin",)
    btc = result.quotes["bitcoin"]
    assert btc.price == 60000.5
    assert btc.volume_24h == 30_000_000_000
    assert btc.change_24h_percent == 2.0
    assert btc.last_updated == datetime.fromtimestamp(1792065630, tz=UTC)
    assert result.quotes["ethereum"].market_cap is None


def test_simple_price_invalid_values(client, mocked_api):
    mocked_api.get(SIMPLE_URL, json={"bitcoin": {"usd": "not-a-number"}})

    with pytest.raises(ResponseSchemaError):
        client.get_simple_price(["bitcoin"])


def test_simple_price_invalid_entry_type(client, mocked_api):
    mocked_api.get(SIMPLE_URL, json={"bitcoin": [1, 2, 3]})

    with pytest.raises(ResponseSchemaError):
        client.get_simple_price(["bitcoin"])


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"vs_currency": "US D"}, "vs_currency"),
        ({"per_page": 0}, "per_page"),
        ({"per_page": 251}, "per_page"),
        ({"page": 0}, "page"),
    ],
)
def test_invalid_market_arguments_are_rejected_locally(client, kwargs, message):
    with responses.RequestsMock() as rsps, pytest.raises(ValueError, match=message):
        client.get_markets(**kwargs)
    assert len(rsps.calls) == 0


def test_simple_price_requires_ids(client):
    with pytest.raises(ValueError):
        client.get_simple_price([" ", ""])


def test_unexpected_request_error_is_not_retried(client, mocked_api, sleeps):
    mocked_api.get(MARKETS_URL, body=requests.TooManyRedirects("redirect loop"))

    with pytest.raises(ProviderUnavailableError, match="TooManyRedirects"):
        client.get_markets()

    assert len(mocked_api.calls) == 1
    assert sleeps == []


def test_simple_price_unexpected_top_level_structure(client, mocked_api):
    mocked_api.get(SIMPLE_URL, json=[{"bitcoin": {"usd": 1}}])

    with pytest.raises(ResponseSchemaError, match="unexpected structure"):
        client.get_simple_price(["bitcoin"])
