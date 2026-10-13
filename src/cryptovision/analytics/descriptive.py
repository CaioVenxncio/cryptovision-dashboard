"""Per-asset descriptive summary of returns, volatility and drawdown."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from cryptovision.analytics.drawdown import max_drawdown
from cryptovision.analytics.exceptions import InsufficientDataError
from cryptovision.analytics.models import DEFAULT_ANNUALIZATION_FACTOR, ResultMetadata
from cryptovision.analytics.returns import ReturnsResult, ReturnStatus
from cryptovision.analytics.volatility import DEFAULT_MIN_OBSERVATIONS, sample_volatility


@dataclass(frozen=True)
class DescriptiveSummary:
    table: pd.DataFrame
    metadata: ResultMetadata


def describe_assets(
    returns: ReturnsResult,
    *,
    annualization_factor: int = DEFAULT_ANNUALIZATION_FACTOR,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> DescriptiveSummary:
    """One row per asset. Statistics needing more data than available are NaN.

    `missing_days` counts calendar days without a price between the asset's
    first and last observation in the selected period. `undefined_returns`
    counts days with a price whose return is undefined because the previous
    day has no price.
    """
    prices = returns.panel.prices
    rows = []
    for asset in prices.columns:
        observed = prices[asset].dropna()
        series = returns.series(asset)
        status = returns.status[asset]
        row: dict[str, object] = {
            "asset_id": asset,
            "first_observation": observed.index.min().date() if len(observed) else None,
            "last_observation": observed.index.max().date() if len(observed) else None,
            "price_observations": len(observed),
            "missing_days": (
                int((observed.index.max() - observed.index.min()).days + 1 - len(observed))
                if len(observed)
                else 0
            ),
            "return_observations": len(series),
            "undefined_returns": int((status == ReturnStatus.AFTER_GAP).sum()),
            "mean_return": math.nan,
            "median_return": math.nan,
            "min_return": math.nan,
            "max_return": math.nan,
            "daily_volatility": math.nan,
            "annualized_volatility": math.nan,
            "max_drawdown": math.nan,
            "drawdown_peak": None,
            "drawdown_trough": None,
            "drawdown_recovered": None,
        }
        if len(series) >= min_observations:
            daily = sample_volatility(series, min_observations=min_observations)
            row.update(
                mean_return=float(series.mean()),
                median_return=float(series.median()),
                min_return=float(series.min()),
                max_return=float(series.max()),
                daily_volatility=daily,
                annualized_volatility=daily * math.sqrt(annualization_factor),
            )
        try:
            drawdown = max_drawdown(prices[asset])
            row.update(
                max_drawdown=drawdown.max_drawdown,
                drawdown_peak=drawdown.peak_date,
                drawdown_trough=drawdown.trough_date,
                drawdown_recovered=drawdown.recovered,
            )
        except InsufficientDataError:
            pass
        rows.append(row)

    metadata = ResultMetadata(
        context=returns.panel.context,
        assets=returns.panel.assets,
        start=returns.panel.start,
        end=returns.panel.end,
        calculation="descriptive_summary",
        return_type=returns.return_type,
        min_observations=min_observations,
        annualization_factor=annualization_factor,
        sample_counts=returns.counts(),
    )
    return DescriptiveSummary(table=pd.DataFrame(rows).set_index("asset_id"), metadata=metadata)
