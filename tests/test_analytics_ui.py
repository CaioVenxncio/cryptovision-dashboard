"""Historical Analytics page and chart builders, using synthetic datasets only."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from cryptovision.analytics.correlation import correlation_matrix, rolling_correlation
from cryptovision.analytics.models import CorrelationMethod, ReturnType
from cryptovision.analytics.returns import log_returns
from cryptovision.analytics.volatility import rolling_volatility
from cryptovision.data import pipeline
from cryptovision.data.synthetic import generate_synthetic_ohlcv, synthetic_config
from cryptovision.ui import analytics_charts
from cryptovision.ui.analytics_view import available_datasets, default_assets
from tests.analytics_helpers import panel

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")
PAGE = "views/historical_analytics.py"


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def store(data_dir: Path, *, anomalies: bool = False, days: int = 120) -> pipeline.CollectionResult:
    config = synthetic_config(start=date(2024, 1, 1), days=days, seed=3, with_anomalies=anomalies)
    frame = generate_synthetic_ohlcv(
        start=date(2024, 1, 1), days=days, seed=3, with_anomalies=anomalies
    )
    plan = pipeline.plan_dataset(config, data_dir)
    collected = pipeline.CollectedData(frame=frame, source={"name": "synthetic"})
    return pipeline.store_dataset(plan, collected, config_sha256="0" * 64, replace=False)


def markdown(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def open_analytics(monkeypatch, data_dir: Path) -> AppTest:
    monkeypatch.setenv("CRYPTOVISION_DATA_DIR", str(data_dir))
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    return at.switch_page(PAGE).run()


def test_market_explorer_is_the_default_page(mocked_api):
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not at.exception
    assert [m.value for m in at.markdown if "Market Explorer" in m.value]


def test_no_datasets_message(monkeypatch, tmp_path, mocked_api):
    at = open_analytics(monkeypatch, tmp_path)
    assert not at.exception
    assert any("No research-ready local dataset" in i.value for i in at.info)
    assert len(mocked_api.calls) == 0


def test_analytics_page_renders_offline(monkeypatch, tmp_path, mocked_api):
    store(tmp_path)
    at = open_analytics(monkeypatch, tmp_path)

    assert not at.exception, at.exception
    assert not at.error
    assert any("synthetic data" in w.value for w in at.warning)
    text = markdown(at)
    for section in ("Historical Analytics", "<h2>Summary</h2>", "<h2>Charts</h2>"):
        assert section in text
    assert "Quote <b>SYNTH</b>" in text  # provenance row
    assert [t.label for t in at.tabs] == ["Price", "Volatility", "Drawdown", "Correlation"]
    assert at.dataframe[0].proto.alt  # summary table carries a text alternative
    assert len(mocked_api.calls) == 0  # no network


def test_controls_update_results(monkeypatch, tmp_path, mocked_api):
    store(tmp_path)
    at = open_analytics(monkeypatch, tmp_path)

    at.radio[0].set_value(ReturnType.SIMPLE).run()
    at.radio[3].set_value(CorrelationMethod.SPEARMAN).run()
    at.radio[1].set_value(7).run()
    at.slider[0].set_value((date(2024, 1, 15), date(2024, 3, 31))).run()

    assert not at.exception, at.exception
    assert "2024-01-15 to 2024-03-31 · simple returns" in markdown(at)
    assert any("Spearman correlation" in c.value for c in at.caption)


def test_single_asset_skips_correlation(monkeypatch, tmp_path, mocked_api):
    store(tmp_path)
    at = open_analytics(monkeypatch, tmp_path)
    at.multiselect[0].set_value(["synthetic-a"]).run()

    assert not at.exception
    assert any("at least two assets" in i.value for i in at.info)


def test_no_asset_selected(monkeypatch, tmp_path, mocked_api):
    store(tmp_path)
    at = open_analytics(monkeypatch, tmp_path)
    at.multiselect[0].set_value([]).run()
    assert any("Select at least one asset" in i.value for i in at.info)


def test_too_short_period_is_reported_not_crashing(monkeypatch, tmp_path, mocked_api):
    store(tmp_path)
    at = open_analytics(monkeypatch, tmp_path)
    at.slider[0].set_value((date(2024, 1, 1), date(2024, 1, 1))).run()
    assert not at.exception, at.exception


def test_unready_and_expired_datasets_are_not_offered(tmp_path):
    ready = store(tmp_path)
    store(tmp_path, anomalies=True)
    options = available_datasets(tmp_path)
    assert [o.path for o in options] == [ready.path]
    assert options[0].label.endswith("[SYNTHETIC]")


def test_expired_cache_is_filtered(tmp_path, monkeypatch):
    store(tmp_path)
    original = pipeline.list_datasets(tmp_path)
    path, manifest = original[0]
    expired = manifest.model_copy(
        update={"expires_at": datetime(2026, 1, 1, tzinfo=UTC), "retention": "ephemeral"}
    )
    monkeypatch.setattr("cryptovision.ui.analytics_view.list_datasets", lambda _: [(path, expired)])
    assert available_datasets(tmp_path, now=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(1)) == []


def test_tampered_dataset_shows_error(monkeypatch, tmp_path, mocked_api):
    stored = store(tmp_path)
    data = stored.path / "data.parquet"
    data.write_bytes(data.read_bytes()[:-5])
    at = open_analytics(monkeypatch, tmp_path)
    assert any("could not be loaded safely" in e.value for e in at.error)


def test_default_assets():
    assert default_assets(("bitcoin", "cardano", "ethereum", "litecoin")) == [
        "bitcoin",
        "ethereum",
        "cardano",
    ]
    assert default_assets(("x", "y", "z", "w")) == ["x", "y", "z"]


# --- Chart builders -------------------------------------------------------------------


@pytest.fixture
def returns():
    prices = {
        "a": [100.0, 102.0, 99.0, 103.0, None, 105.0, 104.0, 108.0],
        "b": [50.0, 50.5, 49.0, 51.0, 52.0, 52.5, 51.5, 53.0],
    }
    return log_returns(panel(prices))


def test_price_and_drawdown_charts_keep_gaps(returns):
    prices = returns.panel.prices
    price = analytics_charts.price_chart(prices, quote_currency="USDT")
    assert [t.name for t in price.data] == ["a", "b"]
    assert price.layout.yaxis.type == "log"
    assert "USDT" in price.layout.yaxis.title.text
    assert math.isnan(price.data[0].y[4])  # missing day is not filled
    assert price.data[0].connectgaps is False

    drawdown = analytics_charts.drawdown_chart(prices)
    assert min(drawdown.data[1].y) == pytest.approx(49.0 / 50.5 - 1)


def test_volatility_and_correlation_charts(returns):
    vol = analytics_charts.rolling_volatility_chart(rolling_volatility(returns, window=3))
    assert vol.layout.yaxis.title.text == "Annualized volatility (3-day window)"

    daily = rolling_volatility(returns, window=3, annualize_result=False)
    assert analytics_charts.rolling_volatility_chart(daily).layout.yaxis.title.text.startswith(
        "Daily"
    )

    matrix = correlation_matrix(returns, min_overlap=3)
    heatmap = analytics_charts.correlation_heatmap(matrix)
    assert heatmap.data[0].zmin == -1 and heatmap.data[0].zmax == 1
    assert heatmap.data[0].customdata[0][1] == matrix.counts.loc["a", "b"]

    strict = correlation_matrix(returns, min_overlap=50)
    assert analytics_charts.correlation_heatmap(strict).data[0].text[0][1] == "n/a"

    rolling = rolling_correlation(returns, "a", "b", window=3)
    chart = analytics_charts.rolling_correlation_chart(rolling)
    assert chart.data[0].name == "a / b"
    assert list(chart.layout.yaxis.range) == [-1, 1]


def test_invalid_configuration_on_analytics_page(monkeypatch, tmp_path, mocked_api):
    monkeypatch.setenv("CACHE_TTL_SECONDS", "1")
    at = open_analytics(monkeypatch, tmp_path)
    assert any("CACHE_TTL_SECONDS" in e.value for e in at.error)
