"""Market Explorer figures. Pure functions: DataFrame in, figure out.

Horizontal bars keep every asset name readable at 50 assets; the chart grows
with the number of rows instead of squeezing labels. Direction is shown by
sign and symbol in the labels, not by color alone.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from cryptovision.formatting import format_percent, format_usd
from cryptovision.ui.theme import (
    CHANGE_DISPLAY_DECIMALS,
    DOWN_SYMBOL,
    FLAT_SYMBOL,
    NEGATIVE_COLOR,
    NEUTRAL_LINE_COLOR,
    POSITIVE_COLOR,
    SERIES_COLORS,
    UP_SYMBOL,
)

ROW_HEIGHT = 24
MIN_HEIGHT = 320


def bar_height(rows: int) -> int:
    return max(MIN_HEIGHT, ROW_HEIGHT * rows + 90)


def direction_symbol(value: float) -> str:
    rounded = round(value, CHANGE_DISPLAY_DECIMALS)
    return UP_SYMBOL if rounded > 0 else DOWN_SYMBOL if rounded < 0 else FLAT_SYMBOL


def market_cap_chart(frame: pd.DataFrame, *, log_scale: bool = False) -> go.Figure:
    """Market capitalization per asset, largest at the top."""
    labels = frame["market_cap"].map(lambda v: format_usd(v, compact=True))
    figure = go.Figure(
        go.Bar(
            x=frame["market_cap"],
            y=frame["name"],
            orientation="h",
            marker={"color": SERIES_COLORS[0]},
            text=labels,
            textposition="outside",
            cliponaxis=False,
            customdata=labels,
            hovertemplate="%{y}<br>Market cap: %{customdata}<extra></extra>",
        )
    )
    figure.update_layout(
        height=bar_height(len(frame)),
        xaxis={
            "title": "Market capitalization (USD)",
            "type": "log" if log_scale else "linear",
            # Headroom so the outside value label of the largest bar is not clipped.
            **({} if log_scale else {"range": [0, float(frame["market_cap"].max()) * 1.2]}),
            "tickprefix": "$",
            "exponentformat": "B",
        },
        yaxis={"autorange": "reversed", "title": None},
        bargap=0.25,
        showlegend=False,
    )
    return figure


def price_change_chart(frame: pd.DataFrame) -> go.Figure:
    """24h price change per asset, sorted, labelled with sign and direction symbol.

    Assets without a reported change are omitted (and named in the caption by
    the caller). A change shown as 0.00% is neutral.
    """
    data = frame.dropna(subset=["change_24h_pct"]).sort_values(
        "change_24h_pct", ascending=False, kind="stable"
    )
    rounded = data["change_24h_pct"].round(CHANGE_DISPLAY_DECIMALS)
    colors = [
        POSITIVE_COLOR if v > 0 else NEGATIVE_COLOR if v < 0 else NEUTRAL_LINE_COLOR
        for v in rounded
    ]
    labels = [f"{direction_symbol(v)} {format_percent(v)}" for v in data["change_24h_pct"]]
    figure = go.Figure(
        go.Bar(
            x=data["change_24h_pct"],
            y=data["name"],
            orientation="h",
            marker={"color": colors},
            text=labels,
            textposition="outside",
            cliponaxis=False,
            customdata=labels,
            hovertemplate="%{y}<br>24h change: %{customdata}<extra></extra>",
        )
    )
    figure.add_vline(x=0, line_width=1, line_color=NEUTRAL_LINE_COLOR)
    figure.update_layout(
        height=bar_height(len(data)),
        xaxis={"title": "24h price change (%)", "ticksuffix": "%"},
        yaxis={"autorange": "reversed", "title": None},
        bargap=0.25,
        showlegend=False,
    )
    return figure
