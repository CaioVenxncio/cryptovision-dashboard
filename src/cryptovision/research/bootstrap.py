"""Stationary bootstrap (Politis & Romano, 1994) for the regime difference.

Days are resampled as whole rows: every asset's return, the regime label and
any derived per-day value move together, which preserves cross-asset
dependence. Blocks have geometric lengths with mean `mean_block_length` and
wrap around the end of the sample (circular). Regime labels are fixed
attributes of the original days and are not recomputed in replicates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from cryptovision.research.estimands import Method, regime_delta


def stationary_indices(n: int, mean_block_length: int, rng: np.random.Generator) -> np.ndarray:
    """One stationary-bootstrap resample of the positions 0..n-1."""
    if n < 1:
        raise ValueError("n must be positive")
    if mean_block_length < 1:
        raise ValueError("mean_block_length must be at least 1")
    new_block = rng.random(n) < 1.0 / mean_block_length
    new_block[0] = True
    starts = rng.integers(0, n, size=n)
    block_start_position = np.maximum.accumulate(np.where(new_block, np.arange(n), 0))
    offset = np.arange(n) - block_start_position
    return (starts[block_start_position] + offset) % n


@dataclass(frozen=True)
class BootstrapResult:
    estimate: float
    replicates: np.ndarray  # valid replicates only
    rejected: int
    confidence_level: float
    ci_low: float
    ci_high: float
    standard_error: float
    replications: int
    mean_block_length: int

    @property
    def rejected_fraction(self) -> float:
        return self.rejected / self.replications

    @property
    def excludes_zero(self) -> bool:
        return bool(self.ci_low > 0 or self.ci_high < 0)

    def interval(self, confidence_level: float) -> tuple[float, float]:
        alpha = 1 - confidence_level
        low, high = np.quantile(self.replicates, [alpha / 2, 1 - alpha / 2])
        return float(low), float(high)


def bootstrap_regime_deltas(
    arrays: Sequence[np.ndarray],
    high: np.ndarray,
    *,
    methods: Sequence[Method],
    replications: int,
    mean_block_length: int,
    confidence_level: float,
    min_days_per_regime: int,
    rng: np.random.Generator,
) -> list[BootstrapResult]:
    """Bootstrap Delta for several (array, method) estimands using the same resampled days.

    A replicate is rejected (and counted) if either regime has fewer than
    `min_days_per_regime` days or a correlation is undefined.
    """
    if len(arrays) != len(methods):
        raise ValueError("arrays and methods must have the same length")
    high = np.asarray(high, dtype=bool)
    n = len(high)
    estimates = [regime_delta(a, high, m) for a, m in zip(arrays, methods, strict=True)]
    draws = np.full((len(arrays), replications), np.nan)
    for b in range(replications):
        index = stationary_indices(n, mean_block_length, rng)
        resampled_high = high[index]
        n_high = int(resampled_high.sum())
        if n_high < min_days_per_regime or n - n_high < min_days_per_regime:
            continue
        for k, (array, method) in enumerate(zip(arrays, methods, strict=True)):
            draws[k, b] = regime_delta(array[index], resampled_high, method)

    alpha = 1 - confidence_level
    results = []
    for estimate, row in zip(estimates, draws, strict=True):
        valid = row[np.isfinite(row)]
        if valid.size < 2:
            low = high_bound = se = float("nan")
        else:
            low, high_bound = (float(v) for v in np.quantile(valid, [alpha / 2, 1 - alpha / 2]))
            se = float(np.std(valid, ddof=1))
        results.append(
            BootstrapResult(
                estimate=estimate,
                replicates=valid,
                rejected=replications - valid.size,
                confidence_level=confidence_level,
                ci_low=low,
                ci_high=high_bound,
                standard_error=se,
                replications=replications,
                mean_block_length=mean_block_length,
            )
        )
    return results
