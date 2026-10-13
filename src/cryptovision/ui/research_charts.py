"""Plotly figures for the Research Lab. Inputs are loaded result artifacts, never raw data."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from cryptovision.ui.theme import ACCENT_COLOR, CHART_HEIGHT, NEGATIVE_COLOR, POSITIVE_COLOR

HIGH_COLOR = "rgba(207, 34, 46, 0.12)"


def regime_chart(regimes: pd.DataFrame) -> go.Figure:
    """Volatility proxy with its threshold; high-regime days shaded."""
    figure = go.Figure()
    high = regimes["regime"] == "high"
    figure.add_trace(
        go.Bar(
            x=regimes["date"],
            y=np.where(high, regimes["proxy"].max() * 1.05, np.nan),
            marker={"color": HIGH_COLOR, "line": {"width": 0}},
            name="High-volatility regime",
            hoverinfo="skip",
            width=86_400_000,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=regimes["date"],
            y=regimes["proxy"],
            mode="lines",
            name="Volatility proxy (mean lagged 30-day)",
            line={"color": ACCENT_COLOR, "width": 1.4},
            hovertemplate="%{x|%Y-%m-%d}: %{y:.4f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=regimes["date"],
            y=regimes["threshold"],
            mode="lines",
            name="Threshold",
            line={"color": "#888888", "dash": "dash", "width": 1},
            hovertemplate="threshold %{y:.4f}<extra></extra>",
        )
    )
    figure.update_layout(
        height=CHART_HEIGHT,
        bargap=0,
        yaxis_title="Daily volatility (fraction)",
        legend={"orientation": "h", "y": -0.15},
        margin={"t": 30},
    )
    return figure


def interval_chart(analyses: list[dict[str, Any]]) -> go.Figure:
    """Point estimates with 95% intervals (forest plot), primary first."""
    labels = [f"{a['id']}: {a['label']}" for a in analyses]
    deltas = [a["delta"] for a in analyses]
    colors = [ACCENT_COLOR if a["id"] == "primary" else "#555555" for a in analyses]
    figure = go.Figure(
        go.Scatter(
            x=deltas,
            y=labels,
            mode="markers",
            marker={"color": colors, "size": 10},
            error_x={
                "type": "data",
                "symmetric": False,
                "array": [a["ci_high"] - a["delta"] for a in analyses],
                "arrayminus": [a["delta"] - a["ci_low"] for a in analyses],
                "color": "#888888",
            },
            customdata=[[a["ci_low"], a["ci_high"]] for a in analyses],
            hovertemplate="%{y}<br>Δ = %{x:+.4f}<br>95%: [%{customdata[0]:+.4f}, "
            "%{customdata[1]:+.4f}]<extra></extra>",
        )
    )
    figure.add_vline(x=0, line_width=1, line_color=NEGATIVE_COLOR, line_dash="dot")
    figure.update_layout(
        height=max(CHART_HEIGHT, 34 * len(analyses) + 80),
        xaxis_title="Δ = average correlation (high) − average correlation (low)",
        yaxis={"autorange": "reversed"},
        margin={"t": 30, "l": 10},
    )
    return figure


def pair_comparison_chart(pairs: list[dict[str, Any]]) -> go.Figure:
    """Pairwise correlation in each regime, sorted by the difference."""
    ordered = sorted(pairs, key=lambda p: p["difference"])
    labels = [f"{p['asset_a']} / {p['asset_b']}" for p in ordered]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[p["low"] for p in ordered],
            y=labels,
            mode="markers",
            name="Low-volatility regime",
            marker={"color": POSITIVE_COLOR, "size": 8},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[p["high"] for p in ordered],
            y=labels,
            mode="markers",
            name="High-volatility regime",
            marker={"color": NEGATIVE_COLOR, "size": 8},
        )
    )
    figure.update_layout(
        height=max(CHART_HEIGHT, 18 * len(ordered) + 100),
        xaxis_title="Pearson correlation of daily returns",
        legend={"orientation": "h", "y": -0.08},
        margin={"t": 30},
    )
    return figure
