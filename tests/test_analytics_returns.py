"""Alignment and returns, checked against hand-calculated values."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from cryptovision.analytics.alignment import build_price_panel
from cryptovision.analytics.exceptions import (
    DuplicateObservationError,
    IncompatibleDataError,
    InsufficientDataError,
    InvalidPriceError,
    UnknownAssetError,
)
from cryptovision.analytics.returns import (
    ReturnStatus,
    compute_returns,
    log_returns,
    simple_returns,
)
from tests.analytics_helpers import long_frame, panel


def test_simple_returns_hand_calculated():
    result = simple_returns(panel({"a": [100.0, 110.0, 99.0, 99.0]}))
    values = result.returns["a"].tolist()
    assert math.isnan(values[0])
    assert values[1:] == pytest.approx([0.10, -0.10, 0.0], abs=1e-15)


def test_log_returns_hand_calculated():
    result = log_returns(panel({"a": [100.0, 110.0, 99.0, 99.0]}))
    assert result.returns["a"].iloc[1:].tolist() == pytest.approx(
        [0.09531017980432486, -0.10536051565782628, 0.0], abs=1e-15
    )


def test_log_returns_are_additive_over_contiguous_days():
    prices = [100.0, 104.0, 97.5, 101.2, 120.0, 88.8]
    result = log_returns(panel({"a": prices}))
    assert result.returns["a"].sum() == pytest.approx(math.log(prices[-1] / prices[0]), abs=1e-14)


def test_zero_return_is_a_value_not_missing():
    result = simple_returns(panel({"a": [5.0, 5.0, 5.0]}))
    assert result.counts() == {"a": 2}
    assert result.returns["a"].iloc[1:].tolist() == [0.0, 0.0]


def test_gaps_are_not_bridged_and_statuses_explain_why():
    result = simple_returns(panel({"a": [100.0, None, 121.0, 133.1]}))

    returns = result.returns["a"]
    assert returns.isna().tolist() == [True, True, True, False]
    assert returns.iloc[3] == pytest.approx(0.1)
    assert result.status["a"].tolist() == [
        ReturnStatus.FIRST_OBSERVATION,
        ReturnStatus.MISSING_PRICE,
        ReturnStatus.AFTER_GAP,
        ReturnStatus.VALID,
    ]
    assert len(result.panel.prices) == 4  # every calendar day is present


def test_first_return_of_a_late_starting_asset():
    result = simple_returns(panel({"a": [1.0, 2.0, 4.0], "b": [None, 10.0, 11.0]}))
    assert result.status["b"].tolist() == [
        ReturnStatus.MISSING_PRICE,
        ReturnStatus.FIRST_OBSERVATION,
        ReturnStatus.VALID,
    ]


def test_returns_never_cross_assets():
    # Column-wise shift: b's first return must not use a's last price.
    result = simple_returns(panel({"a": [1.0, 2.0], "b": [10.0, 30.0]}))
    assert math.isnan(result.returns["b"].iloc[0])
    assert result.returns["b"].iloc[1] == pytest.approx(2.0)


def test_unsorted_input_is_ordered_by_timestamp():
    frame = long_frame({"a": [100.0, 110.0, 121.0]}).iloc[::-1]
    result = simple_returns(build_price_panel(frame, price_column="close"))
    assert result.returns["a"].iloc[1:].tolist() == pytest.approx([0.1, 0.1])


def test_single_observation_has_no_returns():
    result = log_returns(panel({"a": [42.0]}))
    assert result.counts() == {"a": 0}
    assert result.status["a"].tolist() == [ReturnStatus.FIRST_OBSERVATION]


@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf])
def test_invalid_prices_are_rejected(bad):
    frame = long_frame({"a": [100.0, 101.0, 102.0]})
    frame.loc[1, "close"] = bad
    with pytest.raises(InvalidPriceError, match="a 2024-01-02"):
        build_price_panel(frame, price_column="close")


def test_duplicate_timestamps_are_rejected():
    frame = long_frame({"a": [100.0, 101.0]})
    frame = pd.concat([frame, frame.iloc[[1]]], ignore_index=True)
    with pytest.raises(DuplicateObservationError, match="a 2024-01-02"):
        build_price_panel(frame, price_column="close")


@pytest.mark.parametrize("column", ["quote_currency", "provider", "frequency"])
def test_mixed_sources_are_rejected(column):
    frame = long_frame({"a": [1.0, 2.0], "b": [1.0, 2.0]})
    frame.loc[frame["asset_id"] == "b", column] = "OTHER"
    with pytest.raises(IncompatibleDataError, match=column):
        build_price_panel(frame, price_column="close")


def test_different_quote_currencies_in_one_panel_are_rejected():
    usdt = long_frame({"a": [1.0, 2.0]}, quote="USDT")
    usd = long_frame({"b": [1.0, 2.0]}, quote="USD")
    with pytest.raises(IncompatibleDataError, match="quote_currency"):
        build_price_panel(pd.concat([usdt, usd]), price_column="close")


def test_non_daily_frequency_is_rejected():
    frame = long_frame({"a": [1.0, 2.0]}).assign(frequency="1h")
    with pytest.raises(IncompatibleDataError, match="daily"):
        build_price_panel(frame, price_column="close")


def test_mixed_daily_boundaries_are_rejected():
    frame = long_frame({"a": [1.0, 2.0]})
    frame.loc[1, "timestamp_utc"] += pd.Timedelta(hours=8)
    with pytest.raises(IncompatibleDataError, match="00:00 UTC"):
        build_price_panel(frame, price_column="close")


def test_naive_timestamps_are_rejected():
    frame = long_frame({"a": [1.0, 2.0]})
    frame["timestamp_utc"] = frame["timestamp_utc"].dt.tz_localize(None)
    with pytest.raises(IncompatibleDataError, match="UTC"):
        build_price_panel(frame, price_column="close")


def test_missing_columns_and_empty_input():
    with pytest.raises(IncompatibleDataError, match="close"):
        build_price_panel(long_frame({"a": [1.0]}).drop(columns="close"), price_column="close")
    with pytest.raises(InsufficientDataError):
        build_price_panel(long_frame({"a": [1.0]}).iloc[0:0], price_column="close")


def test_asset_and_period_selection():
    full = panel({"a": [1.0, 2.0, 3.0, 4.0], "b": [5.0, 6.0, 7.0, 8.0]})
    subset = full.select(assets=["b"], start=date(2024, 1, 2), end=date(2024, 1, 3))
    assert subset.assets == ("b",)
    assert subset.prices["b"].tolist() == [6.0, 7.0]
    assert (subset.start, subset.end) == (date(2024, 1, 2), date(2024, 1, 3))
    with pytest.raises(UnknownAssetError):
        full.select(assets=["zzz"])
    with pytest.raises(UnknownAssetError):
        full.select(assets=["a", "a"])
    with pytest.raises(InsufficientDataError):
        full.select(start=date(2025, 1, 1))


def test_period_arguments_extend_the_calendar_without_filling():
    frame = long_frame({"a": [1.0, 2.0]})
    result = build_price_panel(
        frame, price_column="close", start=date(2023, 12, 30), end=date(2024, 1, 3)
    )
    assert result.prices["a"].isna().tolist() == [True, True, False, False, True]
    with pytest.raises(InsufficientDataError):
        build_price_panel(frame, price_column="close", start=date(2024, 2, 1), end=date(2024, 1, 1))


def test_unknown_assets_in_build_are_rejected():
    with pytest.raises(UnknownAssetError):
        build_price_panel(long_frame({"a": [1.0]}), price_column="close", assets=["b"])


def test_return_type_accepts_strings_and_metadata_records_context():
    result = compute_returns(panel({"a": [1.0, 2.0, 4.0]}), "simple")
    metadata = result.metadata().to_dict()
    assert metadata["return_type"] == "simple"
    assert metadata["context"]["quote_currency"] == "USDT"
    assert metadata["sample_counts"] == {"a": 2}
    assert metadata["start"] == "2024-01-01"
    assert "no interpolation" in metadata["missing_data_policy"]
    with pytest.raises(UnknownAssetError):
        result.series("zzz")


def test_log_and_simple_returns_are_consistent():
    prices = np.array([10.0, 12.5, 11.0, 14.0])
    log = log_returns(panel({"a": prices.tolist()})).returns["a"].iloc[1:]
    simple = simple_returns(panel({"a": prices.tolist()})).returns["a"].iloc[1:]
    np.testing.assert_allclose(np.exp(log) - 1, simple, rtol=1e-14)
