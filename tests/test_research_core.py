"""Regimes, estimands and the stationary bootstrap, checked against hand calculations."""

from __future__ import annotations

import math
import statistics
from datetime import date

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from cryptovision.research.bootstrap import bootstrap_regime_deltas, stationary_indices
from cryptovision.research.config import AnalysisSpec
from cryptovision.research.estimands import (
    correlation_matrix,
    mean_pairwise,
    pair_count,
    regime_delta,
    regime_estimate,
)
from cryptovision.research.exceptions import InsufficientSampleError
from cryptovision.research.experiment import prepare_sample
from cryptovision.research.regimes import (
    HIGH,
    LOW,
    classify_regimes,
    contemporaneous_volatility,
    lagged_volatility,
    volatility_proxy,
)


def spec(**overrides) -> AnalysisSpec:
    """A valid spec, then small test-only values via model_copy (which skips validation).

    The validators guard real configurations; tiny windows keep hand calculations short.
    """
    base = AnalysisSpec(estimand="raw", evaluation_start=date(2024, 1, 1))
    small = {"lookback_days": 3, "min_days_per_regime": 2, "mean_block_length": 2}
    return base.model_copy(update={**small, **overrides})


def frame(values: dict[str, list[float]]) -> pd.DataFrame:
    n = len(next(iter(values.values())))
    index = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(values, index=index)


# --- Regimes ------------------------------------------------------------------------


def test_lagged_volatility_uses_only_previous_days():
    returns = frame({"a": [0.01, -0.02, 0.03, 0.05, -0.01, 0.02]})
    lagged = lagged_volatility(returns, 3)["a"]
    assert lagged.iloc[:3].isna().all()
    assert lagged.iloc[3] == pytest.approx(statistics.stdev([0.01, -0.02, 0.03]))
    assert lagged.iloc[5] == pytest.approx(statistics.stdev([0.03, 0.05, -0.01]))
    contemporaneous = contemporaneous_volatility(returns, 3)["a"]
    assert contemporaneous.iloc[3] == pytest.approx(statistics.stdev([-0.02, 0.03, 0.05]))


def test_day_t_return_never_affects_its_own_label():
    base = frame({"a": [0.01, -0.02, 0.03, 0.05, -0.01, 0.02, 0.0], "b": [0.0] * 7})
    shocked = base.copy()
    shocked.loc[shocked.index[4], "a"] = 0.9  # huge return on day 5
    p0 = volatility_proxy(base, spec())
    p1 = volatility_proxy(shocked, spec())
    assert p0.iloc[:5].equals(p1.iloc[:5])  # proxy up to and including day 5 unchanged
    assert p1.iloc[5] != p0.iloc[5]  # the shock enters from the next day on
    # The contemporaneous variant does see the same-day return.
    c0 = volatility_proxy(base, spec(contemporaneous=True))
    c1 = volatility_proxy(shocked, spec(contemporaneous=True))
    assert c1.iloc[4] != c0.iloc[4]


def test_mean_proxy_and_single_asset_proxy():
    returns = frame({"a": [0.01, -0.02, 0.03, 0.05], "b": [0.02, 0.0, -0.01, 0.04]})
    mean_proxy = volatility_proxy(returns, spec())
    expected = (statistics.stdev([0.01, -0.02, 0.03]) + statistics.stdev([0.02, 0.0, -0.01])) / 2
    assert mean_proxy.iloc[3] == pytest.approx(expected)
    btc = volatility_proxy(returns, spec(proxy="asset_volatility", proxy_asset="b"))
    assert btc.iloc[3] == pytest.approx(statistics.stdev([0.02, 0.0, -0.01]))


