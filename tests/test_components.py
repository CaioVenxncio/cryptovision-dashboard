from __future__ import annotations

import pytest

from cryptovision.market import snapshot_to_frame
from cryptovision.models import MarketCoin, MarketSnapshot
from cryptovision.ui.components import TABLE_COLUMNS, build_market_table
from cryptovision.ui.theme import NEGATIVE_COLOR, POSITIVE_COLOR, change_color_css
from tests.conftest import FIXED_NOW, load_fixture


@pytest.fixture
def frame():
    coins = tuple(MarketCoin.model_validate(c) for c in load_fixture("coins_markets.json"))
    snapshot = MarketSnapshot(
        provider="CoinGecko",
        endpoint="/coins/markets",
        vs_currency="usd",
        fetched_at=FIXED_NOW,
        coins=coins,
    )
    return snapshot_to_frame(snapshot)


def test_market_table_formats_display_but_keeps_numeric_data(frame):
    styler = build_market_table(frame)

    assert list(styler.data.columns) == TABLE_COLUMNS
    assert styler.data["price"].dtype == "float64"
    html = styler.to_html()
    assert "$60,000.50" in html
    assert "$0.00001234" in html
    assert "+2.00%" in html
    assert "$1.20T" in html


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.0, f"color: {POSITIVE_COLOR}"),
        (-0.1, f"color: {NEGATIVE_COLOR}"),
        (0.0, ""),
        (-0.001, ""),
        (0.004, ""),
        (0.005, f"color: {POSITIVE_COLOR}"),
        (float("nan"), ""),
    ],
)
def test_change_color_css(value, expected):
    assert change_color_css(value) == expected
