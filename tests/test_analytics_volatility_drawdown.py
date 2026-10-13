"""Volatility and drawdown against hand-calculated values."""

from __future__ import annotations

import math
import statistics
from datetime import date

import numpy as np
import pandas as pd
import pytest

from cryptovision.analytics.drawdown import drawdown_series, max_drawdown
from cryptovision.analytics.exceptions import InsufficientDataError, InvalidPriceError
from cryptovision.analytics.returns import log_returns, simple_returns
from cryptovision.analytics.volatility import (
    annualize,
    rolling_volatility,
    sample_volatility,
    volatility_table,
)
from tests.analytics_helpers import panel

SQRT_365 = 19.1049731745428  # sqrt(365)


# --- Volatility -----------------------------------------------------------------------


def test_sample_volatility_hand_calculated():
    # mean 0; squared deviations 0.01 + 0.01 + 0 = 0.02; / (3 - 1) = 0.01; sqrt = 0.1
    assert sample_volatility([0.1, -0.1, 0.0]) == pytest.approx(0.1, abs=1e-15)
    assert annualize(0.1) == pytest.approx(0.1 * SQRT_365, rel=1e-12)
    assert annualize(0.1, 252) == pytest.approx(0.1 * math.sqrt(252), rel=1e-12)


def test_sample_volatility_matches_statistics_module():
    values = [0.013, -0.021, 0.004, 0.017, -0.009, 0.0]
    assert sample_volatility(values) == pytest.approx(statistics.stdev(values), rel=1e-12)


def test_constant_returns_have_zero_volatility():
    assert sample_volatility([0.01] * 10) == 0.0
    # Constant growth rate: log returns are all ln(1.01).
    prices = [100 * 1.01**k for k in range(40)]
    table = volatility_table(log_returns(panel({"a": prices})), min_observations=30).table
    assert table.loc["a", "daily_volatility"] == pytest.approx(0.0, abs=1e-15)


def test_volatility_ignores_missing_values():
    assert sample_volatility(pd.Series([0.1, np.nan, -0.1, 0.0])) == pytest.approx(0.1)


def test_insufficient_observations():
    with pytest.raises(InsufficientDataError):
        sample_volatility([0.1])
    with pytest.raises(InsufficientDataError):
        sample_volatility([0.1, 0.2], min_observations=3)
    with pytest.raises(ValueError):
        sample_volatility([0.1, 0.2], min_observations=1)
    with pytest.raises(ValueError):
        annualize(0.1, 0)


def test_volatility_table_flags_insufficient_assets():
    prices = {"a": [100.0, 110.0, 99.0, 99.0], "b": [1.0, None, 2.0, 3.0]}
    result = volatility_table(simple_returns(panel(prices)), min_observations=3)

    assert result.table.loc["a", "daily_volatility"] == pytest.approx(0.1)
    assert result.table.loc["a", "annualized_volatility"] == pytest.approx(0.1 * SQRT_365)
    assert result.table.loc["b", "status"] == "insufficient"
    assert result.table.loc["b", "observations"] == 1
    assert result.metadata.annualization_factor == 365


def test_simple_and_log_volatility_differ():
    prices = {"a": [100.0, 130.0, 80.0, 120.0, 90.0]}
    simple = volatility_table(simple_returns(panel(prices)), min_observations=2).table
    log = volatility_table(log_returns(panel(prices)), min_observations=2).table
    assert simple.loc["a", "daily_volatility"] != pytest.approx(log.loc["a", "daily_volatility"])


def test_rolling_volatility_windows_and_gaps():
    # Returns: d2 0.1, d3 -0.1, d4 0.0, d5 missing price, d6 after gap, d7 ...
    # Prices 64, 80, 100, 125 give simple returns of exactly 0.25 in binary floating point.
    prices = {"a": [100.0, 110.0, 99.0, 99.0, None, 64.0, 80.0, 100.0, 125.0]}
    result = rolling_volatility(simple_returns(panel(prices)), window=3, annualize_result=False)
    values = result.values["a"]

    # The first full window ends on day 4 (returns of days 2-4): std 0.1.
    assert values.isna().tolist()[:3] == [True, True, True]
    assert values.iloc[3] == pytest.approx(0.1)
    # Windows containing the gap (days 5-6 have no return) are undefined.
    assert values.iloc[4:8].isna().all()
    # Days 7-9 returns are all 0.25 -> constant window -> exactly 0.
    assert values.iloc[8] == 0.0
    assert result.observations["a"].tolist() == [0, 1, 2, 3, 2, 1, 1, 2, 3]


def test_rolling_volatility_with_relaxed_min_periods_spans_gaps():
    prices = {"a": [100.0, 110.0, 99.0, None, 99.0, 108.9]}
    result = rolling_volatility(
        simple_returns(panel(prices)), window=4, min_periods=2, annualize_result=False
    )
    # Window ending day 6 holds returns of days 3 (-0.1) and 6 (0.1): std = sqrt(0.02).
    assert result.values["a"].iloc[5] == pytest.approx(math.sqrt(0.02))