def test_median_split_is_balanced_and_strict():
    proxy = pd.Series([np.nan, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    evaluation = pd.Series([True] * 7)
    result = classify_regimes(proxy, spec(), evaluation)
    assert result.labels.tolist()[1:] == [LOW, LOW, LOW, HIGH, HIGH, HIGH]
    assert pd.isna(result.labels.iloc[0])
    assert result.threshold.iloc[1] == 3.5


def test_trailing_threshold_uses_only_past_proxy_values():
    proxy = pd.Series([1.0, 2.0, 3.0, 10.0, 0.5, 2.5])
    evaluation = pd.Series([True] * 6)
    result = classify_regimes(
        proxy, spec(threshold="trailing_quantile", trailing_days=3), evaluation
    )
    # Day 4 threshold = median(1, 2, 3) = 2 -> 10 is high; day 5: median(2, 3, 10) = 3 -> low.
    assert result.threshold.tolist()[3:] == [2.0, 3.0, 3.0]
    assert result.labels.tolist()[3:] == [HIGH, LOW, LOW]
    assert result.labels.iloc[:3].isna().all()


def test_evaluation_mask_limits_classification():
    proxy = pd.Series([1.0, 2.0, 3.0, 4.0])
    evaluation = pd.Series([False, False, True, True])
    result = classify_regimes(proxy, spec(), evaluation)
    assert result.labels.iloc[:2].isna().all()
    assert result.labels.tolist()[2:] == [LOW, HIGH]  # median of (3, 4) = 3.5


# --- Estimands ----------------------------------------------------------------------


def test_correlation_matrix_matches_references():
    rng = np.random.default_rng(0)
    values = rng.normal(size=(200, 4))
    np.testing.assert_allclose(correlation_matrix(values), np.corrcoef(values.T), atol=1e-12)
    np.testing.assert_allclose(
        correlation_matrix(values, "spearman"), stats.spearmanr(values).statistic, atol=1e-12
    )


def test_mean_pairwise_counts_each_pair_once():
    corr = np.array([[1.0, 0.2, 0.4], [0.2, 1.0, 0.6], [0.4, 0.6, 1.0]])
    assert mean_pairwise(corr) == pytest.approx(0.4)  # (0.2 + 0.4 + 0.6) / 3
    assert pair_count(9) == 36
    corr[0, 1] = corr[1, 0] = np.nan
    assert math.isnan(mean_pairwise(corr))


def test_constant_column_makes_correlation_undefined():
    values = np.column_stack([np.ones(10), np.arange(10.0)])
    assert np.isnan(correlation_matrix(values)[0, 1])


def test_regime_estimate_hand_calculated():
    # High days: x=(1,2,3), y=(2,4,7): r = 15/sqrt(228). Low days: perfectly opposite: r = -1.
    values = np.array([[1, 2], [2, 4], [3, 7], [1, 3], [2, 2], [3, 1]], dtype=float)
    high = np.array([True, True, True, False, False, False])
    estimate = regime_estimate(values, high)
    assert estimate.rho_high == pytest.approx(15 / math.sqrt(228))
    assert estimate.rho_low == pytest.approx(-1.0)
    assert estimate.delta == pytest.approx(15 / math.sqrt(228) + 1)
    assert (estimate.n_high, estimate.n_low, estimate.n_pairs) == (3, 3, 1)
    assert regime_delta(values, high) == pytest.approx(estimate.delta)


def test_correlation_matrix_input_validation():
    with pytest.raises(ValueError):
        correlation_matrix(np.ones(5))


# --- Stationary bootstrap -----------------------------------------------------------


def test_stationary_indices_are_valid_blocks():
    rng = np.random.default_rng(3)
    index = stationary_indices(50, 5, rng)
    assert index.shape == (50,) and index.min() >= 0 and index.max() < 50
    steps = np.diff(index)
    continuing = (steps == 1) | (steps == -49)  # +1 or circular wrap
    assert continuing.mean() > 0.6  # mostly within blocks


def test_stationary_mean_block_length():
    rng = np.random.default_rng(4)
    breaks = []
    for _ in range(200):
        index = stationary_indices(400, 10, rng)
        steps = np.diff(index)
        breaks.append(np.mean(~((steps == 1) | (steps == -399))))
    # New blocks start with probability 1/10 (a random restart can rarely continue a block).
    assert np.mean(breaks) == pytest.approx(0.1, abs=0.01)


def test_stationary_indices_validation_and_iid_limit():
    rng = np.random.default_rng(5)
    with pytest.raises(ValueError):
        stationary_indices(0, 5, rng)
    with pytest.raises(ValueError):
        stationary_indices(10, 0, rng)
    assert stationary_indices(10, 1, rng).shape == (10,)


def test_bootstrap_resamples_days_jointly():
    rng = np.random.default_rng(6)
    x = rng.normal(size=300)
    values = np.column_stack([x, 2 * x + 1, -x])  # perfectly dependent columns
    high = np.arange(300) % 2 == 0
    (result,) = bootstrap_regime_deltas(
        [values],
        high,
        methods=["pearson"],
        replications=50,
        mean_block_length=5,
        confidence_level=0.95,
        min_days_per_regime=50,
        rng=rng,
    )
    # Joint resampling keeps every replicate's correlation structure exactly: Delta = 0.
    np.testing.assert_allclose(result.replicates, 0.0, atol=1e-12)


def test_bootstrap_is_reproducible_with_seed():
    rng_values = np.random.default_rng(7).normal(size=(400, 3))
    high = np.arange(400) < 200

    def run(seed):
        return bootstrap_regime_deltas(
            [rng_values],
            high,
            methods=["pearson"],
            replications=100,
            mean_block_length=10,
            confidence_level=0.9,
            min_days_per_regime=50,
            rng=np.random.default_rng(seed),
        )[0]

    a, b, c = run(1), run(1), run(2)
    np.testing.assert_array_equal(a.replicates, b.replicates)
    assert (a.ci_low, a.ci_high) == (b.ci_low, b.ci_high)
    assert not np.array_equal(a.replicates, c.replicates)
    low, high_bound = np.quantile(a.replicates, [0.05, 0.95])
    # (1 - 0.9) / 2 differs from 0.05 in the last bit, hence approx.
    assert (a.ci_low, a.ci_high) == pytest.approx((low, high_bound), rel=1e-12)
    assert a.standard_error == pytest.approx(np.std(a.replicates, ddof=1))
    assert a.interval(0.5)[0] > a.ci_low


def test_bootstrap_rejects_replicates_with_small_regimes():
    values = np.random.default_rng(8).normal(size=(100, 2))
    high = np.arange(100) < 50
    (result,) = bootstrap_regime_deltas(
        [values],
        high,
        methods=["pearson"],
        replications=40,
        mean_block_length=5,
        confidence_level=0.95,
        min_days_per_regime=60,
        rng=np.random.default_rng(1),
    )
    assert result.rejected == 40
    assert math.isnan(result.ci_low)
    with pytest.raises(ValueError):
        bootstrap_regime_deltas(
            [values],
            high,
            methods=[],
            replications=10,
            mean_block_length=5,
            confidence_level=0.95,
            min_days_per_regime=1,
            rng=np.random.default_rng(1),
        )


def test_bootstrap_detects_known_difference():
    rng = np.random.default_rng(9)
    n = 600
    low = rng.multivariate_normal([0, 0], [[1, 0.1], [0.1, 1]], size=n)
    high = rng.multivariate_normal([0, 0], [[1, 0.8], [0.8, 1]], size=n)
    values = np.vstack([low, high])
    mask = np.arange(2 * n) >= n
    (result,) = bootstrap_regime_deltas(
        [values],
        mask,
        methods=["pearson"],
        replications=300,
        mean_block_length=10,
        confidence_level=0.95,
        min_days_per_regime=200,
        rng=rng,
    )
    assert result.estimate == pytest.approx(0.7, abs=0.08)
    assert result.excludes_zero


# --- Sample preparation -------------------------------------------------------------


def test_prepare_sample_listwise_and_devolatilization():
    rng = np.random.default_rng(10)
    returns = frame({"a": rng.normal(0, 0.02, 40).tolist(), "b": rng.normal(0, 0.03, 40).tolist()})
    returns.iloc[20, 1] = np.nan
    sample = prepare_sample(returns, spec())

    assert sample.assets == ("a", "b")
    assert returns.index[20] not in sample.dates  # incomplete day dropped
    # Days 21-23 lack a full lagged window for b and are unlabelled, so not "incomplete".
    assert sample.excluded_incomplete == 1
    day = sample.dates[5]
    position = returns.index.get_loc(day)
    expected = returns["a"].iloc[position] / statistics.stdev(
        returns["a"].iloc[position - 3 : position]
    )
    assert sample.devolatilized[5, 0] == pytest.approx(expected)
    assert sample.values("raw") is sample.raw


def test_prepare_sample_exclusions_and_minimums():
    rng = np.random.default_rng(11)
    returns = frame({k: rng.normal(size=30).tolist() for k in ("a", "b", "c")})
    assert prepare_sample(returns, spec(exclude_assets=("c",))).assets == ("a", "b")
    with pytest.raises(InsufficientSampleError):
        prepare_sample(returns, spec(min_days_per_regime=30))
    late = prepare_sample(returns, spec(evaluation_start=date(2024, 1, 20)))
    assert late.dates[0].date() == date(2024, 1, 20)
