"""Drawdown from observed prices (close prices for Binance candles).

    Peak_t = max(P_0, ..., P_t)
    DD_t   = P_t / Peak_t - 1          (0 at a new high, negative below it)
    MDD    = min_t DD_t

Days without a price have no drawdown value; peaks are taken over observed
prices only. Tie-breaking:

- trough: the earliest day on which MDD is reached;
- peak: the latest day on or before the trough whose price equals the
  running peak at the trough (the drawdown starts when the price last stood
  at that high);
- recovery: the first observed day after the trough with price >= peak price.
  If none exists the drawdown is unrecovered and no recovery date is given.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from cryptovision.analytics.exceptions import InsufficientDataError, InvalidPriceError


@dataclass(frozen=True)
class DrawdownResult:
    max_drawdown: float  # <= 0; e.g. -0.5 means a 50% fall from the peak
    peak_date: date | None
    peak_price: float | None
    trough_date: date | None
    trough_price: float | None
    recovery_date: date | None
    recovered: bool | None  # None when there was no drawdown at all
    duration_days: int  # calendar days from peak to trough
    duration_observations: int  # observed prices from peak to trough (steps)
    recovery_days: int | None  # calendar days from peak to recovery
    observations: int

    @property
    def magnitude(self) -> float:
        return -self.max_drawdown


def _observed(prices: pd.Series) -> pd.Series:
    observed = prices.dropna().sort_index()
    if not observed.index.is_unique:
        raise InvalidPriceError("Price index has duplicate timestamps.")
    values = observed.to_numpy(dtype="float64")
    if (~np.isfinite(values) | (values <= 0)).any():
        raise InvalidPriceError("Prices must be finite and strictly positive.")
    return observed.astype("float64")


def drawdown_series(prices: pd.Series) -> pd.Series:
    """Drawdown on each observed day; NaN on days without a price."""
    observed = _observed(prices)
    return (observed / observed.cummax() - 1.0).reindex(prices.index)


def max_drawdown(prices: pd.Series) -> DrawdownResult:
    observed = _observed(prices)
    if len(observed) < 2:
        raise InsufficientDataError("At least two observed prices are required.")
    drawdowns = observed / observed.cummax() - 1.0
    worst = float(drawdowns.min())
    if worst == 0.0:
        return DrawdownResult(
            max_drawdown=0.0,
            peak_date=None,
            peak_price=None,
            trough_date=None,
            trough_price=None,
            recovery_date=None,
            recovered=None,
            duration_days=0,
            duration_observations=0,
            recovery_days=None,
            observations=len(observed),
        )

    trough = drawdowns.idxmin()  # first occurrence
    before = observed.loc[:trough]
    peak_price = float(before.max())
    peak = before.index[before == peak_price][-1]
    after = observed.loc[observed.index > trough]
    recovered_at = after.index[after >= peak_price]
    recovery = recovered_at[0] if len(recovered_at) else None
    positions = observed.index
    return DrawdownResult(
        max_drawdown=worst,
        peak_date=peak.date(),
        peak_price=peak_price,
        trough_date=trough.date(),
        trough_price=float(observed.loc[trough]),
        recovery_date=recovery.date() if recovery is not None else None,
        recovered=recovery is not None,
        duration_days=(trough - peak).days,
        duration_observations=int(positions.get_loc(trough) - positions.get_loc(peak)),
        recovery_days=(recovery - peak).days if recovery is not None else None,
        observations=len(observed),
    )
