from __future__ import annotations

import io

import pandas as pd
import pytest

from cryptovision.market import (
    EXPORT_COLUMNS,
    NUMERIC_COLUMNS,
    export_filename,
    select_top,
    snapshot_to_frame,
    summarize_selection,
    to_csv_bytes,
)
from cryptovision.models import MarketCoin, MarketSnapshot
from tests.conftest import FIXED_NOW, load_fixture


@pytest.fixture
def snapshot() -> MarketSnapshot:
    coins = [MarketCoin.model_validate(item) for item in load_fixture("coins_markets.json")]
    # Reverse to check that the frame is re-ordered by rank.
    return MarketSnapshot(
        provider="CoinGecko",
        endpoint="/coins/markets",
        vs_currency="usd",
        fetched_at=FIXED_NOW,
        coins=tuple(reversed(coins)),
    )


def test_frame_keeps_numeric_types(snapshot):
    frame = snapshot_to_frame(snapshot)

    for column in NUMERIC_COLUMNS:
        assert frame[column].dtype == "float64", column
    assert str(frame["rank"].dtype) == "Int64"
    assert isinstance(frame["last_updated"].dtype, pd.DatetimeTZDtype)
    assert str(frame["last_updated"].dt.tz) == "UTC"


def test_frame_sorted_by_rank_with_unranked_last(snapshot):
    frame = snapshot_to_frame(snapshot)
    assert frame["id"].tolist() == ["bitcoin", "ethereum", "tiny-token"]
    assert frame["symbol"].tolist() == ["BTC", "ETH", "TINY"]


def test_missing_values_become_nan(snapshot):
    tiny = snapshot_to_frame(snapshot).iloc[2]
    assert pd.isna(tiny["market_cap"])
    assert pd.isna(tiny["rank"])
    assert tiny["price"] == pytest.approx(0.00001234)


def test_numeric_sorting_is_by_value_not_text(snapshot):
    frame = snapshot_to_frame(snapshot).sort_values("price")
    assert frame["id"].tolist() == ["tiny-token", "ethereum", "bitcoin"]


def test_select_top(snapshot):
    frame = snapshot_to_frame(snapshot)
    assert select_top(frame, 2)["id"].tolist() == ["bitcoin", "ethereum"]
    assert len(select_top(frame, 50)) == 3
    with pytest.raises(ValueError):
        select_top(frame, 0)


def test_summary_aggregates_selected_assets_only(snapshot):
    summary = summarize_selection(snapshot_to_frame(snapshot))

    assert summary.asset_count == 3
    assert summary.market_cap_total == 1_500_000_000_000
    assert summary.volume_24h_total == 45_000_000_000
    assert summary.assets_missing_market_cap == 1
    # Combined change: (20e9 - 5e9) / ((1200e9 - 20e9) + (300e9 + 5e9)) * 100
    assert summary.market_cap_change_24h_pct == pytest.approx(15 / 1485 * 100)


def test_summary_with_no_market_data():
    frame = pd.DataFrame(
        {
            "market_cap": [float("nan")],
            "volume_24h": [float("nan")],
            "market_cap_change_24h": [float("nan")],
        }
    )
    summary = summarize_selection(frame)
    assert summary.market_cap_total is None
    assert summary.volume_24h_total is None
    assert summary.market_cap_change_24h_pct is None


def test_csv_export_round_trips_full_precision(snapshot):
    frame = snapshot_to_frame(snapshot)

    data = to_csv_bytes(frame, snapshot)
    parsed = pd.read_csv(io.BytesIO(data))

    assert list(parsed.columns) == [*EXPORT_COLUMNS, "currency", "source", "fetched_at"]
    assert "image" not in parsed.columns
    assert parsed.loc[0, "price"] == 60000.5
    assert parsed.loc[2, "price"] == pytest.approx(0.00001234, rel=0, abs=1e-15)
    assert pd.isna(parsed.loc[2, "market_cap"])
    assert parsed.loc[0, "last_updated"] == "2026-10-13T12:00:30Z"
    assert set(parsed["fetched_at"]) == {"2026-10-13T12:05:00Z"}
    assert set(parsed["source"]) == {"CoinGecko /coins/markets"}
    assert set(parsed["currency"]) == {"USD"}


def test_csv_export_does_not_touch_the_filesystem(snapshot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    to_csv_bytes(snapshot_to_frame(snapshot), snapshot)
    assert list(tmp_path.iterdir()) == []


def test_export_filename(snapshot):
    assert export_filename(snapshot) == "cryptovision_markets_usd_20261013T120500Z.csv"
