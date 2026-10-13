"""CoinGecko Demo API client.

Docs: https://docs.coingecko.com/reference/introduction
The API key is sent only in the `x-cg-demo-api-key` header, never in the URL.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import requests
from pydantic import SecretStr, ValidationError

from cryptovision.config import DEFAULT_COINGECKO_BASE_URL, Settings
from cryptovision.models import (
    MarketChart,
    MarketCoin,
    MarketSnapshot,
    SimplePriceQuote,
    SimplePriceResult,
)
from cryptovision.providers.errors import MissingApiKeyError, ResponseSchemaError
from cryptovision.providers.http_client import HttpJsonClient, RetryPolicy

logger = logging.getLogger(__name__)

PROVIDER_NAME = "CoinGecko"
# Wording required by CoinGecko API terms §4.4.
ATTRIBUTION_TEXT = "Powered by CoinGecko"
ATTRIBUTION_URL = "https://www.coingecko.com/en/api"
API_KEY_HEADER = "x-cg-demo-api-key"

MARKETS_ENDPOINT = "/coins/markets"
MARKET_CHART_ENDPOINT = "/coins/{id}/market_chart"
SIMPLE_PRICE_ENDPOINT = "/simple/price"
MAX_PER_PAGE = 250

# Documented auto-granularity: ranges above 90 days return daily points at 00:00 UTC.
# The Demo plan provides about one year of history, so requests stay within 365 days.
MIN_DAILY_CHART_DAYS = 91
MAX_DEMO_CHART_DAYS = 365

_VS_CURRENCY_PATTERN = re.compile(r"^[a-z]{2,10}$")
_COIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _validate_vs_currency(vs_currency: str) -> str:
    if not _VS_CURRENCY_PATTERN.match(vs_currency):
        raise ValueError(f"Invalid vs_currency: {vs_currency!r}")
    return vs_currency


class CoinGeckoClient:
    """Typed access to the CoinGecko endpoints CryptoVision uses."""

    def __init__(
        self,
        api_key: SecretStr | None,
        *,
        base_url: str = DEFAULT_COINGECKO_BASE_URL,
        timeout_seconds: float = 10.0,
        retry_policy: RetryPolicy | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if api_key is None or not api_key.get_secret_value().strip():
            raise MissingApiKeyError(
                "No CoinGecko API key configured. Set COINGECKO_API_KEY in your .env file."
            )
        headers = {
            "Accept": "application/json",
            "User-Agent": "CryptoVision (+https://github.com/CaioVenxncio/cryptovision-dashboard)",
            API_KEY_HEADER: api_key.get_secret_value(),
        }
        self._http = HttpJsonClient(
            base_url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            retry_policy=retry_policy,
            session=session,
            sleep=sleep or time.sleep,
            auth_error_message=(
                "The provider rejected the API key (HTTP {status}). "
                "Check COINGECKO_API_KEY and that it is a Demo plan key."
            ),
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> CoinGeckoClient:
        return cls(
            settings.coingecko_api_key,
            base_url=settings.coingecko_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            retry_policy=RetryPolicy(max_retries=settings.http_max_retries),
            **kwargs,
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(http={self._http!r})"

    def get_markets(
        self, vs_currency: str = "usd", *, per_page: int = 100, page: int = 1
    ) -> MarketSnapshot:
        """Fetch one page of assets ordered by market cap (one API credit)."""
        _validate_vs_currency(vs_currency)
        if not 1 <= per_page <= MAX_PER_PAGE:
            raise ValueError(f"per_page must be between 1 and {MAX_PER_PAGE}")
        if page < 1:
            raise ValueError("page must be >= 1")

        payload = self._http.get_json(
            MARKETS_ENDPOINT,
            {
                "vs_currency": vs_currency,
                "order": "market_cap_desc",
                "per_page": str(per_page),
                "page": str(page),
                "sparkline": "false",
            },
        )
        fetched_at = self._clock()
        if not isinstance(payload, list):
            raise ResponseSchemaError(f"{MARKETS_ENDPOINT} returned an unexpected structure.")

        coins: list[MarketCoin] = []
        dropped = 0
        for item in payload:
            try:
                coins.append(MarketCoin.model_validate(item))
            except ValidationError:
                dropped += 1
        if dropped:
            logger.warning("Dropped %d invalid records from %s", dropped, MARKETS_ENDPOINT)
        if payload and not coins:
            raise ResponseSchemaError(f"{MARKETS_ENDPOINT} returned no valid records.")

        return MarketSnapshot(
            provider=PROVIDER_NAME,
            endpoint=MARKETS_ENDPOINT,
            vs_currency=vs_currency,
            fetched_at=fetched_at,
            coins=tuple(coins),
            dropped_records=dropped,
        )

    def get_simple_price(self, ids: Sequence[str], vs_currency: str = "usd") -> SimplePriceResult:
        """Fetch price, market cap, 24h volume and 24h change for specific coin ids."""
        _validate_vs_currency(vs_currency)
        clean_ids = list(dict.fromkeys(i.strip().lower() for i in ids if i.strip()))
        if not clean_ids:
            raise ValueError("At least one coin id is required")

        payload = self._http.get_json(
            SIMPLE_PRICE_ENDPOINT,
            {
                "ids": ",".join(clean_ids),
                "vs_currencies": vs_currency,
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_last_updated_at": "true",
            },
        )
        fetched_at = self._clock()
        if not isinstance(payload, dict):
            raise ResponseSchemaError(f"{SIMPLE_PRICE_ENDPOINT} returned an unexpected structure.")

        quotes: dict[str, SimplePriceQuote] = {}
        missing: list[str] = []
        for coin_id in clean_ids:
            entry = payload.get(coin_id)
            if entry is None:
                missing.append(coin_id)
                continue
            if not isinstance(entry, dict):
                raise ResponseSchemaError(f"{SIMPLE_PRICE_ENDPOINT} returned an invalid entry.")
            try:
                quotes[coin_id] = SimplePriceQuote(
                    id=coin_id,
                    vs_currency=vs_currency,
                    price=entry.get(vs_currency),
                    market_cap=entry.get(f"{vs_currency}_market_cap"),
                    volume_24h=entry.get(f"{vs_currency}_24h_vol"),
                    change_24h_percent=entry.get(f"{vs_currency}_24h_change"),
                    last_updated=entry.get("last_updated_at"),
                )
            except ValidationError:
                raise ResponseSchemaError(
                    f"{SIMPLE_PRICE_ENDPOINT} returned invalid values for {coin_id}."
                ) from None

        return SimplePriceResult(
            provider=PROVIDER_NAME,
            endpoint=SIMPLE_PRICE_ENDPOINT,
            fetched_at=fetched_at,
            quotes=quotes,
            missing_ids=tuple(missing),
        )

    def get_daily_market_chart(
        self, coin_id: str, *, days: int, vs_currency: str = "usd"
    ) -> MarketChart:
        """Fetch daily price, market cap and volume history for one coin (one API credit).

        No `interval` parameter is sent. Daily granularity comes from the documented
        automatic rule for ranges above 90 days. The response may also contain a
        final intraday point for the current day; callers must handle it.
        """
        _validate_vs_currency(vs_currency)
        if not _COIN_ID_PATTERN.match(coin_id):
            raise ValueError(f"Invalid coin id: {coin_id!r}")
        if not MIN_DAILY_CHART_DAYS <= days <= MAX_DEMO_CHART_DAYS:
            raise ValueError(
                f"days must be between {MIN_DAILY_CHART_DAYS} and {MAX_DEMO_CHART_DAYS} "
                "for daily data on the Demo plan"
            )
        path = MARKET_CHART_ENDPOINT.format(id=coin_id)
        payload = self._http.get_json(path, {"vs_currency": vs_currency, "days": str(days)})
        fetched_at = self._clock()
        if not isinstance(payload, dict) or not all(
            isinstance(payload.get(key), list) for key in ("prices", "market_caps", "total_volumes")
        ):
            raise ResponseSchemaError(f"{path} returned an unexpected structure.")
        try:
            return MarketChart(
                provider=PROVIDER_NAME,
                endpoint=MARKET_CHART_ENDPOINT,
                coin_id=coin_id,
                vs_currency=vs_currency,
                days=days,
                fetched_at=fetched_at,
                prices=payload["prices"],
                market_caps=payload["market_caps"],
                total_volumes=payload["total_volumes"],
            )
        except (ValidationError, ValueError):
            raise ResponseSchemaError(f"{path} returned invalid data points.") from None
