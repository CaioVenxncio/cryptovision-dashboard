"""Correlation against hand calculations and SciPy as an independent reference."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from cryptovision.analytics.correlation import (
    CONSTANT,
    INSUFFICIENT,
    correlation_matrix,
    pair_correlation,
    rolling_correlation,
)
from cryptovision.analytics.exceptions import UnknownAssetError
from cryptovision.analytics.models import CorrelationMethod
from cryptovision.analytics.returns import ReturnsResult, compute_returns, simple_returns
from tests.analytics_helpers import panel


def returns_from(values: dict[str, list[float | None]]) -> ReturnsResult:
    """Build a ReturnsResult whose returns are exactly `values` (prices are irrelevant here)."""
    days = len(next(iter(values.values())))
    base = simple_returns(panel({asset: [1.0] * days for asset in values}))
    frame = pd.DataFrame(
        {k: [np.nan if v is None else v for v in vals] for k, vals in values.items()},
        index=base.returns.index,
    )
    return ReturnsResult(
        returns=frame, status=base.status, return_type=base.return_type, panel=base.panel
    )


def test_pearson_hand_calculated():
    # x = [1,2,3], y = [2,4,7]: r = 5 / sqrt(2 * 114/9) = 15 / sqrt(228)
    value = pair_correlation(np.array([1.0, 2.0, 3.0]), np.array([2.0, 4.0, 7.0]))
    assert value == pytest.approx(15 / math.sqrt(228), rel=1e-14)


def test_spearman_with_ties_hand_calculated():
    # ranks x = [1, 2.5, 2.5, 4], y = [1, 3, 2, 4] -> r = 4.5 / sqrt(4.5 * 5)
    x, y = np.array([1.0, 2.0, 2.0, 3.0]), np.array([1.0, 3.0, 2.0, 4.0])
    value = pair_correlation(x, y, "spearman")
    assert value == pytest.approx(4.5 / math.sqrt(22.5), rel=1e-14)
    assert value == pytest.approx(stats.spearmanr(x, y).statistic, rel=1e-12)


def test_perfect_and_inverse_correlation_are_clipped():
    x = np.linspace(-1, 1, 50)
    assert pair_correlation(x, 3 * x + 1) == 1.0
    assert pair_correlation(x, -x) == -1.0


def test_constant_series_correlation_is_undefined():
    assert pair_correlation(np.array([1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0])) is None
    assert pair_correlation(np.array([1.0]), np.array([2.0])) is None
    with pytest.raises(ValueError):
        pair_correlation(np.array([1.0, 2.0]), np.array([1.0]))


@pytest.mark.parametrize("method", ["pearson", "spearman"])
def test_matrix_matches_scipy_on_random_returns(method):
    rng = np.random.default_rng(5)
    common = rng.normal(0, 0.02, 200)
    values = {
        "a": (common + rng.normal(0, 0.01, 200)).tolist(),
        "b": (common + rng.normal(0, 0.03, 200)).tolist(),
        "c": rng.normal(0, 0.02, 200).tolist(),
    }
    result = correlation_matrix(returns_from(values), method=method)
    reference = stats.pearsonr if method == "pearson" else stats.spearmanr
    for a, b in [("a", "b"), ("a", "c"), ("b", "c")]:
        expected = reference(values[a], values[b]).statistic
        assert result.matrix.loc[a, b] == pytest.approx(expected, rel=1e-10)
        assert result.matrix.loc[b, a] == result.matrix.loc[a, b]
    assert np.diag(result.matrix).tolist() == [1.0, 1.0, 1.0]
    assert result.counts.loc["a", "b"] == 200
    assert result.metadata.method is CorrelationMethod(method)


def test_pairwise_deletion_uses_only_common_days():
    a = [0.01, 0.02, None, 0.04, -0.01, 0.03]
    b = [0.02, None, 0.01, 0.05, -0.02, 0.01]
    result = correlation_matrix(returns_from({"a": a, "b": b}), min_overlap=2)
    pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    expected = stats.pearsonr(*zip(*pairs, strict=True)).statistic
    assert result.counts.loc["a", "b"] == 4
    assert result.counts.loc["a", "a"] == 5
    assert result.matrix.loc["a", "b"] == pytest.approx(expected, rel=1e-12)


def test_non_overlapping_and_partially_overlapping_assets():
    early = [0.01, -0.02, 0.03, 0.01, None, None, None, None]
    late = [None, None, None, None, 0.02, 0.01, -0.01, 0.03]
    partial = [None, None, 0.01, 0.02, -0.03, 0.04, None, None]
    result = correlation_matrix(
        returns_from({"early": early, "late": late, "partial": partial}), min_overlap=2
    )
    assert result.counts.loc["early", "late"] == 0
    assert math.isnan(result.matrix.loc["early", "late"])
    assert result.undefined[("early", "late")] == INSUFFICIENT
    assert result.counts.loc["early", "partial"] == 2
    assert not math.isnan(result.matrix.loc["early", "partial"])


def test_min_overlap_and_constant_series_are_reported():
    values = {"a": [0.01, 0.02, -0.01], "b": [0.0, 0.0, 0.0], "c": [0.02, 0.01, 0.0]}
    result = correlation_matrix(returns_from(values), min_overlap=3)
    assert result.undefined[("a", "b")] == CONSTANT
    assert result.undefined[("b", "b")] == CONSTANT
    assert math.isnan(result.matrix.loc["a", "b"])
    assert result.matrix.loc["a", "c"] == pytest.approx(
        stats.pearsonr(values["a"], values["c"]).statistic
    )
    strict = correlation_matrix(returns_from(values), min_overlap=4)
    assert strict.matrix.isna().all().all()
    with pytest.raises(ValueError):
        correlation_matrix(returns_from(values), min_overlap=1)


def test_zero_returns_are_data_not_missing():
    values = {"a": [0.0, 0.01, 0.0, -0.01], "b": [0.0, 0.02, 0.01, -0.02]}
    result = correlation_matrix(returns_from(values), min_overlap=4)
    assert result.counts.loc["a", "b"] == 4


def test_rolling_correlation_hand_checked_windows():
    a = [0.01, 0.02, 0.03, None, 0.01, 0.02, 0.03, 0.04]
    b = [0.02, 0.04, 0.07, 0.01, 0.03, 0.01, 0.05, 0.02]
    result = rolling_correlation(returns_from({"a": a, "b": b}), "a", "b", window=3)
    values = result.values["a|b"]

    assert values.iloc[:2].isna().all()  # incomplete first windows
    assert values.iloc[2] == pytest.approx(15 / math.sqrt(228))  # same as the hand example
    assert values.iloc[3:6].isna().all()  # windows containing the gap on day 4
    assert values.iloc[6] == pytest.approx(stats.pearsonr(a[4:7], b[4:7]).statistic)
    assert result.observations["a|b"].tolist() == [1, 2, 3, 2, 2, 2, 3, 3]


def test_rolling_spearman_and_relaxed_min_periods():
    a = [0.01, 0.02, 0.03, None, 0.01, 0.02]
    b = [0.03, 0.01, 0.02, 0.01, 0.05, 0.06]
    result = rolling_correlation(
        returns_from({"a": a, "b": b}), "a", "b", window=4, min_periods=3, method="spearman"
    )
    # Window ending day 5 has common days 2, 3, 5.
    expected = stats.spearmanr([0.02, 0.03, 0.01], [0.01, 0.02, 0.05]).statistic
    assert result.values["a|b"].iloc[4] == pytest.approx(expected)
    assert result.metadata.method is CorrelationMethod.SPEARMAN


def test_rolling_correlation_constant_window_and_no_look_ahead():
    a = [0.01, 0.01, 0.01, 0.02, 0.03, 0.05]
    b = [0.02, 0.03, 0.01, 0.02, 0.01, 0.09]
    base = rolling_correlation(returns_from({"a": a, "b": b}), "a", "b", window=3).values["a|b"]
    assert math.isnan(base.iloc[2])  # a constant in the first window
    changed = rolling_correlation(
        returns_from({"a": a, "b": b[:-1] + [-0.5]}), "a", "b", window=3
    ).values["a|b"]
    pd.testing.assert_series_equal(base.iloc[:-1], changed.iloc[:-1])


def test_rolling_correlation_argument_validation():
    data = returns_from({"a": [0.1, 0.2, 0.3], "b": [0.1, 0.3, 0.2]})
    with pytest.raises(UnknownAssetError):
        rolling_correlation(data, "a", "zzz", window=2)
    with pytest.raises(ValueError):
        rolling_correlation(data, "a", "a", window=2)
    with pytest.raises(ValueError):
        rolling_correlation(data, "a", "b", window=3, min_periods=1)
    short = rolling_correlation(data, "a", "b", window=10)
    assert short.values["a|b"].isna().all()
    assert short.observations["a|b"].tolist() == [1, 2, 3]


def test_correlation_from_real_prices_flow():
    prices = {"a": [100.0, 102.0, 101.0, 105.0, 107.0], "b": [50.0, 51.5, 50.2, 52.0, 54.0]}
    result = correlation_matrix(compute_returns(panel(prices), "log"), min_overlap=4)
    expected = stats.pearsonr(np.diff(np.log(prices["a"])), np.diff(np.log(prices["b"])))
    assert result.counts.loc["a", "b"] == 4
    assert result.matrix.loc["a", "b"] == pytest.approx(expected.statistic, rel=1e-12)
