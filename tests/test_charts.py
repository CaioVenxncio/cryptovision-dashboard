from __future__ import annotations

import math

import pandas as pd
import pytest

from cryptovision.ui.charts import market_cap_chart, price_change_chart
from cryptovision.ui.theme import NEGATIVE_COLOR, POSITIVE_COLOR


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["Bitcoin", "Ethereum", "Tether", "Tiny"],
            "market_cap": [1.2e12, 3.0e11, 1.5e11, math.nan],
            "change_24h_pct": [2.0, -1.5, 0.0, math.nan],
        }
    )


def test_market_cap_chart_bars_and_hover_labels(frame):
    figure = market_cap_chart(frame)

    (trace,) = figure.data
    assert list(trace.x) == ["Bitcoin", "Ethereum", "Tether", "Tiny"]
    assert [row[0] for row in trace.customdata] == ["$1.20T", "$300.00B", "$150.00B", "—"]
    assert figure.layout.yaxis.type != "log"
    assert figure.layout.yaxis.title.text == "Market cap (USD)"


def test_market_cap_chart_log_scale(frame):
    assert market_cap_chart(frame, log_scale=True).layout.yaxis.type == "log"


def test_price_change_chart_sorted_colored_and_drops_missing(frame):
    figure = price_change_chart(frame)

    by_direction = {trace.name: trace for trace in figure.data}
    assert list(by_direction["Down"].x) == ["Ethereum"]
    assert list(by_direction["Up"].x) == ["Tether", "Bitcoin"]
    assert by_direction["Down"].marker.color == NEGATIVE_COLOR
    assert by_direction["Up"].marker.color == POSITIVE_COLOR
    assert list(figure.layout.xaxis.categoryarray) == ["Ethereum", "Tether", "Bitcoin"]
    assert [row[0] for row in by_direction["Up"].customdata] == ["0.00%", "+2.00%"]
    assert figure.layout.yaxis.ticksuffix == "%"


def test_change_that_displays_as_zero_is_not_red():
    frame = pd.DataFrame({"name": ["Dai", "Ethereum"], "change_24h_pct": [-0.001, -1.0]})

    by_direction = {trace.name: trace for trace in price_change_chart(frame).data}

    assert list(by_direction["Down"].x) == ["Ethereum"]
    assert list(by_direction["Up"].x) == ["Dai"]
    assert [row[0] for row in by_direction["Up"].customdata] == ["0.00%"]
