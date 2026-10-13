"""Plotly figures for historical analytics. Pure functions: results in, figures out."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from cryptovision.analytics.correlation import CorrelationResult
from cryptovision.analytics.drawdown import drawdown_series
from cryptovision.analytics.volatility import RollingResult
from cryptovision.ui.theme import CHART_HEIGHT, NEGATIVE_COLOR

SERIES_COLORS = (
    "#6200EE",
    "#1F77B4",
    "#FF7F0E",
    "#2CA02C",
    "#D62728",
    "#9467BD",
    "#8C564B",
    "#E377C2",
    "#17BECF",
)


def _layout(figure: go.Figure, *, yaxis_title: str, **extra: object) -> go.Figure:
    figure.update_layout(
        height=CHART_HEIGHT,
        xaxis_title=None,
        yaxis_title=yaxis_title,
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.15},
        margin={"t": 30},
        **extra,
    )
    return figure


def _line(figure: go.Figure, series: pd.Series, name: str, index: int, fmt: str) -> None:
    figure.add_trace(
        go.Scatter(
            x=series.index,
            y=series.to_numpy(),
            mode="lines",
            name=name,
            line={"color": SERIES_COLORS[index % len(SERIES_COLORS)], "width": 1.6},
            hovertemplate=f"{name}: %{{y:{fmt}}}<extra></extra>",
            connectgaps=False,  # gaps stay visible
        )
    )


def price_chart(prices: pd.DataFrame, *, quote_currency: str) -> go.Figure:
    """Close prices on a log scale, so assets with different price levels are comparable."""
    figure = go.Figure()
    for index, asset in enumerate(prices.columns):
        _line(figure, prices[asset], asset, index, ",.4~f")
    return _layout(
        figure, yaxis_title=f"Close price ({quote_currency}, log scale)", yaxis_type="log"
    )


def rolling_volatility_chart(result: RollingResult) -> go.Figure:
    figure = go.Figure()
    for index, asset in enumerate(result.values.columns):
        _line(figure, result.values[asset], asset, index, ".1%")
    annualized = result.metadata.annualization_factor is not None
    label = "Annualized volatility" if annualized else "Daily volatility"
    return _layout(
        figure,
        yaxis_title=f"{label} ({result.metadata.window}-day window)",
        yaxis_tickformat=".0%",
    )


def drawdown_chart(prices: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    for index, asset in enumerate(prices.columns):
        if prices[asset].notna().sum() < 1:
            continue
        _line(figure, drawdown_series(prices[asset]), asset, index, ".1%")
    figure.add_hline(y=0, line_width=1, line_color="#888888")
    return _layout(figure, yaxis_title="Drawdown from running peak", yaxis_tickformat=".0%")


def correlation_heatmap(result: CorrelationResult) -> go.Figure:
    matrix = result.matrix
    labels = list(matrix.columns)
    text = [
        ["n/a" if np.isnan(value) else f"{value:.2f}" for value in row] for row in matrix.to_numpy()
    ]
    figure = go.Figure(
        go.Heatmap(
            z=matrix.to_numpy(),
            x=labels,
            y=labels,
            zmin=-1,
            zmax=1,
            colorscale="RdBu",
            reversescale=True,
            text=text,
            texttemplate="%{text}",
            customdata=result.counts.to_numpy(),
            hovertemplate="%{y} / %{x}<br>r = %{text}<br>n = %{customdata}<extra></extra>",
            colorbar={"title": "r"},
        )
    )
    figure.update_layout(height=max(CHART_HEIGHT, 60 * len(labels)), margin={"t": 30})
    figure.update_yaxes(autorange="reversed")
    return figure


def rolling_correlation_chart(result: RollingResult) -> go.Figure:
    figure = go.Figure()
    column = result.values.columns[0]
    _line(figure, result.values[column], column.replace("|", " / "), 0, ".2f")
    figure.add_hline(y=0, line_width=1, line_color=NEGATIVE_COLOR, line_dash="dot")
    return _layout(
        figure,
        yaxis_title=f"{result.metadata.method} correlation ({result.metadata.window}-day window)",
        yaxis_range=[-1, 1],
    )
