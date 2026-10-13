"""Market data loading for the Streamlit app: caching, staleness and failure cooldown.

Streamlit reruns the whole script on every interaction. This module makes sure
those reruns reuse one cached snapshot, so only an expired cache, a manual
refresh or a recovered failure contacts the provider.
"""

from __future__ import annotations

import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import streamlit as st

from cryptovision.config import Settings
from cryptovision.models import MarketSnapshot
from cryptovision.providers.coingecko import CoinGeckoClient
from cryptovision.providers.errors import MissingApiKeyError, ProviderError, RateLimitError

VS_CURRENCY = "usd"
# One request returns enough assets for every slider position, so moving the
# slider never triggers a new API call.
MARKET_FETCH_SIZE = 100
# CoinGecko Demo data updates about every 60 s; refreshing faster wastes credits.
MIN_MANUAL_REFRESH_SECONDS = 60
# After a failed request, wait before contacting the provider again.
FAILURE_COOLDOWN_SECONDS = 60
FAILURE_STATE_KEY = "market_last_failure"


@dataclass(frozen=True)
class MarketLoadResult:
    """Outcome of one load attempt. Exactly one of the cases applies."""

    snapshot: MarketSnapshot | None = None
    newly_fetched: bool = False
    missing_api_key: bool = False
    error_message: str | None = None
    retry_in_seconds: float | None = None


@st.cache_data(max_entries=4, show_spinner=False)
def _fetch_market_snapshot(vs_currency: str, per_page: int, _settings: Settings) -> MarketSnapshot:
    # `_settings` is excluded from the cache key (leading underscore), so the
    # API key never influences cache hashing. Failures are not cached.
    client = CoinGeckoClient.from_settings(_settings)
    return client.get_markets(vs_currency, per_page=per_page)


def clear_market_cache() -> None:
    _fetch_market_snapshot.clear()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def snapshot_age_seconds(snapshot: MarketSnapshot, now: datetime) -> float:
    return max(0.0, (now - snapshot.fetched_at).total_seconds())


def refresh_allowed(age_seconds: float | None) -> bool:
    """Manual refresh is allowed once cached data is at least one provider cycle old."""
    return age_seconds is None or age_seconds >= MIN_MANUAL_REFRESH_SECONDS


def load_market_snapshot(
    settings: Settings,
    state: MutableMapping[str, Any],
    *,
    now: Callable[[], datetime] = _utc_now,
    monotonic: Callable[[], float] = time.monotonic,
) -> MarketLoadResult:
    """Return cached market data, fetching only when the cache is empty or expired.

    `state` is per-session storage (`st.session_state` in the app). A failure
    is recorded there and blocks further requests for a cooldown period.
    """
    failure = state.get(FAILURE_STATE_KEY)
    if failure is not None:
        failed_at, message, cooldown = failure
        remaining = cooldown - (monotonic() - failed_at)
        if remaining > 0:
            return MarketLoadResult(error_message=message, retry_in_seconds=remaining)
        del state[FAILURE_STATE_KEY]

    started_at = now()
    try:
        snapshot = _fetch_market_snapshot(VS_CURRENCY, MARKET_FETCH_SIZE, settings)
        if snapshot_age_seconds(snapshot, started_at) > settings.cache_ttl_seconds:
            clear_market_cache()
            snapshot = _fetch_market_snapshot(VS_CURRENCY, MARKET_FETCH_SIZE, settings)
    except MissingApiKeyError:
        return MarketLoadResult(missing_api_key=True)
    except ProviderError as exc:
        cooldown = float(FAILURE_COOLDOWN_SECONDS)
        if isinstance(exc, RateLimitError) and exc.retry_after_seconds:
            cooldown = max(cooldown, exc.retry_after_seconds)
        message = f"Market data is unavailable: {exc}"
        state[FAILURE_STATE_KEY] = (monotonic(), message, cooldown)
        return MarketLoadResult(error_message=message, retry_in_seconds=cooldown)

    return MarketLoadResult(snapshot=snapshot, newly_fetched=snapshot.fetched_at >= started_at)
