"""Dataset integrity validation.

Validation never repairs data silently. Every removed or modified value is
recorded as an issue, and removed rows are kept in a separate `rejected` frame
with the reason. Missing observations are reported, never filled.

Severities:
- FATAL: the dataset must not be used for research (e.g. an asset has no data,
  too many missing observations, schema mismatch).
- ERROR: invalid rows were rejected; the dataset can still be research-ready if
  no fatal threshold is crossed.
- WARNING: noteworthy but harmless conditions (e.g. out-of-order input, null
  volume, rows outside the requested period).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

import pandas as pd

from cryptovision.data.config import ValidationRules
from cryptovision.data.schemas import (
    PRICE_COLUMNS,
    SECONDARY_COLUMNS,
    SORT_KEYS,
    DatasetKind,
    column_names,
)

MAX_EXAMPLES = 5


class Severity(StrEnum):
    FATAL = "fatal"
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str
    count: int = 1
    asset_id: str | None = None
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssetCoverage:
    asset_id: str
    rows: int
    first: str | None
    last: str | None
    expected_observations: int
    missing_observations: int
    longest_gap: int
    missing_examples: tuple[str, ...]


@dataclass
class ValidationReport:
    input_rows: int = 0
    valid_rows: int = 0
    rejected_rows: int = 0
    issues: list[Issue] = field(default_factory=list)
    coverage: list[AssetCoverage] = field(default_factory=list)
    rules: dict[str, Any] = field(default_factory=dict)

    @property
    def research_ready(self) -> bool:
        return not any(issue.severity is Severity.FATAL for issue in self.issues)

    def count(self, severity: Severity) -> int:
        return sum(1 for issue in self.issues if issue.severity is severity)

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_ready": self.research_ready,
            "input_rows": self.input_rows,
            "valid_rows": self.valid_rows,
            "rejected_rows": self.rejected_rows,
            "fatal_count": self.count(Severity.FATAL),
            "error_count": self.count(Severity.ERROR),
            "warning_count": self.count(Severity.WARNING),
            "rules": self.rules,
            "issues": [
                {**asdict(issue), "severity": issue.severity.value} for issue in self.issues
            ],
            "coverage": [asdict(item) for item in self.coverage],
        }


@dataclass(frozen=True)
class ValidationResult:
    valid: pd.DataFrame
    rejected: pd.DataFrame
    report: ValidationReport


def _examples(values: pd.Series) -> tuple[str, ...]:
    return tuple(str(value) for value in values.head(MAX_EXAMPLES))


def _day_label(timestamps: pd.Series) -> pd.Series:
    return timestamps.dt.strftime("%Y-%m-%d")


class _Rejector:
    """Moves rows from the working frame to the rejected frame with a reason."""

    def __init__(self, frame: pd.DataFrame, report: ValidationReport) -> None:
        self.frame = frame
        self.report = report
        self.rejected: list[pd.DataFrame] = []

    def reject(
        self, mask: pd.Series, severity: Severity, code: str, message: str, per_asset: bool = True
    ) -> None:
        if not mask.any():
            return
        removed = self.frame[mask].assign(rejection_reason=code)
        self.rejected.append(removed)
        self.frame = self.frame[~mask]
        groups = removed.groupby("asset_id", sort=True) if per_asset else [(None, removed)]
        for asset_id, rows in groups:
            self.report.add(
                Issue(
                    severity=severity,
                    code=code,
                    message=message,
                    count=len(rows),
                    asset_id=asset_id,
                    examples=_examples(_day_label(rows["timestamp_utc"].dropna())),
                )
            )


def validate_dataset(
    frame: pd.DataFrame,
    *,
    kind: DatasetKind,
    asset_ids: list[str],
    start: date,
    end: date,
    rules: ValidationRules,
) -> ValidationResult:
    """Validate a normalized daily dataset for the inclusive period [start, end]."""
    report = ValidationReport(input_rows=len(frame), rules=rules.model_dump())
    expected_columns = column_names(kind)

    missing_columns = [name for name in expected_columns if name not in frame.columns]
    if missing_columns:
        report.add(
            Issue(
                Severity.FATAL,
                "schema_missing_columns",
                "Required columns are missing; the source format may have changed.",
                count=len(missing_columns),
                examples=tuple(missing_columns),
            )
        )
        empty = frame.iloc[0:0]
        report.rejected_rows = len(frame)
        return ValidationResult(empty, frame.assign(rejection_reason="schema"), report)

    extra_columns = [name for name in frame.columns if name not in expected_columns]
    if extra_columns:
        report.add(
            Issue(
                Severity.WARNING,
                "schema_extra_columns",
                "Unexpected columns were dropped.",
                count=len(extra_columns),
                examples=tuple(extra_columns),
            )
        )
    work = frame.loc[:, expected_columns].reset_index(drop=True)
    rejector = _Rejector(work, report)

    _check_order(rejector.frame, report)
    _reject_unknown_assets(rejector, asset_ids)
    _reject_bad_timestamps(rejector, start, end)
    _reject_duplicates(rejector)
    _reject_invalid_prices(rejector, kind)
    _null_invalid_secondary_values(rejector, kind)
    _check_coverage(rejector.frame, report, asset_ids, start, end, rules)

    valid = rejector.frame.sort_values(list(SORT_KEYS), kind="stable").reset_index(drop=True)
    rejected = (
        pd.concat(rejector.rejected, ignore_index=True)
        if rejector.rejected
        else work.iloc[0:0].assign(rejection_reason=pd.Series(dtype="object"))
    )
    report.valid_rows = len(valid)
    report.rejected_rows = len(rejected)
    return ValidationResult(valid, rejected, report)


def _check_order(frame: pd.DataFrame, report: ValidationReport) -> None:
    for asset_id, rows in frame.groupby("asset_id", sort=True):
        timestamps = rows["timestamp_utc"].dropna()
        inversions = int((timestamps.diff() < pd.Timedelta(0)).sum())
        if inversions:
            report.add(
                Issue(
                    Severity.WARNING,
                    "out_of_order",
                    "Observations were not in chronological order; they were sorted.",
                    count=inversions,
                    asset_id=str(asset_id),
                )
            )


def _reject_unknown_assets(rejector: _Rejector, asset_ids: list[str]) -> None:
    mask = ~rejector.frame["asset_id"].isin(asset_ids)
    rejector.reject(mask, Severity.ERROR, "unknown_asset", "Rows for assets not in the config.")


def _reject_bad_timestamps(rejector: _Rejector, start: date, end: date) -> None:
    timestamps = rejector.frame["timestamp_utc"]
    rejector.reject(
        timestamps.isna(), Severity.ERROR, "missing_timestamp", "Rows without a timestamp."
    )
    frame = rejector.frame
    timestamps = frame["timestamp_utc"]
    misaligned = timestamps != timestamps.dt.floor("D")
    # A provider may append a provisional point for the current, unfinished day
    # (CoinGecko does). That expected artifact is a warning; any other
    # misaligned timestamp is an error.
    last_aligned = timestamps.where(~misaligned).groupby(frame["asset_id"]).transform("max")
    trailing = misaligned & (last_aligned.isna() | (timestamps > last_aligned))
    rejector.reject(
        trailing,
        Severity.WARNING,
        "intraday_latest_point",
        "Provisional intraday point after the last complete day was dropped.",
    )
    timestamps = rejector.frame["timestamp_utc"]
    rejector.reject(
        timestamps != timestamps.dt.floor("D"),
        Severity.ERROR,
        "misaligned_timestamp",
        "Timestamps not at 00:00 UTC.",
    )
    days = rejector.frame["timestamp_utc"].dt.date
    outside = (days < start) | (days > end)
    rejector.reject(
        outside, Severity.WARNING, "outside_period", "Rows outside the requested period."
    )


def _reject_duplicates(rejector: _Rejector) -> None:
    frame = rejector.frame
    keys = list(SORT_KEYS)
    duplicated_key = frame.duplicated(keys, keep=False)
    if not duplicated_key.any():
        return
    identical_extra = frame.duplicated(keep="first")
    rejector.reject(
        identical_extra,
        Severity.WARNING,
        "duplicate_identical",
        "Exact duplicate rows; one copy was kept.",
    )
    frame = rejector.frame
    conflicting = frame.duplicated(keys, keep=False)
    rejector.reject(
        conflicting,
        Severity.ERROR,
        "duplicate_conflict",
        "Several different rows share one timestamp; all copies were rejected.",
    )


def _reject_invalid_prices(rejector: _Rejector, kind: DatasetKind) -> None:
    columns = list(PRICE_COLUMNS[kind])
    prices = rejector.frame[columns]
    rejector.reject(
        prices.isna().any(axis=1), Severity.ERROR, "missing_price", "Rows with a null price."
    )
    prices = rejector.frame[columns]
    rejector.reject(
        (prices <= 0).any(axis=1),
        Severity.ERROR,
        "non_positive_price",
        "Rows with a zero or negative price.",
    )
    if kind is DatasetKind.OHLCV:
        frame = rejector.frame
        body_high = frame[["open", "close"]].max(axis=1)
        body_low = frame[["open", "close"]].min(axis=1)
        inconsistent = (frame["high"] < body_high) | (frame["low"] > body_low)
        rejector.reject(
            inconsistent,
            Severity.ERROR,
            "inconsistent_ohlc",
            "High below open/close or low above open/close.",
        )


def _null_invalid_secondary_values(rejector: _Rejector, kind: DatasetKind) -> None:
    frame = rejector.frame.copy()
    report = rejector.report
    for column in SECONDARY_COLUMNS[kind]:
        values = frame[column]
        nulls = values.isna()
        for asset_id, rows in frame[nulls].groupby("asset_id", sort=True):
            report.add(
                Issue(
                    Severity.WARNING,
                    "null_value",
                    f"{column} is null in the source; the value is unknown, not zero.",
                    count=len(rows),
                    asset_id=str(asset_id),
                    examples=_examples(_day_label(rows["timestamp_utc"])),
                )
            )
        negative = values < 0
        if kind is DatasetKind.PRICE_SERIES and column == "market_cap":
            # CoinGecko reports 0 when market cap is unknown; 0 is not a real value.
            negative = values <= 0
        negative = negative.fillna(False).astype(bool)
        for asset_id, rows in frame[negative].groupby("asset_id", sort=True):
            report.add(
                Issue(
                    Severity.WARNING,
                    "invalid_value_nulled",
                    f"Invalid {column} values were replaced by null; the rows were kept.",
                    count=len(rows),
                    asset_id=str(asset_id),
                    examples=_examples(_day_label(rows["timestamp_utc"])),
                )
            )
        frame.loc[negative, column] = None
    rejector.frame = frame


def _longest_run(missing: list[date]) -> int:
    longest = current = 0
    previous: date | None = None
    for day in missing:
        current = current + 1 if previous is not None and day - previous == timedelta(1) else 1
        longest = max(longest, current)
        previous = day
    return longest


def _check_coverage(
    frame: pd.DataFrame,
    report: ValidationReport,
    asset_ids: list[str],
    start: date,
    end: date,
    rules: ValidationRules,
) -> None:
    expected_days = pd.date_range(start, end, freq="D").date
    for asset_id in asset_ids:
        rows = frame[frame["asset_id"] == asset_id]
        present = set(rows["timestamp_utc"].dt.date)
        missing = [day for day in expected_days if day not in present]
        longest = _longest_run(missing)
        report.coverage.append(
            AssetCoverage(
                asset_id=asset_id,
                rows=len(rows),
                first=min(present).isoformat() if present else None,
                last=max(present).isoformat() if present else None,
                expected_observations=len(expected_days),
                missing_observations=len(missing),
                longest_gap=longest,
                missing_examples=tuple(day.isoformat() for day in missing[:MAX_EXAMPLES]),
            )
        )
        if not present:
            report.add(
                Issue(Severity.FATAL, "asset_without_data", "No valid rows.", asset_id=asset_id)
            )
            continue
        if not missing:
            continue
        fraction = len(missing) / len(expected_days)
        fatal = fraction > rules.max_missing_fraction or longest > rules.max_consecutive_missing
        report.add(
            Issue(
                Severity.FATAL if fatal else Severity.WARNING,
                "missing_observations",
                (
                    f"{len(missing)} of {len(expected_days)} expected days missing "
                    f"({fraction:.2%}, longest gap {longest}); gaps are not filled."
                ),
                count=len(missing),
                asset_id=asset_id,
                examples=tuple(day.isoformat() for day in missing[:MAX_EXAMPLES]),
            )
        )
