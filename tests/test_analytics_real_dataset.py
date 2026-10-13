"""Validation against the real local Binance dataset, when it exists.

The dataset is git-ignored (provider terms), so these tests are skipped in CI
and on fresh clones. References are computed independently: the Parquet file
is read directly with pyarrow (not through CryptoVision's loader) and metrics
are computed with plain NumPy, the `statistics` module and SciPy.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest
from scipy import stats

from cryptovision.analytics.correlation import correlation_matrix, rolling_correlation
from cryptovision.analytics.data import load_price_panel
from cryptovision.analytics.descriptive import describe_assets
from cryptovision.analytics.returns import compute_returns
from cryptovision.analytics.volatility import rolling_volatility

DATASET = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "datasets"
    / "binance-spot-1d-top10-20210103"
    / "1.0.0"
)

pytestmark = pytest.mark.skipif(
    not (DATASET / "manifest.json").exists(), reason="real Binance dataset not available locally"
)

ASSETS = ("bitcoin", "ethereum", "cardano")


@pytest.fixture(scope="module")
def raw_closes() -> dict[str, np.ndarray]:
    """Independent read: close prices per asset, sorted by time, straight from Parquet."""
    table = pq.read_table(DATASET / "data.parquet", columns=["timestamp_utc", "asset_id", "close"])
    rows = table.to_pylist()
    closes = {}
    for asset in ASSETS:
        series = sorted((r["timestamp_utc"], r["close"]) for r in rows if r["asset_id"] == asset)
        days = [t for t, _ in series]
        gaps = {(b - a).days for a, b in zip(days, days[1:], strict=False)}
        assert gaps == {1}, "the reference assumes consecutive days"
        closes[asset] = np.array([c for _, c in series])
    return closes


@pytest.fixture(scope="module")
def returns():
    return compute_returns(load_price_panel(DATASET, assets=list(ASSETS)), "log")


def test_dataset_context(returns):
    context = returns.panel.context
    manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    assert context.provider == "binance_vision"
    assert context.quote_currency == "USDT"  # exchange prices in USDT, not USD
    assert context.content_sha256 == manifest["content_sha256"]
    assert context.pairs["bitcoin"] == "BTCUSDT"


def test_log_returns_match_reference(raw_closes, returns):
    for asset in ASSETS:
        expected = np.diff(np.log(raw_closes[asset]))
        # ln(P_t / P_t-1) and ln(P_t) - ln(P_t-1) differ only by rounding (< 1e-14).
        np.testing.assert_allclose(
            returns.series(asset).to_numpy(), expected, rtol=1e-12, atol=1e-14
        )


def test_volatility_matches_statistics_module(raw_closes, returns):
    table = describe_assets(returns).table
    for asset in ASSETS:
        reference = statistics.stdev(np.diff(np.log(raw_closes[asset])).tolist())
        assert table.loc[asset, "daily_volatility"] == pytest.approx(reference, rel=1e-10)
        assert table.loc[asset, "annualized_volatility"] == pytest.approx(
            reference * math.sqrt(365), rel=1e-10
        )


def test_max_drawdown_matches_loop_reference(raw_closes, returns):
    table = describe_assets(returns).table
    for asset in ASSETS:
        peak, worst = -math.inf, 0.0
        for price in raw_closes[asset]:
            peak = max(peak, price)
            worst = min(worst, price / peak - 1)
        assert table.loc[asset, "max_drawdown"] == pytest.approx(worst, rel=1e-12)


def test_btc_eth_correlation_matches_scipy(raw_closes, returns):
    btc = np.diff(np.log(raw_closes["bitcoin"]))
    eth = np.diff(np.log(raw_closes["ethereum"]))
    pearson = correlation_matrix(returns, method="pearson")
    spearman = correlation_matrix(returns, method="spearman")
    assert pearson.matrix.loc["bitcoin", "ethereum"] == pytest.approx(
        stats.pearsonr(btc, eth).statistic, rel=1e-10
    )
    assert spearman.matrix.loc["bitcoin", "ethereum"] == pytest.approx(
        stats.spearmanr(btc, eth).statistic, rel=1e-10
    )
    assert pearson.counts.loc["bitcoin", "ethereum"] == len(btc)


def test_rolling_metrics_match_reference_windows(raw_closes, returns):
    btc = np.diff(np.log(raw_closes["bitcoin"]))
    eth = np.diff(np.log(raw_closes["ethereum"]))
    vol = rolling_volatility(returns, window=30, annualize_result=False).values["bitcoin"]
    corr = rolling_correlation(returns, "bitcoin", "ethereum", window=90).values["bitcoin|ethereum"]
    # Row k of the panel holds the return ending on day k; returns start on row 1.
    for end in (29, 500, len(btc) - 1):
        expected_vol = statistics.stdev(btc[end - 29 : end + 1].tolist())
        assert vol.iloc[end + 1] == pytest.approx(expected_vol, rel=1e-9)
    for end in (89, 1000, len(btc) - 1):
        window = slice(end - 89, end + 1)
        expected_corr = stats.pearsonr(btc[window], eth[window]).statistic
        assert corr.iloc[end + 1] == pytest.approx(expected_corr, rel=1e-9)
