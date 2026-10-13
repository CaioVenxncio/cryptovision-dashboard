"""Average pairwise correlation and its regime difference.

    rho_bar(R) = (2 / (N (N-1))) * sum_{i<j} corr_R(x_i, x_j)
    Delta      = rho_bar(High) - rho_bar(Low)

Each unordered pair is counted once, the diagonal is excluded and all pairs
have equal weight. All pairs in a regime use the same days (listwise
complete), so the effective sample size is the number of days in the regime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

Method = Literal["pearson", "spearman"]


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Column-wise ranks (1-based); tied values share their average rank."""
    n, k = values.shape
    ranks = np.empty((n, k), dtype="float64")
    for column in range(k):
        x = values[:, column]
        order = np.argsort(x, kind="mergesort")
        sorted_x = x[order]
        new_group = np.concatenate(([True], sorted_x[1:] != sorted_x[:-1]))
        group = np.cumsum(new_group) - 1
        first = np.flatnonzero(new_group)
        counts = np.diff(np.append(first, n))
        average = first + (counts + 1) / 2.0
        ranks[order, column] = average[group]
    return ranks


def correlation_matrix(values: np.ndarray, method: Method = "pearson") -> np.ndarray:
    """N x N correlation of the columns. NaN rows/columns where a column is constant."""
    if values.ndim != 2 or values.shape[1] < 2:
        raise ValueError("values must be a 2-D array with at least two columns")
    if method == "spearman":
        values = _average_ranks(values)
    centered = values - values.mean(axis=0)
    cov = centered.T @ centered
    scale = np.sqrt(np.diag(cov))
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = cov / np.outer(scale, scale)
    corr[:, scale == 0] = np.nan
    corr[scale == 0, :] = np.nan
    return np.clip(corr, -1.0, 1.0)


def mean_pairwise(corr: np.ndarray) -> float:
    """Mean of the strictly upper-triangular entries; NaN if any pair is undefined."""
    upper = corr[np.triu_indices(corr.shape[0], k=1)]
    return float(upper.mean()) if np.all(np.isfinite(upper)) else float("nan")


def pair_count(n_assets: int) -> int:
    return n_assets * (n_assets - 1) // 2


@dataclass(frozen=True)
class RegimeEstimate:
    delta: float
    rho_high: float
    rho_low: float
    n_high: int
    n_low: int
    n_assets: int
    corr_high: np.ndarray
    corr_low: np.ndarray

    @property
    def n_pairs(self) -> int:
        return pair_count(self.n_assets)


def regime_estimate(
    values: np.ndarray, high: np.ndarray, method: Method = "pearson"
) -> RegimeEstimate:
    """Delta and its components for an (n_days x n_assets) array and a boolean High mask."""
    high = np.asarray(high, dtype=bool)
    corr_high = correlation_matrix(values[high], method)
    corr_low = correlation_matrix(values[~high], method)
    rho_high, rho_low = mean_pairwise(corr_high), mean_pairwise(corr_low)
    return RegimeEstimate(
        delta=rho_high - rho_low,
        rho_high=rho_high,
        rho_low=rho_low,
        n_high=int(high.sum()),
        n_low=int((~high).sum()),
        n_assets=values.shape[1],
        corr_high=corr_high,
        corr_low=corr_low,
    )


def regime_delta(values: np.ndarray, high: np.ndarray, method: Method = "pearson") -> float:
    """Fast path used inside the bootstrap: only Delta."""
    return mean_pairwise(correlation_matrix(values[high], method)) - mean_pairwise(
        correlation_matrix(values[~high], method)
    )
