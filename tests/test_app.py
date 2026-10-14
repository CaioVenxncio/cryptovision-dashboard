"""End-to-end checks of the Streamlit app with a mocked CoinGecko API."""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from cryptovision.ui import market_data
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


def all_text(at: AppTest) -> str:
    parts = [e.value for e in at.markdown] + [e.value for e in at.caption]
    parts += (
        [e.value for e in at.error] + [e.value for e in at.warning] + [e.value for e in at.info]
    )
    return "\n".join(str(p) for p in parts)


def test_renders_market_data(configured, mocked_api):
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))

    at = run_app()

    assert not at.exception
    assert not at.error
    labels = [metric.label for metric in at.metric]
    assert labels == [
        "Market cap · selected",
        "24h volume · selected",
        "Market cap change · 24h",
        "Assets shown",
    ]
    assert not any("Total" in label for label in labels)  # selected assets, not the market
    assert [metric.value for metric in at.metric] == ["$1.50T", "$45.00B", "▲ +1.01%", "3"]
    assert len(at.dataframe) == 1
    text = all_text(at)
    assert "Top 3 assets" in text
    assert "Provider update <b>2026-10-13 12:01:00 UTC</b>" in text
    assert "retrieved just now" in text
    assert "Powered by CoinGecko" in text
    assert "1 asset(s) report no market cap" in text
    assert "Demo mode" not in text


def test_slider_and_reruns_reuse_cached_data(configured, mocked_api):
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))

    at = run_app()
    at.radio[0].set_value(25).run()
    at.radio[0].set_value(50).run()
    at.toggle[0].set_value(True).run()
    at.run()

    assert not at.exception
    assert len(mocked_api.calls) == 1
    assert "cached copy" in all_text(at)


def test_refresh_button_disabled_while_data_is_fresh(configured, mocked_api):
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))

    at = run_app()

    assert at.button[0].label == "Refresh data"
    assert at.button[0].disabled is True


def test_refresh_button_fetches_new_data_when_allowed(configured, mocked_api, monkeypatch):
    monkeypatch.setattr(market_data, "MIN_MANUAL_REFRESH_SECONDS", 0)
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))

    at = run_app()
    assert at.button[0].disabled is False
    at.button[0].click().run()

    assert not at.exception
    assert len(mocked_api.calls) == 2


def test_missing_key_shows_setup_instructions_without_requests(mocked_api):
    at = run_app()

    assert not at.exception
    assert any("No CoinGecko API key" in warning.value for warning in at.warning)
    assert len(mocked_api.calls) == 0


def test_invalid_configuration_stops_before_any_request(configured, monkeypatch, mocked_api):
    monkeypatch.setenv("CACHE_TTL_SECONDS", "5")

    at = run_app()

    assert not at.exception
    assert "CACHE_TTL_SECONDS" in at.error[0].value
    assert len(at.metric) == 0
    assert len(mocked_api.calls) == 0


def test_provider_failure_is_reported_safely_and_not_retried_on_rerun(configured, mocked_api):
    mocked_api.get(MARKETS_URL, status=503)

    at = run_app()
    at.radio[0].set_value(25).run()

    assert not at.exception
    messages = " ".join(error.value for error in at.error)
    assert "Market data is unavailable" in messages
    assert FAKE_KEY not in messages
    assert any("try again" in info.value for info in at.info)
    # The failure cooldown prevents a second request on the rerun.
    assert len(mocked_api.calls) == 1


def test_app_recovers_after_cooldown(configured, mocked_api, monkeypatch):
    monkeypatch.setattr(market_data, "FAILURE_COOLDOWN_SECONDS", 0)
    mocked_api.get(MARKETS_URL, status=503)
    mocked_api.get(MARKETS_URL, json=load_fixture("coins_markets.json"))

    at = run_app()
    assert at.error
    at.run()

    assert not at.error
    assert len(at.metric) == 4
    assert len(mocked_api.calls) == 2


def test_auth_failure_message(configured, mocked_api):
    mocked_api.get(MARKETS_URL, status=401)

    at = run_app()

    assert any("rejected the API key" in error.value for error in at.error)


def test_empty_provider_response(configured, mocked_api):
    mocked_api.get(MARKETS_URL, json=[])

    at = run_app()

    assert not at.exception
    assert any("no market data" in info.value for info in at.info)


def test_invalid_records_are_reported(configured, mocked_api):
    payload = load_fixture("coins_markets.json") + [{"name": "missing id"}]
    mocked_api.get(MARKETS_URL, json=payload)

    at = run_app()

    assert any("1 record(s)" in warning.value for warning in at.warning)


def test_demo_mode_needs_no_key_and_makes_no_requests(monkeypatch, mocked_api):
    monkeypatch.setenv("CRYPTOVISION_DEMO", "1")

    at = run_app()

    assert not at.exception
    assert any("Demo mode" in w.value for w in at.warning)
    assert [m.label for m in at.metric][0] == "Market cap · selected"
    assert "synthetic demo snapshot" in all_text(at)
    assert not any(b.label == "Refresh data" for b in at.button)  # nothing to refresh
    assert len(mocked_api.calls) == 0
