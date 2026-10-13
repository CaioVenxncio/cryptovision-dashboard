"""Deterministic synthetic OHLCV datasets for tests and offline demonstrations.

Synthetic data is never market data. Rows use provider `synthetic`, exchange
`synthetic`, quote currency `SYNTH` and asset ids prefixed `synthetic-`, and
manifests set `synthetic: true`.

Generation rules (seeded `numpy.random.default_rng`):
- Daily log returns are `0.6 * market + 0.8 * idiosyncratic` with both factors
  standard normal, scaled by each asset's daily volatility (2%, 3%, 4%), giving
  a pairwise correlation of about 0.36.
- Close follows `close_t = close_{t-1} * exp(return_t)` from start prices 100,
  50 and 10. Open is the previous close. High and low extend the open/close
  range by `|N(0, 1)| * 0.5%`. Base volume is log-normal; quote volume is base
  volume times close; trade count is base volume / 10, rounded.

With `with_anomalies=True`, documented defects are injected after generation:
two missing days (asset A), an identical duplicate row (asset B), a conflicting
duplicate (asset B), a zero close (asset C), a null base volume (asset C), and
reversed row order for the first five rows of asset A.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from cryptovision.data.config import AssetSpec, DatasetConfig, SelectionInfo
from cryptovision.data.schemas import DatasetKind, column_names
from cryptovision.data.storage import normalize_dtypes

SYNTHETIC_ASSETS = (
    AssetSpec(asset_id="synthetic-a", symbol="SYNA"),
    AssetSpec(asset_id="synthetic-b", symbol="SYNB"),
    AssetSpec(asset_id="synthetic-c", symbol="SYNC"),
)
_START_PRICES = (100.0, 50.0, 10.0)
_DAILY_VOLATILITY = (0.02, 0.03, 0.04)
_MARKET_WEIGHT, _IDIOSYNCRATIC_WEIGHT = 0.6, 0.8


def synthetic_config(
    *, start: date, days: int, seed: int, with_anomalies: bool, version: str = "1.0.0"
) -> DatasetConfig:
    suffix = "anomalies" if with_anomalies else "clean"
    return DatasetConfig(
        id=f"synthetic-ohlcv-{suffix}-seed{seed}",
        version=version,
        description=(
            f"Synthetic OHLCV data ({suffix}), seed {seed}, {days} days. Not market observations."
        ),
        provider="synthetic",
        quote_currency="SYNTH",
        start=start,
        end=start + timedelta(days=days - 1),
        assets=SYNTHETIC_ASSETS,
        selection=SelectionInfo(rule="Fixed synthetic assets for testing and demonstration."),
    )


def generate_synthetic_ohlcv(
    *, start: date, days: int, seed: int, with_anomalies: bool = False
) -> pd.DataFrame:
    if days < 6:
        raise ValueError("days must be at least 6")
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=days, freq="D", tz="UTC")
    market = rng.standard_normal(days)
    frames = []
    for asset, start_price, volatility in zip(
        SYNTHETIC_ASSETS, _START_PRICES, _DAILY_VOLATILITY, strict=True
    ):
        shocks = _MARKET_WEIGHT * market + _IDIOSYNCRATIC_WEIGHT * rng.standard_normal(days)
        close = start_price * np.exp(np.cumsum(volatility * shocks))
        open_ = np.concatenate(([start_price], close[:-1]))
        spread = np.abs(rng.standard_normal((2, days))) * 0.005
        high = np.maximum(open_, close) * (1 + spread[0])
        low = np.minimum(open_, close) * (1 - spread[1])
        volume_base = rng.lognormal(mean=10, sigma=0.5, size=days)
        frames.append(
            pd.DataFrame(
                {
                    "timestamp_utc": dates,
                    "close_time_utc": dates + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1),
                    "asset_id": asset.asset_id,
                    "symbol": asset.symbol,
                    "pair": f"{asset.symbol}SYNTH",
                    "exchange": "synthetic",
                    "provider": "synthetic",
                    "quote_currency": "SYNTH",
                    "frequency": "1d",
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume_base": volume_base,
                    "volume_quote": volume_base * close,
                    "trade_count": np.round(volume_base / 10).astype("int64"),
                    "taker_buy_volume_base": volume_base * 0.5,
                    "taker_buy_volume_quote": volume_base * 0.5 * close,
                }
            )
        )
    frame = pd.concat(frames, ignore_index=True).loc[:, column_names(DatasetKind.OHLCV)]
    frame = normalize_dtypes(frame, DatasetKind.OHLCV)
    return _inject_anomalies(frame) if with_anomalies else frame


def _inject_anomalies(frame: pd.DataFrame) -> pd.DataFrame:
    a = frame[frame["asset_id"] == "synthetic-a"]
    b = frame[frame["asset_id"] == "synthetic-b"]
    c_index = frame.index[frame["asset_id"] == "synthetic-c"]

    frame = frame.drop(index=a.index[2:4])  # two missing days
    identical = b.iloc[[1]]
    conflicting = b.iloc[[3]].assign(close=b.iloc[3]["close"] * 1.1)
    frame = frame.copy()
    frame.loc[c_index[2], "close"] = 0.0  # non-positive price
    frame.loc[c_index[4], "volume_base"] = np.nan  # null volume
    frame = pd.concat([frame, identical, conflicting], ignore_index=True)

    first_a = frame.index[frame["asset_id"] == "synthetic-a"][:5]
    reordered = frame.loc[first_a[::-1]]
    rest = frame.drop(index=first_a)
    return pd.concat([reordered, rest], ignore_index=True)
