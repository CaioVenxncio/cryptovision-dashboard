"""Historical and rolling volatility.

    sigma_daily      = sqrt( sum_i (x_i - mean(x))^2 / (n - 1) )      (sample std, ddof = 1)
    sigma_annualized = sigma_daily * sqrt(N),   N = 365 by default

Crypto markets trade every calendar day, so one year has 365 daily returns.
The equity convention of 252 counts trading days and would understate annual
volatility here. Annualization assumes independent, identically distributed
returns; it rescales past variation and is not a forecast.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from cryptovision.analytics.exceptions import InsufficientDataError
from cryptovision.analytics.models import DEFAULT_ANNUALIZATION_FACTOR, ResultMetadata
from cryptovision.analytics.returns import ReturnsResult

# ddof = 1 needs at least two values. Summary tables use a larger default.
MATHEMATICAL_MINIMUM = 2
DEFAULT_MIN_OBSERVATIONS = 30
DEFAULT_ROLLING_WINDOWS = (7, 30, 90)


def _check_factor(annualization_factor: int) -> None:
    if annualization_factor <= 0:
        raise ValueError("annualization_factor must be positive")


def sample_volatility(values: pd.Series | np.ndarray, *, min_observations: int = 2) -> float:
    """Sample standard deviation (ddof=1) of the finite values.

    Raises `InsufficientDataError` with fewer than `min_observations` values.
    A constant series has volatility 0.
    """
    if min_observations < MATHEMATICAL_MINIMUM:
        raise ValueError("min_observations must be at least 2")
    array = np.asarray(values, dtype="float64")
    array = array[np.isfinite(array)]
    if array.size < min_observations:
        raise InsufficientDataError(
            f"{array.size} observations; at least {min_observations} are required."
        )
    if np.all(array == array[0]):
        return 0.0
    return float(np.std(array, ddof=1))


def annualize(
    daily_volatility: float, annualization_factor: int = DEFAULT_ANNUALIZATION_FACTOR
) -> float:
    _check_factor(annualization_factor)
    return daily_volatility * math.sqrt(annualization_factor)


@dataclass(frozen=True)
class VolatilityTable:
    """Per-asset volatility. Assets with too few returns have NaN and status `insufficient`."""

    table: pd.DataFrame
    metadata: ResultMetadata


def volatility_table(
    returns: ReturnsResult,
    *,
    annualization_factor: int = DEFAULT_ANNUALIZATION_FACTOR,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> VolatilityTable:
    _check_factor(annualization_factor)
    rows = []
    for asset in returns.returns.columns:
        series = returns.series(asset)
        try:
            daily = sample_volatility(series, min_observations=min_observations)
            status = "ok"
        except InsufficientDataError:
            daily, status = math.nan, "insufficient"
        rows.append(
            {
                "asset_id": asset,
                "observations": len(series),
                "daily_volatility": daily,
                "annualized_volatility": daily * math.sqrt(annualization_factor),
                "status": status,
            }
        )
    metadata = ResultMetadata(
        context=returns.panel.context,
        assets=returns.panel.assets,
        start=returns.panel.start,
        end=returns.panel.end,
        calculation="volatility",
        return_type=returns.return_type,
        min_observations=min_observations,
        annualization_factor=annualization_factor,
        sample_counts=returns.counts(),
    )
    return VolatilityTable(table=pd.DataFrame(rows).set_index("asset_id"), metadata=metadata)


@dataclass(frozen=True)
class RollingResult:
    """A rolling statistic per asset (or pair), labelled by the window's last day."""

    values: pd.DataFrame
    observations: pd.DataFrame
    metadata: ResultMetadata


def rolling_volatility(
    returns: ReturnsResult,
    *,
    window: int,
    min_periods: int | None = None,
    annualization_factor: int = DEFAULT_ANNUALIZATION_FACTOR,
    annualize_result: bool = True,
) -> RollingResult:
    """Rolling sample volatility over `window` calendar days ending on (and including) each day.

    The returns index is calendar-complete, so a window of `window` rows is
    exactly `window` calendar days. Missing returns inside a window reduce its
    observation count. With the default `min_periods = window`, any gap in
    the window makes the value undefined, so windows never span missing data.
    The first `window - 1` days are undefined. No future values are used.
    """
    min_periods = window if min_periods is None else min_periods
    if not MATHEMATICAL_MINIMUM <= min_periods <= window:
        raise ValueError("min_periods must be between 2 and window")
    _check_factor(annualization_factor)
    data = returns.returns
    rolling = data.rolling(window=window, min_periods=min_periods)
    std = rolling.std(ddof=1)
    # Constant windows: report exactly 0 instead of floating-point residue.
    constant = rolling.max() == rolling.min()
    std = std.mask(constant & std.notna(), 0.0)
    if annualize_result:
        std = std * math.sqrt(annualization_factor)
    counts = data.notna().astype("int64").rolling(window=window, min_periods=1).sum()
    metadata = ResultMetadata(
        context=returns.panel.context,
        assets=returns.panel.assets,
        start=returns.panel.start,
        end=returns.panel.end,
        calculation="rolling_volatility" + ("_annualized" if annualize_result else "_daily"),
        return_type=returns.return_type,
        window=window,
        min_observations=min_periods,
        annualization_factor=annualization_factor if annualize_result else None,
        sample_counts=returns.counts(),
    )
    return RollingResult(values=std, observations=counts.astype("int64"), metadata=metadata)
