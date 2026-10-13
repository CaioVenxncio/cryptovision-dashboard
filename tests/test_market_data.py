"""Caching, staleness and failure-cooldown behavior of the app's data loader."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import streamlit as st

from cryptovision.config import Settings
from cryptovision.ui.market_data import (
    FAILURE_COOLDOWN_SECONDS,
    FAILURE_STATE_KEY,
    MIN_MANUAL_REFRESH_SECONDS,
    load_market_snapshot,
    refresh_allowed,
    snapshot_age_seconds,
)
from tests.conftest import BASE_URL, FAKE_KEY, load_fixture

MARKETS_URL = f"{BASE_URL}/coins/markets"


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(coingecko_api_key=FAKE_KEY, http_max_retries=0, cache_ttl_seconds=900)


class FakeMonotonic:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


def test_second_load_is_served_from_cache(settings, mocked_api):
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))
    state: dict = {}

    first = load_market_snapshot(settings, state)
    second = load_market_snapshot(settings, state)

    assert first.newly_fetched is True
    assert second.newly_fetched is False
    assert second.snapshot == first.snapshot
    assert len(mocked_api.calls) == 1


def test_expired_cache_triggers_exactly_one_new_request(settings, mocked_api):
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))
    state: dict = {}
    load_market_snapshot(settings, state)

    later = datetime.now(UTC) + timedelta(seconds=settings.cache_ttl_seconds + 1)
    result = load_market_snapshot(settings, state, now=lambda: later)

    assert result.snapshot is not None
    assert len(mocked_api.calls) == 2


def test_missing_key_reports_without_request(mocked_api):
    result = load_market_snapshot(Settings(), {})

    assert result.missing_api_key is True
    assert result.snapshot is None
    assert len(mocked_api.calls) == 0


def test_failure_starts_cooldown_then_recovers(settings, mocked_api):
    mocked_api.get(MARKETS_URL, status=503)
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))
    state: dict = {}
    clock = FakeMonotonic()

    failed = load_market_snapshot(settings, state, monotonic=clock)
    assert failed.snapshot is None
    assert "HTTP 503" in failed.error_message
    assert failed.retry_in_seconds == FAILURE_COOLDOWN_SECONDS
    assert FAILURE_STATE_KEY in state

    clock.value += FAILURE_COOLDOWN_SECONDS - 1
    blocked = load_market_snapshot(settings, state, monotonic=clock)
    assert blocked.error_message == failed.error_message
    assert blocked.retry_in_seconds == pytest.approx(1)
    assert len(mocked_api.calls) == 1

    clock.value += 2
    recovered = load_market_snapshot(settings, state, monotonic=clock)
    assert recovered.snapshot is not None
    assert recovered.error_message is None
    assert FAILURE_STATE_KEY not in state
    assert len(mocked_api.calls) == 2


def test_rate_limit_cooldown_respects_retry_after(settings, mocked_api):
    mocked_api.get(MARKETS_URL, status=429, headers={"Retry-After": "120"})

    result = load_market_snapshot(settings, {}, monotonic=FakeMonotonic())

    assert result.retry_in_seconds == 120
    assert "429" in result.error_message


def test_failure_message_never_contains_key(settings, mocked_api):
    mocked_api.get(MARKETS_URL, status=401)

    result = load_market_snapshot(settings, {})

    assert "rejected the API key" in result.error_message
    assert FAKE_KEY not in result.error_message


def test_failures_are_not_cached(settings, mocked_api):
    mocked_api.get(MARKETS_URL, status=500)
    mocked_api.get(MARKETS_URL, json=[])
    clock = FakeMonotonic()
    state: dict = {}

    load_market_snapshot(settings, state, monotonic=clock)
    clock.value += FAILURE_COOLDOWN_SECONDS + 1
    result = load_market_snapshot(settings, state, monotonic=clock)

    assert result.snapshot is not None
    assert result.snapshot.coins == ()


@pytest.mark.parametrize(
    ("age", "allowed"),
    [
        (None, True),
        (0, False),
        (MIN_MANUAL_REFRESH_SECONDS - 1, False),
        (MIN_MANUAL_REFRESH_SECONDS, True),
    ],
)
def test_refresh_allowed(age, allowed):
    assert refresh_allowed(age) is allowed


def test_snapshot_age_is_never_negative(settings, mocked_api):
    mocked_api.get(MARKETS_URL, json=[])
    snapshot = load_market_snapshot(settings, {}).snapshot
    assert snapshot_age_seconds(snapshot, snapshot.fetched_at - timedelta(seconds=5)) == 0
    assert snapshot_age_seconds(snapshot, snapshot.fetched_at + timedelta(seconds=90)) == 90
