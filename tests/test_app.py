"""End-to-end checks of the Streamlit app with a mocked CoinGecko API."""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from tests.conftest import BASE_URL, FAKE_KEY, load_fixture

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")
MARKETS_URL = f"{BASE_URL}/coins/markets"


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", FAKE_KEY)
    monkeypatch.setenv("HTTP_MAX_RETRIES", "0")


def run_app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=30).run()


def test_renders_market_data(configured, mocked_api):
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))

    at = run_app()

    assert not at.exception
    assert not at.error
    labels = [metric.label for metric in at.metric]
    assert "Selected Assets Market Cap" in labels
    assert not any("Total" in label for label in labels)
    assert len(at.dataframe) == 1


def test_slider_and_reruns_reuse_cached_data(configured, mocked_api):
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))

    at = run_app()
    at.slider[0].set_value(5).run()
    at.slider[0].set_value(20).run()
    at.run()

    assert not at.exception
    assert len(mocked_api.calls) == 1


def test_missing_key_shows_setup_instructions_without_requests(mocked_api):
    at = run_app()

    assert not at.exception
    assert any("No CoinGecko API key" in warning.value for warning in at.warning)
    assert len(mocked_api.calls) == 0


def test_provider_failure_is_reported_safely_and_not_retried_on_rerun(configured, mocked_api):
    mocked_api.get(MARKETS_URL, status=503)

    at = run_app()
    at.slider[0].set_value(15).run()

    assert not at.exception
    messages = " ".join(error.value for error in at.error)
    assert "Market data is unavailable" in messages
    assert FAKE_KEY not in messages
    # The failure cooldown prevents a second request on the rerun.
    assert len(mocked_api.calls) == 1


def test_auth_failure_message(configured, mocked_api):
    mocked_api.get(MARKETS_URL, status=401)

    at = run_app()

    assert any("rejected the API key" in error.value for error in at.error)
