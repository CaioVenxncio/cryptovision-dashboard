"""Plotly figure builders. Pure functions: DataFrame in, figure out."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from cryptovision.formatting import format_percent, format_usd
from cryptovision.ui.theme import (
    ACCENT_COLOR,
    CHANGE_DISPLAY_DECIMALS,
    CHART_HEIGHT,
    NEGATIVE_COLOR,
    NEUTRAL_LINE_COLOR,
    POSITIVE_COLOR,
)


def market_cap_chart(frame: pd.DataFrame, *, log_scale: bool = False) -> go.Figure:
    """Bar chart of market capitalization per asset, in the frame's order."""
    data = frame.assign(
        market_cap_label=frame["market_cap"].map(lambda v: format_usd(v, compact=True))
    )
    figure = px.bar(
        data,
        x="name",
        y="market_cap",
        custom_data=["market_cap_label"],
        log_y=log_scale,
        color_discrete_sequence=[ACCENT_COLOR],
    )
    figure.update_traces(hovertemplate="%{x}<br>Market cap: %{customdata[0]}<extra></extra>")
    figure.update_layout(
        xaxis_title=None,
        yaxis_title="Market cap (USD)",
        yaxis_tickprefix="$",
        yaxis_exponentformat="B",
        height=CHART_HEIGHT,
    )
    return figure


def price_change_chart(frame: pd.DataFrame) -> go.Figure:
    """Bar chart of 24h price change, sorted ascending and colored by sign.

    The sign uses the displayed precision, so a change shown as 0.00% is never
    red. Assets without a reported change are omitted.
    """
    data = (
        frame.dropna(subset=["change_24h_pct"])
        .sort_values("change_24h_pct", kind="stable")
        .assign(
            change_label=lambda df: df["change_24h_pct"].map(format_percent),
            direction=lambda df: df["change_24h_pct"].map(
                lambda v: "Down" if round(v, CHANGE_DISPLAY_DECIMALS) < 0 else "Up"
            ),
        )
    )
    figure = px.bar(
        data,
        x="name",
        y="change_24h_pct",
        color="direction",
        custom_data=["change_label"],
        color_discrete_map={"Up": POSITIVE_COLOR, "Down": NEGATIVE_COLOR},
        category_orders={"name": data["name"].tolist()},
    )
    figure.update_traces(hovertemplate="%{x}<br>24h change: %{customdata[0]}<extra></extra>")
    figure.update_layout(
        xaxis_title=None,
        yaxis_title="24h price change (%)",
        yaxis_ticksuffix="%",
        showlegend=False,
        height=CHART_HEIGHT,
    )
    figure.add_hline(y=0, line_width=1, line_color=NEUTRAL_LINE_COLOR)
    return figure
