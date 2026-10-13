"""Descriptive summaries and loading through the validated dataset loader."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from cryptovision.analytics.data import load_price_panel
from cryptovision.analytics.descriptive import describe_assets
from cryptovision.analytics.returns import log_returns, simple_returns
from cryptovision.data import pipeline
from cryptovision.data.config import DatasetConfig
from cryptovision.data.errors import (
    DatasetExpiredError,
    DatasetIntegrityError,
    DatasetNotReadyError,
)
from cryptovision.data.synthetic import generate_synthetic_ohlcv, synthetic_config
from tests.analytics_helpers import panel


def test_describe_hand_calculated():
    prices = {
        "a": [100.0, 110.0, 99.0, 99.0, None, 120.0],
        "b": [10.0, 11.0, None, None, None, None],
    }
    table = describe_assets(simple_returns(panel(prices)), min_observations=3).table

    a = table.loc["a"]
    assert a["price_observations"] == 5
    assert a["missing_days"] == 1
    assert a["return_observations"] == 3
    assert a["undefined_returns"] == 1  # day 6 follows the gap
    assert a["mean_return"] == pytest.approx(0.0, abs=1e-15)
    assert a["median_return"] == pytest.approx(0.0, abs=1e-15)
    assert (a["min_return"], a["max_return"]) == pytest.approx((-0.1, 0.1))
    assert a["daily_volatility"] == pytest.approx(0.1)
    assert a["annualized_volatility"] == pytest.approx(0.1 * math.sqrt(365))
    assert a["max_drawdown"] == pytest.approx(-0.1)
    assert a["drawdown_peak"] == date(2024, 1, 2)
    assert a["drawdown_recovered"] is True
    assert (a["first_observation"], a["last_observation"]) == (date(2024, 1, 1), date(2024, 1, 6))

    b = table.loc["b"]
    assert b["return_observations"] == 1
    assert math.isnan(b["daily_volatility"])  # below min_observations
    assert b["max_drawdown"] == 0.0  # two rising prices: no drawdown
    assert b["drawdown_recovered"] is None


def test_describe_metadata():
    summary = describe_assets(log_returns(panel({"a": [1.0, 2.0, 3.0]})), min_observations=2)
    metadata = summary.metadata.to_dict()
    assert metadata["calculation"] == "descriptive_summary"
    assert metadata["annualization_factor"] == 365
    assert metadata["return_type"] == "log"


# --- Loading through the Phase 3 loader ---------------------------------------------


def store(tmp_path, *, anomalies=False):
    config = synthetic_config(start=date(2024, 1, 1), days=60, seed=9, with_anomalies=anomalies)
    frame = generate_synthetic_ohlcv(
        start=date(2024, 1, 1), days=60, seed=9, with_anomalies=anomalies
    )
    plan = pipeline.plan_dataset(config, tmp_path)
    collected = pipeline.CollectedData(frame=frame, source={"name": "synthetic"})
    return pipeline.store_dataset(plan, collected, config_sha256="0" * 64, replace=False)


def test_load_price_panel_carries_manifest_context(tmp_path):
    stored = store(tmp_path)
    loaded = load_price_panel(stored.path, assets=["synthetic-a", "synthetic-b"])

    context = loaded.context
    assert context.dataset_id == stored.manifest.dataset_id
    assert context.content_sha256 == stored.manifest.content_sha256
    assert context.quote_currency == "SYNTH"
    assert context.synthetic is True
    assert context.price_column == "close"
    assert context.pairs == {}  # synthetic assets declare no exchange pair
    assert loaded.assets == ("synthetic-a", "synthetic-b")
    assert loaded.prices.shape == (60, 2)


def test_load_price_panel_with_period(tmp_path):
    stored = store(tmp_path)
    loaded = load_price_panel(stored.path, start=date(2024, 1, 10), end=date(2024, 1, 19))
    assert (loaded.start, loaded.end) == (date(2024, 1, 10), date(2024, 1, 19))
    assert len(loaded.prices) == 10


def test_loader_refuses_unready_and_tampered_datasets(tmp_path):
    unready = store(tmp_path, anomalies=True)
    with pytest.raises(DatasetNotReadyError):
        load_price_panel(unready.path)

    ready = store(tmp_path)
    data_file = ready.path / "data.parquet"
    data_file.write_bytes(data_file.read_bytes()[:-10])
    with pytest.raises(DatasetIntegrityError):
        load_price_panel(ready.path)


def test_loader_refuses_expired_caches(tmp_path, client, mocked_api):
    config = DatasetConfig.model_validate(
        {
            "id": "cg",
            "version": "1.0.0",
            "description": "mocked",
            "provider": "coingecko",
            "quote_currency": "USD",
            "lookback_days": 100,
            "selection": {"rule": "test"},
            "assets": [{"asset_id": "bitcoin", "symbol": "BTC", "coingecko_id": "bitcoin"}],
        }
    )
    now = datetime(2026, 10, 13, 12, tzinfo=UTC)
    plan = pipeline.plan_dataset(config, tmp_path, now=now)
    day0 = datetime.combine(plan.start, datetime.min.time(), UTC)
    stamps = [int((day0 + timedelta(days=i)).timestamp() * 1000) for i in range(100)]
    mocked_api.get(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        json={
            "prices": [[s, 100.0 + i] for i, s in enumerate(stamps)],
            "market_caps": [[s, 1e9] for s in stamps],
            "total_volumes": [[s, 1e6] for s in stamps],
        },
    )
    stored = pipeline.store_dataset(
        plan,
        pipeline.collect_coingecko(plan, client),
        config_sha256="0" * 64,
        replace=False,
        now=now,
    )
    expires = stored.manifest.expires_at

    valid = load_price_panel(stored.path, now=expires - timedelta(minutes=1))
    assert valid.context.price_column == "price"
    assert valid.context.quote_currency == "USD"
    with pytest.raises(DatasetExpiredError):
        load_price_panel(stored.path, now=expires)
