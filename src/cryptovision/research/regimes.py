"""Volatility proxies and regime classification.

All volatilities are sample standard deviations (ddof=1) of returns over a
fixed number of calendar rows. *Lagged* volatility for day t uses days
t-L..t-1 only (strictly past), so the return on day t never affects its own
regime label. The *contemporaneous* variant (days t-L+1..t) exists only for
the methodological illustration.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from cryptovision.research.config import AnalysisSpec

HIGH = "high"
LOW = "low"


def lagged_volatility(returns: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Volatility of days t-lookback..t-1, labelled on day t. Requires a full window."""
    return returns.rolling(lookback, min_periods=lookback).std(ddof=1).shift(1)


def contemporaneous_volatility(returns: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Volatility of days t-lookback+1..t (includes day t). Illustration only."""
    return returns.rolling(lookback, min_periods=lookback).std(ddof=1)


def volatility_proxy(returns: pd.DataFrame, spec: AnalysisSpec) -> pd.Series:
    """Market volatility proxy for each day, computed only from the returns given."""
    compute = contemporaneous_volatility if spec.contemporaneous else lagged_volatility
    if spec.proxy == "asset_volatility":
        return compute(returns[[spec.proxy_asset]], spec.lookback_days)[spec.proxy_asset]
    # Mean of individual volatilities (not the volatility of an equal-weight
    # portfolio, which would rise mechanically with cross-asset correlation).
    return compute(returns, spec.lookback_days).mean(axis=1, skipna=False)


@dataclass(frozen=True)
class RegimeClassification:
    proxy: pd.Series
    threshold: pd.Series
    labels: pd.Series  # "high", "low" or NaN (unclassified)


def classify_regimes(
    proxy: pd.Series, spec: AnalysisSpec, evaluation_mask: pd.Series
) -> RegimeClassification:
    """Label days High if the proxy exceeds the threshold, Low otherwise.

    `full_sample_quantile`: one threshold, the quantile of the proxy over the
    evaluation days (an in-sample, descriptive split).
    `trailing_quantile`: the quantile of the proxy over the previous
    `trailing_days` days (t-K..t-1), so classification uses only past data.
    """
    eligible = evaluation_mask & proxy.notna()
    if spec.threshold == "full_sample_quantile":
        value = float(proxy[eligible].quantile(spec.quantile)) if eligible.any() else np.nan
        threshold = pd.Series(value, index=proxy.index).where(eligible)
    else:
        threshold = (
            proxy.rolling(spec.trailing_days, min_periods=spec.trailing_days)
            .quantile(spec.quantile)
            .shift(1)
            .where(eligible)
        )
    defined = threshold.notna() & eligible
    labels = pd.Series(np.nan, index=proxy.index, dtype="object")
    labels[defined & (proxy > threshold)] = HIGH
    labels[defined & ~(proxy > threshold)] = LOW
    return RegimeClassification(proxy=proxy, threshold=threshold, labels=labels)
