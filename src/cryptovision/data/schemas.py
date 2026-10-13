"""Normalized historical data schemas.

Two dataset kinds exist because providers publish different information:

- `ohlcv`: exchange candles (Binance Vision, synthetic). Open/high/low/close in
  the quote currency, volumes in base and quote units. No market cap.
- `price_series`: aggregated daily points (CoinGecko). One price per day plus
  market cap and 24h volume, all in the quote currency.

The schemas are never merged: an exchange close price and an aggregated
00:00 UTC price are different measurements.
"""

from __future__ import annotations

from enum import StrEnum

import pyarrow as pa

SCHEMA_VERSION = "1.0"


class DatasetKind(StrEnum):
    OHLCV = "ohlcv"
    PRICE_SERIES = "price_series"


_TIMESTAMP = pa.timestamp("us", tz="UTC")

OHLCV_SCHEMA = pa.schema(
    [
        pa.field("timestamp_utc", _TIMESTAMP, nullable=False),  # candle open time
        pa.field("close_time_utc", _TIMESTAMP),
        pa.field("asset_id", pa.string(), nullable=False),
        pa.field("symbol", pa.string()),
        pa.field("pair", pa.string()),
        pa.field("exchange", pa.string()),
        pa.field("provider", pa.string(), nullable=False),
        pa.field("quote_currency", pa.string(), nullable=False),
        pa.field("frequency", pa.string(), nullable=False),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("volume_base", pa.float64()),  # base-asset units
        pa.field("volume_quote", pa.float64()),  # quote-currency units
        pa.field("trade_count", pa.int64()),
        pa.field("taker_buy_volume_base", pa.float64()),
        pa.field("taker_buy_volume_quote", pa.float64()),
    ]
)

PRICE_SERIES_SCHEMA = pa.schema(
    [
        pa.field("timestamp_utc", _TIMESTAMP, nullable=False),
        pa.field("asset_id", pa.string(), nullable=False),
        pa.field("symbol", pa.string()),
        pa.field("provider", pa.string(), nullable=False),
        pa.field("quote_currency", pa.string(), nullable=False),
        pa.field("frequency", pa.string(), nullable=False),
        pa.field("price", pa.float64()),
        pa.field("market_cap", pa.float64()),
        pa.field("volume_24h", pa.float64()),
    ]
)

SCHEMAS: dict[DatasetKind, pa.Schema] = {
    DatasetKind.OHLCV: OHLCV_SCHEMA,
    DatasetKind.PRICE_SERIES: PRICE_SERIES_SCHEMA,
}

# Columns that must hold a strictly positive price for a row to be valid.
PRICE_COLUMNS: dict[DatasetKind, tuple[str, ...]] = {
    DatasetKind.OHLCV: ("open", "high", "low", "close"),
    DatasetKind.PRICE_SERIES: ("price",),
}

# Non-price numeric columns. Nulls are allowed; negative values are invalid.
SECONDARY_COLUMNS: dict[DatasetKind, tuple[str, ...]] = {
    DatasetKind.OHLCV: (
        "volume_base",
        "volume_quote",
        "trade_count",
        "taker_buy_volume_base",
        "taker_buy_volume_quote",
    ),
    DatasetKind.PRICE_SERIES: ("market_cap", "volume_24h"),
}

SORT_KEYS = ("asset_id", "timestamp_utc")


def column_names(kind: DatasetKind) -> list[str]:
    return SCHEMAS[kind].names
