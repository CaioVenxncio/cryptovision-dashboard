"""Transform market snapshots into numeric DataFrames and summaries."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from cryptovision.models import MarketSnapshot

NUMERIC_COLUMNS = (
    "price",
    "market_cap",
    "volume_24h",
    "change_24h_pct",
    "high_24h",
    "low_24h",
    "market_cap_change_24h",
    "circulating_supply",
)
COLUMNS = ("rank", "id", "name", "symbol", "image", *NUMERIC_COLUMNS, "last_updated")
EXPORT_COLUMNS = tuple(column for column in COLUMNS if column != "image")


def snapshot_to_frame(snapshot: MarketSnapshot) -> pd.DataFrame:
    """One row per asset, ordered by market-cap rank (unranked assets last).

    Numeric columns are float64, `rank` is nullable Int64 and `last_updated`
    is timezone-aware UTC. Missing provider values become NaN / NA.
    """
    rows = [
        {
            "rank": coin.market_cap_rank,
            "id": coin.id,
            "name": coin.name,
            "symbol": coin.symbol.upper(),
            "image": coin.image,
            "price": coin.current_price,
            "market_cap": coin.market_cap,
            "volume_24h": coin.total_volume,
            "change_24h_pct": coin.price_change_percentage_24h,
            "high_24h": coin.high_24h,
            "low_24h": coin.low_24h,
            "market_cap_change_24h": coin.market_cap_change_24h,
            "circulating_supply": coin.circulating_supply,
            "last_updated": coin.last_updated,
        }
        for coin in snapshot.coins
    ]
    frame = pd.DataFrame(rows, columns=list(COLUMNS))
    frame["rank"] = frame["rank"].astype("Int64")
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    frame["last_updated"] = pd.to_datetime(frame["last_updated"], utc=True)
    return frame.sort_values(
        ["rank", "market_cap"], ascending=[True, False], na_position="last", kind="stable"
    ).reset_index(drop=True)


def select_top(frame: pd.DataFrame, count: int) -> pd.DataFrame:
    """The first `count` rows of a frame produced by `snapshot_to_frame`."""
    if count < 1:
        raise ValueError("count must be >= 1")
    return frame.head(count).reset_index(drop=True)


@dataclass(frozen=True)
class SelectionSummary:
    """Aggregates over the selected assets only, not the whole crypto market."""

    asset_count: int
    market_cap_total: float | None
    volume_24h_total: float | None
    market_cap_change_24h_pct: float | None
    assets_missing_market_cap: int


def summarize_selection(frame: pd.DataFrame) -> SelectionSummary:
    """Sum market cap and volume, and compute the aggregate 24h market-cap change.

    The 24h change is `sum(change) / sum(market_cap - change) * 100`, i.e. the
    percentage change of the combined market cap of the selected assets, using
    only assets that report both values.
    """
    market_cap = frame["market_cap"]
    volume = frame["volume_24h"]

    complete = frame.dropna(subset=["market_cap", "market_cap_change_24h"])
    previous_total = (complete["market_cap"] - complete["market_cap_change_24h"]).sum()
    change_pct = (
        complete["market_cap_change_24h"].sum() / previous_total * 100
        if len(complete) and previous_total > 0
        else None
    )

    return SelectionSummary(
        asset_count=len(frame),
        market_cap_total=float(market_cap.sum()) if market_cap.notna().any() else None,
        volume_24h_total=float(volume.sum()) if volume.notna().any() else None,
        market_cap_change_24h_pct=float(change_pct) if change_pct is not None else None,
        assets_missing_market_cap=int(market_cap.isna().sum()),
    )


def to_csv_bytes(frame: pd.DataFrame, snapshot: MarketSnapshot) -> bytes:
    """Export numeric values at full precision with provenance columns, as UTF-8."""
    export = frame.loc[:, list(EXPORT_COLUMNS)].copy()
    export["currency"] = snapshot.vs_currency.upper()
    export["source"] = f"{snapshot.provider} {snapshot.endpoint}"
    export["fetched_at"] = snapshot.fetched_at
    return export.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode("utf-8")


def export_filename(snapshot: MarketSnapshot) -> str:
    stamp = snapshot.fetched_at.strftime("%Y%m%dT%H%M%SZ")
    return f"cryptovision_markets_{snapshot.vs_currency}_{stamp}.csv"