def test_rolling_volatility_has_no_look_ahead():
    prices = [100.0, 101.0, 99.0, 102.0, 98.0, 103.0, 97.0, 150.0]
    base = rolling_volatility(log_returns(panel({"a": prices})), window=3).values["a"]
    changed = prices[:-1] + [10.0]
    altered = rolling_volatility(log_returns(panel({"a": changed})), window=3).values["a"]
    pd.testing.assert_series_equal(base.iloc[:-1], altered.iloc[:-1])
    assert base.iloc[-1] != altered.iloc[-1]


def test_rolling_volatility_annualizes_and_validates():
    prices = {"a": [100.0, 110.0, 99.0, 99.0]}
    result = rolling_volatility(simple_returns(panel(prices)), window=3)
    assert result.values["a"].iloc[3] == pytest.approx(0.1 * SQRT_365)
    assert result.metadata.window == 3
    assert result.metadata.calculation == "rolling_volatility_annualized"
    with pytest.raises(ValueError):
        rolling_volatility(simple_returns(panel(prices)), window=3, min_periods=1)
    with pytest.raises(ValueError):
        rolling_volatility(simple_returns(panel(prices)), window=3, min_periods=4)


# --- Drawdown -------------------------------------------------------------------------


def series(values, start=date(2024, 1, 1)) -> pd.Series:
    index = pd.date_range(start, periods=len(values), freq="D", tz="UTC")
    return pd.Series(values, index=index, dtype="float64")


def test_drawdown_with_repeated_peak_and_recovery():
    # Peaks 100,120,120,120,120,130 -> drawdowns 0, 0, -0.25, 0, -0.5, 0
    prices = series([100, 120, 90, 120, 60, 130])
    assert drawdown_series(prices).tolist() == pytest.approx([0, 0, -0.25, 0, -0.5, 0])

    result = max_drawdown(prices)
    assert result.max_drawdown == pytest.approx(-0.5)
    assert result.magnitude == pytest.approx(0.5)
    assert result.peak_date == date(2024, 1, 4)  # latest day at the 120 peak
    assert result.trough_date == date(2024, 1, 5)
    assert (result.peak_price, result.trough_price) == (120.0, 60.0)
    assert result.recovery_date == date(2024, 1, 6)
    assert result.recovered is True
    assert result.duration_days == 1
    assert result.duration_observations == 1
    assert result.recovery_days == 2


def test_unrecovered_drawdown_has_no_recovery_date():
    result = max_drawdown(series([100, 80, 90]))
    assert result.max_drawdown == pytest.approx(-0.2)
    assert (result.peak_date, result.trough_date) == (date(2024, 1, 1), date(2024, 1, 2))
    assert result.recovered is False
    assert result.recovery_date is None and result.recovery_days is None


def test_recovery_at_exactly_the_peak_counts():
    result = max_drawdown(series([100, 50, 100]))
    assert result.recovery_date == date(2024, 1, 3)


def test_equal_troughs_use_the_first():
    result = max_drawdown(series([100, 50, 100, 50]))
    assert result.trough_date == date(2024, 1, 2)
    assert result.recovery_date == date(2024, 1, 3)


def test_increasing_prices_have_no_drawdown():
    result = max_drawdown(series([1, 2, 2, 3]))
    assert result.max_drawdown == 0.0
    assert result.peak_date is None and result.recovered is None
    assert result.observations == 4


def test_constant_prices_have_no_drawdown():
    assert max_drawdown(series([5, 5, 5])).max_drawdown == 0.0


def test_decreasing_prices():
    result = max_drawdown(series([4, 3, 2, 1]))
    assert result.max_drawdown == pytest.approx(-0.75)
    assert (result.peak_date, result.trough_date) == (date(2024, 1, 1), date(2024, 1, 4))
    assert result.duration_days == 3 and result.duration_observations == 3


def test_drawdown_skips_missing_days_but_counts_calendar_duration():
    prices = series([100, np.nan, np.nan, 70, 110])
    result = max_drawdown(prices)
    assert result.max_drawdown == pytest.approx(-0.3)
    assert result.duration_days == 3  # calendar days
    assert result.duration_observations == 1  # observed steps
    assert drawdown_series(prices).isna().tolist() == [False, True, True, False, False]


def test_drawdown_input_validation():
    with pytest.raises(InsufficientDataError):
        max_drawdown(series([100]))
    with pytest.raises(InvalidPriceError):
        max_drawdown(series([100, 0, 50]))
    with pytest.raises(InvalidPriceError):
        max_drawdown(series([100, -5]))
    duplicated = pd.concat([series([1, 2]), series([3], start=date(2024, 1, 2))])
    with pytest.raises(InvalidPriceError, match="duplicate"):
        max_drawdown(duplicated)


def test_max_drawdown_matches_brute_force_on_random_walk():
    rng = np.random.default_rng(11)
    prices = series(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 400))))
    values = prices.to_numpy()
    brute = min(values[j] / values[: j + 1].max() - 1 for j in range(len(values)))
    assert max_drawdown(prices).max_drawdown == pytest.approx(brute, rel=1e-12)
