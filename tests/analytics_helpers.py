"""Small hand-made price frames for analytics tests. All values are synthetic."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from cryptovision.analytics.alignment import PricePanel, build_price_panel

START = date(2024, 1, 1)


def long_frame(
    prices: dict[str, list[float | None]],
    *,
    start: date = START,
    quote: str = "USDT",
    provider: str = "synthetic",
) -> pd.DataFrame:
    """Long-format rows; a None price means the day has no observation (row omitted)."""
    rows = [
        {
            "timestamp_utc": pd.Timestamp(start + timedelta(days=offset), tz="UTC"),
            "asset_id": asset,
            "provider": provider,
            "quote_currency": quote,
            "frequency": "1d",
            "close": price,
        }
        for asset, series in prices.items()
        for offset, price in enumerate(series)
        if price is not None
    ]
    return pd.DataFrame(rows)


def panel(prices: dict[str, list[float | None]], **kwargs) -> PricePanel:
    return build_price_panel(long_frame(prices, **kwargs), price_column="close")
