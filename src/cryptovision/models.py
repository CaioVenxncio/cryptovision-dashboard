"""Typed internal data models.

Provider responses are validated into these models so the rest of the
application never depends on raw JSON shapes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_to_utc)]
OptionalUtcDatetime = Annotated[datetime | None, AfterValidator(_to_utc)]


class MarketCoin(BaseModel):
    """One asset from CoinGecko `/coins/markets`. Market values may be null."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)
    image: str | None = None
    current_price: float | None = None
    market_cap: float | None = None
    market_cap_rank: int | None = None
    total_volume: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    price_change_percentage_24h: float | None = None
    market_cap_change_24h: float | None = None
    circulating_supply: float | None = None
    last_updated: OptionalUtcDatetime = None


class MarketSnapshot(BaseModel):
    """A batch of market records with provenance and freshness metadata."""

    model_config = ConfigDict(frozen=True)

    provider: str
    endpoint: str
    vs_currency: str
    fetched_at: UtcDatetime
    coins: tuple[MarketCoin, ...]
    dropped_records: int = 0

    @property
    def data_last_updated(self) -> datetime | None:
        """Most recent provider-reported update time across all coins."""
        times = [coin.last_updated for coin in self.coins if coin.last_updated is not None]
        return max(times) if times else None


class SimplePriceQuote(BaseModel):
    """One asset from CoinGecko `/simple/price`."""

    model_config = ConfigDict(frozen=True)

    id: str
    vs_currency: str
    price: float | None = None
    market_cap: float | None = None
    volume_24h: float | None = None
    change_24h_percent: float | None = None
    last_updated: OptionalUtcDatetime = None


class SimplePriceResult(BaseModel):
    """Quotes for the requested ids, plus the ids the provider did not return."""

    model_config = ConfigDict(frozen=True)

    provider: str
    endpoint: str
    fetched_at: UtcDatetime
    quotes: dict[str, SimplePriceQuote]
    missing_ids: tuple[str, ...] = ()
