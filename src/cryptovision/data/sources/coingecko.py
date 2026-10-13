"""CoinGecko daily history, for short-lived local caches only.

CoinGecko's API terms discourage storing Data and require any cache to be
refreshed at least every 24 hours (§6.1, §6.1.1). CryptoVision therefore never
archives CoinGecko history: datasets built here are marked `ephemeral`, expire
24 hours after retrieval and are refused by the loader afterwards.

Daily points come from the documented automatic granularity (ranges above 90
days return one point per day at 00:00 UTC). Each point is a price at that
instant, not an exchange close. The response may end with an intraday point
for the current time, which validation rejects as misaligned.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from cryptovision.data.config import AssetSpec
from cryptovision.data.schemas import DatasetKind, column_names
from cryptovision.data.storage import normalize_dtypes
from cryptovision.models import ChartPoint, MarketChart

PROVIDER_ID = "coingecko"
CACHE_RETENTION = timedelta(hours=24)
# The completed day's 00:00 UTC point is published shortly after midnight.
DAILY_PUBLICATION_DELAY = timedelta(minutes=10)
ATTRIBUTION = "Powered by CoinGecko (https://www.coingecko.com)."
LICENSE_NOTES = (
    "CoinGecko API terms §6.1 discourage storing Data and §6.1.1 require caches to be "
    "refreshed at least every 24 hours; §6.2 prohibits storing or deriving Data except as "
    "expressly permitted. This cache expires after 24 hours and must not be archived, "
    "shared or committed. See https://www.coingecko.com/en/api_terms"
)


def resolve_period(lookback_days: int, now: datetime) -> tuple[date, date]:
    """Inclusive daily period covered by `days=lookback_days` requested at `now`.

    The last point is today's 00:00 UTC point once published; the first is the
    first 00:00 UTC after `now - lookback_days`.
    """
    end = (now - DAILY_PUBLICATION_DELAY).date()
    start = end - timedelta(days=lookback_days - 1)
    return start, end


def _series(points: tuple[ChartPoint, ...], column: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime([point.timestamp for point in points], utc=True),
            column: [point.value for point in points],
        }
    )


def chart_to_frame(chart: MarketChart, *, asset: AssetSpec, quote_currency: str) -> pd.DataFrame:
    """Join the three chart series on timestamp into normalized price-series rows.

    A timestamp present in one series but not another gets nulls, never zeros.
    """
    merged = _series(chart.prices, "price")
    for points, column in ((chart.market_caps, "market_cap"), (chart.total_volumes, "volume_24h")):
        merged = merged.merge(_series(points, column), on="timestamp_utc", how="outer")
    merged = merged.assign(
        asset_id=asset.asset_id,
        symbol=asset.symbol,
        provider=PROVIDER_ID,
        quote_currency=quote_currency,
        frequency="1d",
    )
    return normalize_dtypes(
        merged.loc[:, column_names(DatasetKind.PRICE_SERIES)], DatasetKind.PRICE_SERIES
    )
