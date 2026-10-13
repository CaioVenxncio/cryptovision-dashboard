"""Validation rules, using deterministic synthetic data with known defects."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from cryptovision.data.config import ValidationRules
from cryptovision.data.schemas import DatasetKind, column_names
from cryptovision.data.storage import normalize_dtypes
from cryptovision.data.synthetic import generate_synthetic_ohlcv
from cryptovision.data.validate import Severity, validate_dataset

START = date(2024, 1, 1)
DAYS = 30
END = date(2024, 1, 30)
ASSETS = ["synthetic-a", "synthetic-b", "synthetic-c"]


@pytest.fixture
def clean() -> pd.DataFrame:
    return generate_synthetic_ohlcv(start=START, days=DAYS, seed=7)


def run(frame, *, rules=None, assets=ASSETS, kind=DatasetKind.OHLCV, start=START, end=END):
    return validate_dataset(
        frame, kind=kind, asset_ids=assets, start=start, end=end, rules=rules or ValidationRules()
    )


def codes(result, severity=None):
    return {
        (issue.code, issue.asset_id)
        for issue in result.report.issues
        if severity is None or issue.severity is severity
    }


def test_clean_data_is_research_ready(clean):
    result = run(clean)
    assert result.report.research_ready
    assert result.report.issues == []
    assert len(result.valid) == 90 and len(result.rejected) == 0
    assert all(c.missing_observations == 0 for c in result.report.coverage)


def test_documented_anomalies_are_all_detected():
    frame = generate_synthetic_ohlcv(start=START, days=DAYS, seed=7, with_anomalies=True)
    result = run(frame)

    assert not result.report.research_ready
    found = codes(result)
    assert ("out_of_order", "synthetic-a") in found
    assert ("duplicate_identical", "synthetic-b") in found
    assert ("duplicate_conflict", "synthetic-b") in found
    assert ("non_positive_price", "synthetic-c") in found
    assert ("null_value", "synthetic-c") in found
    assert ("missing_observations", "synthetic-a") in found
    assert set(result.rejected["rejection_reason"]) == {
        "duplicate_identical",
        "duplicate_conflict",
        "non_positive_price",
    }
    assert result.report.input_rows == result.report.valid_rows + result.report.rejected_rows


def test_output_is_sorted_and_nothing_is_filled(clean):
    shuffled = clean.sample(frac=1, random_state=1).drop(index=clean.index[5])
    result = run(shuffled)
    assert result.valid.equals(
        result.valid.sort_values(["asset_id", "timestamp_utc"]).reset_index(drop=True)
    )
    assert len(result.valid) == 89  # the missing day is reported, not interpolated


@pytest.mark.parametrize(
    ("missing", "max_fraction", "max_gap", "fatal"),
    [
        (1, 1 / 30, 3, False),  # exactly at the fraction threshold
        (2, 1 / 30, 3, True),  # just above it
        (3, 1.0, 3, False),  # gap exactly at the limit
        (4, 1.0, 3, True),  # gap above the limit
        (1, 0.0, 3, True),  # zero tolerance
    ],
)
def test_missing_observation_thresholds(clean, missing, max_fraction, max_gap, fatal):
    a_rows = clean.index[clean["asset_id"] == "synthetic-a"]
    frame = clean.drop(index=a_rows[10 : 10 + missing])
    rules = ValidationRules(max_missing_fraction=max_fraction, max_consecutive_missing=max_gap)

    result = run(frame, rules=rules)

    issue = next(i for i in result.report.issues if i.code == "missing_observations")
    assert issue.count == missing
    assert (issue.severity is Severity.FATAL) is fatal
    assert result.report.research_ready is not fatal
    coverage = next(c for c in result.report.coverage if c.asset_id == "synthetic-a")
    assert coverage.longest_gap == missing


def test_asset_without_data_is_fatal(clean):
    result = run(clean[clean["asset_id"] != "synthetic-c"])
    assert ("asset_without_data", "synthetic-c") in codes(result, Severity.FATAL)


def test_unknown_asset_rows_are_rejected(clean):
    result = run(clean, assets=["synthetic-a", "synthetic-b"])
    assert ("unknown_asset", "synthetic-c") in codes(result, Severity.ERROR)
    assert len(result.rejected) == 30


def test_rows_outside_period_are_dropped_with_warning(clean):
    result = run(clean, end=date(2024, 1, 20))
    assert ("outside_period", "synthetic-a") in codes(result, Severity.WARNING)
    assert result.valid["timestamp_utc"].max().date() == date(2024, 1, 20)


def test_trailing_intraday_point_is_a_warning_but_inner_misalignment_an_error(clean):
    a = clean[clean["asset_id"] == "synthetic-a"]
    trailing = a.iloc[[-1]].assign(
        timestamp_utc=a["timestamp_utc"].iloc[-1] + pd.Timedelta(hours=20)
    )
    inner = a.iloc[[3]].assign(timestamp_utc=a["timestamp_utc"].iloc[3] + pd.Timedelta(hours=6))
    frame = pd.concat([clean, trailing, inner], ignore_index=True)

    result = run(frame, end=date(2024, 1, 31))

    assert ("intraday_latest_point", "synthetic-a") in codes(result, Severity.WARNING)
    assert ("misaligned_timestamp", "synthetic-a") in codes(result, Severity.ERROR)


def test_missing_timestamps_are_rejected(clean):
    frame = clean.copy()
    frame.loc[0, "timestamp_utc"] = pd.NaT
    result = run(frame)
    assert result.rejected["rejection_reason"].tolist() == ["missing_timestamp"]


def test_inconsistent_ohlc_rejected(clean):
    frame = clean.copy()
    frame.loc[0, "high"] = frame.loc[0, "low"] * 0.5
    result = run(frame)
    assert ("inconsistent_ohlc", "synthetic-a") in codes(result, Severity.ERROR)


@pytest.mark.parametrize("price", [0.0, -1.0, np.nan])
def test_invalid_prices_rejected(clean, price):
    frame = clean.copy()
    frame.loc[0, "open"] = price
    result = run(frame)
    expected = "missing_price" if np.isnan(price) else "non_positive_price"
    assert result.rejected["rejection_reason"].tolist() == [expected]


def test_negative_volume_is_nulled_not_dropped(clean):
    frame = clean.copy()
    frame.loc[0, "volume_base"] = -5.0
    frame.loc[1, "trade_count"] = -1
    result = run(frame)

    assert len(result.rejected) == 0
    assert pd.isna(result.valid.loc[0, "volume_base"])
    assert ("invalid_value_nulled", "synthetic-a") in codes(result, Severity.WARNING)


def test_schema_missing_columns_is_fatal(clean):
    result = run(clean.drop(columns=["close"]))
    assert ("schema_missing_columns", None) in codes(result, Severity.FATAL)
    assert len(result.valid) == 0


def test_extra_columns_are_dropped_with_warning(clean):
    result = run(clean.assign(unexpected=1))
    assert ("schema_extra_columns", None) in codes(result, Severity.WARNING)
    assert "unexpected" not in result.valid.columns


def price_series(values: dict[str, list]) -> pd.DataFrame:
    days = len(values["price"])
    frame = pd.DataFrame(
        {
            "timestamp_utc": pd.date_range("2024-01-01", periods=days, tz="UTC"),
            "asset_id": "bitcoin",
            "symbol": "BTC",
            "provider": "coingecko",
            "quote_currency": "USD",
            "frequency": "1d",
            **values,
        }
    )
    return normalize_dtypes(frame[column_names(DatasetKind.PRICE_SERIES)], DatasetKind.PRICE_SERIES)


def test_price_series_zero_market_cap_means_unknown():
    frame = price_series(
        {"price": [1.0, 2.0, 3.0], "market_cap": [0.0, 5.0, None], "volume_24h": [1.0, 0.0, 2.0]}
    )
    result = validate_dataset(
        frame,
        kind=DatasetKind.PRICE_SERIES,
        asset_ids=["bitcoin"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 3),
        rules=ValidationRules(),
    )
    assert result.report.research_ready
    assert pd.isna(result.valid.loc[0, "market_cap"])
    assert result.valid.loc[1, "volume_24h"] == 0.0  # zero volume can be genuine
    issue_codes = [(i.code, i.count) for i in result.report.issues]
    assert ("invalid_value_nulled", 1) in issue_codes
    assert ("null_value", 1) in issue_codes


def test_report_serializes(clean):
    rules = ValidationRules(max_missing_fraction=0.1)
    report = run(clean.drop(index=[0]), rules=rules).report.to_dict()
    assert report["research_ready"] is True
    assert report["warning_count"] == 1
    assert report["issues"][0]["severity"] == "warning"
    assert list(report["coverage"][0]["missing_examples"]) == ["2024-01-01"]
