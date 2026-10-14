from __future__ import annotations

import math

import pandas as pd
import pytest

from cryptovision.ui.charts import (
    bar_height,
    direction_symbol,
    market_cap_chart,
    price_change_chart,
)
from cryptovision.ui.theme import NEGATIVE_COLOR, NEUTRAL_LINE_COLOR, POSITIVE_COLOR


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["Bitcoin", "Ethereum", "Tether", "Tiny"],
            "market_cap": [1.2e12, 3.0e11, 1.5e11, math.nan],
            "change_24h_pct": [2.0, -1.5, 0.0, math.nan],
        }
    )


def test_market_cap_chart_horizontal_bars_with_labels(frame):
    figure = market_cap_chart(frame)

    (trace,) = figure.data
    assert trace.orientation == "h"
    assert list(trace.y) == ["Bitcoin", "Ethereum", "Tether", "Tiny"]
    assert list(trace.text) == ["$1.20T", "$300.00B", "$150.00B", "—"]
    assert figure.layout.yaxis.autorange == "reversed"  # largest at the top
    assert figure.layout.xaxis.title.text == "Market capitalization (USD)"
    assert figure.layout.xaxis.range[1] == pytest.approx(1.2e12 * 1.2)  # label headroom


def test_market_cap_chart_log_scale(frame):
    figure = market_cap_chart(frame, log_scale=True)
    assert figure.layout.xaxis.type == "log"
    assert figure.layout.xaxis.range is None


def test_chart_height_grows_with_assets():
    assert bar_height(5) == 320
    assert bar_height(50) == 24 * 50 + 90


def test_price_change_chart_sorted_labelled_and_drops_missing(frame):
    figure = price_change_chart(frame)

    (trace,) = figure.data
    assert list(trace.y) == ["Bitcoin", "Tether", "Ethereum"]  # descending, NaN dropped
    assert list(trace.text) == ["▲ +2.00%", "■ 0.00%", "▼ -1.50%"]
    assert list(trace.marker.color) == [POSITIVE_COLOR, NEUTRAL_LINE_COLOR, NEGATIVE_COLOR]
    assert figure.layout.xaxis.ticksuffix == "%"


def test_change_that_displays_as_zero_is_neutral():
    frame = pd.DataFrame({"name": ["Dai", "Ethereum"], "change_24h_pct": [-0.001, -1.0]})
    (trace,) = price_change_chart(frame).data
    assert list(trace.text) == ["■ 0.00%", "▼ -1.00%"]
    assert list(trace.marker.color) == [NEUTRAL_LINE_COLOR, NEGATIVE_COLOR]


@pytest.mark.parametrize(("value", "symbol"), [(0.5, "▲"), (-0.5, "▼"), (0.004, "■")])
def test_direction_symbol(value, symbol):
    assert direction_symbol(value) == symbol
