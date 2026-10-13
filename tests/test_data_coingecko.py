from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest
from responses import matchers

from cryptovision.data.config import AssetSpec
from cryptovision.data.sources.coingecko import chart_to_frame, resolve_period
from cryptovision.providers.coingecko import API_KEY_HEADER
from cryptovision.providers.errors import ResponseSchemaError
from tests.conftest import BASE_URL, FAKE_KEY, FIXED_NOW

CHART_URL = f"{BASE_URL}/coins/bitcoin/market_chart"
ASSET = AssetSpec(asset_id="bitcoin", symbol="BTC", coingecko_id="bitcoin")
DAY_MS = 86_400_000
JAN_1_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z


def chart_payload():
    return {
        "prices": [
            [JAN_1_MS, 42000.5],
            [JAN_1_MS + DAY_MS, 43000.0],
            [JAN_1_MS + DAY_MS + 5, 43100],
        ],
        "market_caps": [[JAN_1_MS, 8.2e11], [JAN_1_MS + DAY_MS, 0]],
        "total_volumes": [[JAN_1_MS + DAY_MS, 2.5e10]],
    }


def test_daily_chart_request_uses_header_and_auto_granularity(client, mocked_api):
    mocked_api.get(
        CHART_URL,
        json=chart_payload(),
        match=[
            matchers.header_matcher({API_KEY_HEADER: FAKE_KEY}),
            matchers.query_param_matcher({"vs_currency": "usd", "days": "365"}),
        ],
    )

    chart = client.get_daily_market_chart("bitcoin", days=365)

    request = mocked_api.calls[0].request
    assert "interval" not in request.url
    assert FAKE_KEY not in request.url
    assert chart.fetched_at == FIXED_NOW
    assert chart.prices[0].timestamp == datetime(2024, 1, 1, tzinfo=UTC)
    assert chart.market_caps[1].value == 0


@pytest.mark.parametrize("days", [90, 366])
def test_days_outside_daily_demo_range_rejected(client, days):
    with pytest.raises(ValueError, match="between 91 and 365"):
        client.get_daily_market_chart("bitcoin", days=days)


def test_invalid_coin_id_rejected(client):
    with pytest.raises(ValueError, match="coin id"):
        client.get_daily_market_chart("../bitcoin", days=120)


@pytest.mark.parametrize(
    "payload",
    [
        {"prices": []},
        [],
        {"prices": [[1, 2, 3]], "market_caps": [], "total_volumes": []},
        {"prices": [["x", 1.0]], "market_caps": [], "total_volumes": []},
        {"prices": [[JAN_1_MS, "abc"]], "market_caps": [], "total_volumes": []},
    ],
    ids=["missing-series", "wrong-type", "bad-pair", "bad-timestamp", "bad-value"],
)
def test_malformed_chart_responses(client, mocked_api, payload):
    mocked_api.get(CHART_URL, json=payload)
    with pytest.raises(ResponseSchemaError):
        client.get_daily_market_chart("bitcoin", days=120)


def test_chart_to_frame_outer_joins_with_nulls(client, mocked_api):
    mocked_api.get(CHART_URL, json=chart_payload())
    chart = client.get_daily_market_chart("bitcoin", days=120)

    frame = chart_to_frame(chart, asset=ASSET, quote_currency="USD")

    assert len(frame) == 3
    first = frame.iloc[0]
    assert first["price"] == 42000.5 and first["market_cap"] == 8.2e11
    assert pd.isna(first["volume_24h"])  # missing, not zero
    assert frame["quote_currency"].unique().tolist() == ["USD"]
    assert frame["provider"].unique().tolist() == ["coingecko"]
    assert pd.isna(frame.iloc[2]["market_cap"])


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 13, 21, 0, tzinfo=UTC), (date(2025, 10, 14), date(2026, 10, 13))),
        # Before 00:10 UTC today's point is not yet published.
        (datetime(2026, 10, 13, 0, 5, tzinfo=UTC), (date(2025, 10, 13), date(2026, 10, 12))),
    ],
)
def test_resolve_period(now, expected):
    assert resolve_period(365, now) == expected
