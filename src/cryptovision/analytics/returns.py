"""Simple and logarithmic returns on a calendar-complete price panel.

    simple:  R_t = P_t / P_{t-1} - 1
    log:     r_t = ln(P_t / P_{t-1})

`t-1` is the previous calendar day. A return exists only when both days have
an observed price, so returns never bridge gaps and never cross assets (each
column is computed independently). With Binance daily candles, P_t is the
close of UTC day t, so R_t is the close-to-close return over day t.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from cryptovision.analytics.alignment import PricePanel
from cryptovision.analytics.exceptions import UnknownAssetError
from cryptovision.analytics.models import ResultMetadata, ReturnType


class ReturnStatus(StrEnum):
    """Why a return cell has (or lacks) a value."""

    VALID = "valid"
    FIRST_OBSERVATION = "first_observation"  # no earlier price for this asset
    MISSING_PRICE = "missing_price"  # no price on this day
    AFTER_GAP = "after_gap"  # price today, but none on the previous day


@dataclass(frozen=True)
class ReturnsResult:
    returns: pd.DataFrame
    status: pd.DataFrame
    return_type: ReturnType
    panel: PricePanel

    def series(self, asset: str) -> pd.Series:
        """Defined returns of one asset, indexed by the day they end on."""
        if asset not in self.returns.columns:
            raise UnknownAssetError(f"Unknown asset: {asset}")
        return self.returns[asset].dropna()

    def counts(self) -> dict[str, int]:
        return {asset: int(n) for asset, n in self.returns.notna().sum().items()}

    def metadata(self, calculation: str = "returns") -> ResultMetadata:
        return ResultMetadata(
            context=self.panel.context,
            assets=self.panel.assets,
            start=self.panel.start,
            end=self.panel.end,
            calculation=calculation,
            return_type=self.return_type,
            sample_counts=self.counts(),
        )


def compute_returns(
    panel: PricePanel, return_type: ReturnType | str = ReturnType.LOG
) -> ReturnsResult:
    return_type = ReturnType(return_type)
    prices = panel.prices
    previous = prices.shift(1)  # previous calendar day; the index has no gaps
    ratio = prices / previous
    returns = np.log(ratio) if return_type is ReturnType.LOG else ratio - 1.0

    observed = prices.notna()
    seen_before = observed.cumsum().shift(1, fill_value=0) > 0
    status = pd.DataFrame(
        np.select(
            [~observed, observed & previous.isna() & ~seen_before, observed & previous.isna()],
            [ReturnStatus.MISSING_PRICE, ReturnStatus.FIRST_OBSERVATION, ReturnStatus.AFTER_GAP],
            default=ReturnStatus.VALID,
        ),
        index=prices.index,
        columns=prices.columns,
    )
    return ReturnsResult(returns=returns, status=status, return_type=return_type, panel=panel)


def simple_returns(panel: PricePanel) -> ReturnsResult:
    return compute_returns(panel, ReturnType.SIMPLE)


def log_returns(panel: PricePanel) -> ReturnsResult:
    return compute_returns(panel, ReturnType.LOG)
