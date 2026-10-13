"""Temporal alignment: turn long-format observations into a calendar-complete price panel.

Policy (used by every analytics module):

- One provider, one quote currency, frequency `1d`, timestamps at 00:00 UTC.
  Anything else raises `IncompatibleDataError`; nothing is converted.
- The panel index contains every calendar day in the selected period. A day
  without an observation is NaN in the panel. Nothing is interpolated or
  forward-filled.
- Duplicate (asset, day) observations raise `DuplicateObservationError`.
- Prices must be finite and strictly positive, else `InvalidPriceError`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import numpy as np
import pandas as pd

from cryptovision.analytics.exceptions import (
    DuplicateObservationError,
    IncompatibleDataError,
    InsufficientDataError,
    InvalidPriceError,
    UnknownAssetError,
)
from cryptovision.analytics.models import AnalysisContext

REQUIRED_COLUMNS = ("timestamp_utc", "asset_id", "provider", "quote_currency", "frequency")
SUPPORTED_FREQUENCY = "1d"
MAX_EXAMPLES = 3


@dataclass(frozen=True)
class PricePanel:
    """Prices with a calendar-complete daily UTC index (rows) and one column per asset."""

    prices: pd.DataFrame
    context: AnalysisContext

    @property
    def assets(self) -> tuple[str, ...]:
        return tuple(self.prices.columns)

    @property
    def start(self) -> date:
        return self.prices.index[0].date()

    @property
    def end(self) -> date:
        return self.prices.index[-1].date()

    def observation_counts(self) -> dict[str, int]:
        return {asset: int(count) for asset, count in self.prices.notna().sum().items()}

    def select(
        self,
        assets: list[str] | tuple[str, ...] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> PricePanel:
        """Subset assets and/or period. The calendar index stays complete."""
        prices = self.prices
        if assets is not None:
            _check_assets(assets, prices.columns)
            prices = prices.loc[:, list(assets)]
        if start is not None:
            prices = prices.loc[prices.index >= _utc_midnight(start)]
        if end is not None:
            prices = prices.loc[prices.index <= _utc_midnight(end)]
        if prices.empty or prices.shape[1] == 0:
            raise InsufficientDataError("The selection contains no days or no assets.")
        return replace(self, prices=prices)


def _utc_midnight(day: date) -> pd.Timestamp:
    return pd.Timestamp(day).tz_localize("UTC")


def _check_assets(assets: list[str] | tuple[str, ...], available: pd.Index) -> None:
    unknown = [asset for asset in assets if asset not in available]
    if unknown:
        raise UnknownAssetError(f"Unknown assets: {', '.join(unknown)}")
    if len(set(assets)) != len(assets):
        raise UnknownAssetError("Assets must not be repeated.")


def _single_value(frame: pd.DataFrame, column: str) -> str:
    values = frame[column].dropna().unique()
    if len(values) != 1:
        raise IncompatibleDataError(
            f"Expected exactly one {column}, found {len(values)}: "
            f"{', '.join(sorted(map(str, values))[:MAX_EXAMPLES])}"
        )
    return str(values[0])


def context_from_frame(frame: pd.DataFrame, *, price_column: str) -> AnalysisContext:
    """A context for data that did not come from a stored dataset (e.g. tests)."""
    return AnalysisContext(
        dataset_id="in-memory",
        dataset_version="n/a",
        provider=_single_value(frame, "provider"),
        quote_currency=_single_value(frame, "quote_currency"),
        frequency=_single_value(frame, "frequency"),
        price_column=price_column,
        synthetic=_single_value(frame, "provider") == "synthetic",
    )


def build_price_panel(
    frame: pd.DataFrame,
    *,
    price_column: str,
    context: AnalysisContext | None = None,
    assets: list[str] | tuple[str, ...] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> PricePanel:
    """Validate long-format observations and pivot them into a `PricePanel`."""
    missing = [c for c in (*REQUIRED_COLUMNS, price_column) if c not in frame.columns]
    if missing:
        raise IncompatibleDataError(f"Missing columns: {', '.join(missing)}")
    if frame.empty:
        raise InsufficientDataError("No observations.")

    provider = _single_value(frame, "provider")
    quote = _single_value(frame, "quote_currency")
    frequency = _single_value(frame, "frequency")
    if frequency != SUPPORTED_FREQUENCY:
        raise IncompatibleDataError(f"Only daily data is supported, got {frequency!r}.")
    context = context or context_from_frame(frame, price_column=price_column)
    if (context.provider, context.quote_currency) != (provider, quote):
        raise IncompatibleDataError("The context does not match the data's provider or currency.")

    data = frame
    if assets is not None:
        _check_assets(assets, pd.Index(frame["asset_id"].unique()))
        data = data[data["asset_id"].isin(assets)]

    timestamps = pd.to_datetime(data["timestamp_utc"])
    if timestamps.dt.tz is None or str(timestamps.dt.tz) != "UTC":
        raise IncompatibleDataError("Timestamps must be timezone-aware UTC.")
    if timestamps.isna().any():
        raise IncompatibleDataError("Timestamps must not be missing.")
    misaligned = timestamps != timestamps.dt.floor("D")
    if misaligned.any():
        raise IncompatibleDataError(
            "All daily observations must be stamped 00:00 UTC; "
            f"{int(misaligned.sum())} are not (mixed daily boundaries)."
        )

    keyed = pd.DataFrame(
        {"timestamp_utc": timestamps, "asset_id": data["asset_id"], "price": data[price_column]}
    )
    duplicated = keyed.duplicated(["asset_id", "timestamp_utc"], keep=False)
    if duplicated.any():
        examples = keyed.loc[duplicated, ["asset_id", "timestamp_utc"]].head(MAX_EXAMPLES)
        raise DuplicateObservationError(
            f"{int(duplicated.sum())} rows share an (asset, day): "
            + "; ".join(f"{a} {t.date()}" for a, t in examples.itertuples(index=False))
        )

    prices = pd.to_numeric(keyed["price"], errors="coerce").astype("float64")
    invalid = ~np.isfinite(prices) | (prices <= 0)
    if invalid.any():
        examples = keyed.loc[invalid, ["asset_id", "timestamp_utc"]].head(MAX_EXAMPLES)
        raise InvalidPriceError(
            f"{int(invalid.sum())} prices are missing, non-finite, zero or negative: "
            + "; ".join(f"{a} {t.date()}" for a, t in examples.itertuples(index=False))
        )

    wide = keyed.assign(price=prices).pivot(
        index="timestamp_utc", columns="asset_id", values="price"
    )
    first = _utc_midnight(start) if start is not None else wide.index.min()
    last = _utc_midnight(end) if end is not None else wide.index.max()
    if last < first:
        raise InsufficientDataError("The period end is before its start.")
    calendar = pd.date_range(first, last, freq="D", tz="UTC", name="timestamp_utc")
    columns = list(assets) if assets is not None else sorted(wide.columns)
    panel = wide.reindex(index=calendar, columns=columns)
    panel.columns.name = "asset_id"
    return PricePanel(prices=panel, context=context)
