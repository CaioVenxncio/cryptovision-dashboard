"""Pearson and Spearman correlation of returns, full-period and rolling.

Pairwise deletion: each pair uses only the days on which *both* assets have a
defined return, so one asset's gap does not remove data from other pairs.
Listwise deletion (common days for all assets) is not used because one
short-history asset would shrink every pair. Sample counts are returned with
every coefficient, because pairs can rest on different days.

Undefined coefficients (NaN):
- `insufficient_overlap`: fewer than `min_overlap` common observations;
- `constant_series`: one series is constant over the sample (zero variance).

Spearman = Pearson correlation of the ranks (ties get their average rank).
Correlation describes co-movement, not causation.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from cryptovision.analytics.exceptions import UnknownAssetError
from cryptovision.analytics.models import CorrelationMethod, ResultMetadata
from cryptovision.analytics.returns import ReturnsResult
from cryptovision.analytics.volatility import RollingResult

DEFAULT_MIN_OVERLAP = 30
DEFAULT_ROLLING_WINDOWS = (30, 90, 180)
INSUFFICIENT = "insufficient_overlap"
CONSTANT = "constant_series"


def _ranks(values: np.ndarray) -> np.ndarray:
    return pd.Series(values).rank(method="average").to_numpy(dtype="float64")


def pair_correlation(
    x: np.ndarray, y: np.ndarray, method: CorrelationMethod | str = CorrelationMethod.PEARSON
) -> float | None:
    """Correlation of two equal-length, fully observed arrays; None if a series is constant."""
    method = CorrelationMethod(method)
    if len(x) != len(y):
        raise ValueError("x and y must have the same length")
    if len(x) < 2 or np.all(x == x[0]) or np.all(y == y[0]):
        return None
    if method is CorrelationMethod.SPEARMAN:
        x, y = _ranks(x), _ranks(y)
    xc, yc = x - x.mean(), y - y.mean()
    value = float(np.dot(xc, yc) / np.sqrt(np.dot(xc, xc) * np.dot(yc, yc)))
    return min(1.0, max(-1.0, value))


@dataclass(frozen=True)
class CorrelationResult:
    matrix: pd.DataFrame
    counts: pd.DataFrame
    undefined: dict[tuple[str, str], str]
    metadata: ResultMetadata


def correlation_matrix(
    returns: ReturnsResult,
    *,
    method: CorrelationMethod | str = CorrelationMethod.PEARSON,
    min_overlap: int = DEFAULT_MIN_OVERLAP,
) -> CorrelationResult:
    method = CorrelationMethod(method)
    if min_overlap < 2:
        raise ValueError("min_overlap must be at least 2")
    data = returns.returns
    assets = list(data.columns)
    matrix = pd.DataFrame(np.nan, index=assets, columns=assets)
    counts = pd.DataFrame(0, index=assets, columns=assets, dtype="int64")
    undefined: dict[tuple[str, str], str] = {}

    for a, b in [(asset, asset) for asset in assets] + list(combinations(assets, 2)):
        pair = data[[a, b]].dropna() if a != b else data[[a]].dropna()
        x = pair[a].to_numpy()
        y = pair[b].to_numpy() if a != b else x
        counts.loc[a, b] = counts.loc[b, a] = len(pair)
        if len(pair) < min_overlap:
            undefined[(a, b)] = INSUFFICIENT
            continue
        value = pair_correlation(x, y, method)
        if value is None:
            undefined[(a, b)] = CONSTANT
            continue
        matrix.loc[a, b] = matrix.loc[b, a] = 1.0 if a == b else value

    metadata = ResultMetadata(
        context=returns.panel.context,
        assets=returns.panel.assets,
        start=returns.panel.start,
        end=returns.panel.end,
        calculation="correlation_matrix",
        return_type=returns.return_type,
        method=method,
        min_observations=min_overlap,
        sample_counts=returns.counts(),
    )
    return CorrelationResult(matrix=matrix, counts=counts, undefined=undefined, metadata=metadata)


def rolling_correlation(
    returns: ReturnsResult,
    asset_a: str,
    asset_b: str,
    *,
    window: int,
    method: CorrelationMethod | str = CorrelationMethod.PEARSON,
    min_periods: int | None = None,
) -> RollingResult:
    """Correlation over `window` calendar days ending on (and including) each day.

    Only days where both returns exist count. With the default
    `min_periods = window`, a window containing any gap is undefined. Constant
    windows are undefined. The first `window - 1` days are undefined.
    """
    method = CorrelationMethod(method)
    for asset in (asset_a, asset_b):
        if asset not in returns.returns.columns:
            raise UnknownAssetError(f"Unknown asset: {asset}")
    if asset_a == asset_b:
        raise ValueError("Rolling correlation needs two different assets.")
    min_periods = window if min_periods is None else min_periods
    if not 2 <= min_periods <= window:
        raise ValueError("min_periods must be between 2 and window")

    x = returns.returns[asset_a].to_numpy(dtype="float64")
    y = returns.returns[asset_b].to_numpy(dtype="float64")
    both = np.isfinite(x) & np.isfinite(y)
    index = returns.returns.index
    values = np.full(len(index), np.nan)
    counts = np.zeros(len(index), dtype="int64")

    if len(index) >= window:
        xs, ys = sliding_window_view(x, window), sliding_window_view(y, window)
        masks = sliding_window_view(both, window)
        for end, (wx, wy, mask) in enumerate(zip(xs, ys, masks, strict=True), start=window - 1):
            n = int(mask.sum())
            counts[end] = n
            if n >= min_periods:
                value = pair_correlation(wx[mask], wy[mask], method)
                values[end] = np.nan if value is None else value
    # Partial windows at the start still report how many pairs they contain.
    head = min(window - 1, len(index))
    counts[:head] = np.cumsum(both[:head])

    label = f"{asset_a}|{asset_b}"
    metadata = ResultMetadata(
        context=returns.panel.context,
        assets=(asset_a, asset_b),
        start=returns.panel.start,
        end=returns.panel.end,
        calculation="rolling_correlation",
        return_type=returns.return_type,
        method=method,
        window=window,
        min_observations=min_periods,
        sample_counts={label: int(both.sum())},
    )
    return RollingResult(
        values=pd.DataFrame({label: values}, index=index),
        observations=pd.DataFrame({label: counts}, index=index),
        metadata=metadata,
    )
