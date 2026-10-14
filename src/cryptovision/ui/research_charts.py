"""Plotly figures for the Research Lab. Inputs are loaded result artifacts, never raw data."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from cryptovision.ui.theme import CHART_HEIGHT, SERIES_COLORS, TOKENS

HIGH_SHADE = "rgba(251, 191, 36, 0.14)"  # warning token, translucent


def regime_chart(regimes: pd.DataFrame) -> go.Figure:
    """Volatility proxy with its threshold; high-regime days shaded and named in the legend."""
    figure = go.Figure()
    high = regimes["regime"] == "high"
    figure.add_trace(
        go.Bar(
            x=regimes["date"],
            y=np.where(high, regimes["proxy"].max() * 1.05, np.nan),
            marker={"color": HIGH_SHADE, "line": {"width": 0}},
            name="High-volatility regime (shaded)",
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
            line={"color": SERIES_COLORS[0], "width": 1.4},
            hovertemplate="%{x|%Y-%m-%d}: %{y:.4f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=regimes["date"],
            y=regimes["threshold"],
            mode="lines",
            name="Threshold",
            line={"color": TOKENS.text_muted, "dash": "dash", "width": 1},
            hovertemplate="threshold %{y:.4f}<extra></extra>",
        )
    )
    figure.update_layout(height=CHART_HEIGHT, bargap=0, yaxis_title="Daily volatility (fraction)")
    return figure


def interval_chart(
    analyses: list[dict[str, Any]], *, show_intervals: bool = False, validated: bool = False
) -> go.Figure:
    """Point estimates per analysis; bootstrap intervals only on request.

    When the method is not validated, intervals are drawn dotted and named
    "diagnostic (unvalidated)" so they cannot be read as confidence intervals.
    """
    labels = [f"{a['id']}: {a['label']}" for a in analyses]
    deltas = [a["delta"] for a in analyses]
    is_primary = [a["id"] == "primary" for a in analyses]
    marker = {
        "color": [TOKENS.accent if p else TOKENS.text_muted for p in is_primary],
        "size": [12 if p else 9 for p in is_primary],
        "symbol": ["diamond" if p else "circle" for p in is_primary],
    }
    error_x = None
    if show_intervals:
        error_x = {
            "type": "data",
            "symmetric": False,
            "array": [a["ci_high"] - a["delta"] for a in analyses],
            "arrayminus": [a["delta"] - a["ci_low"] for a in analyses],
            "color": TOKENS.text_muted if validated else TOKENS.warning,
            "thickness": 1 if validated else 1.2,
            "width": 4,
        }
    interval_name = "95% interval" if validated else "diagnostic interval (unvalidated)"
    figure = go.Figure(
        go.Scatter(
            x=deltas,
            y=labels,
            mode="markers",
            marker=marker,
            error_x=error_x,
            name="Point estimate",
            customdata=[[a["ci_low"], a["ci_high"]] for a in analyses],
            hovertemplate="%{y}<br>Δ = %{x:+.4f}"
            + (
                f"<br>{interval_name}: [%{{customdata[0]:+.4f}}, %{{customdata[1]:+.4f}}]"
                if show_intervals
                else ""
            )
            + "<extra></extra>",
        )
    )
    figure.add_vline(x=0, line_width=1, line_color=TOKENS.text_muted, line_dash="dot")
    figure.update_layout(
        height=max(240, 38 * len(analyses) + 110),
        xaxis_title="Δ = average correlation (high) − average correlation (low)",
        yaxis={"autorange": "reversed"},
        showlegend=False,
    )
    return figure


def pair_comparison_chart(pairs: list[dict[str, Any]]) -> go.Figure:
    """Pairwise correlation in each regime, sorted by the difference (shape + color coded)."""
    ordered = sorted(pairs, key=lambda p: p["difference"])
    labels = [f"{p['asset_a']} / {p['asset_b']}" for p in ordered]
    figure = go.Figure()
    for name, key, color, symbol in (
        ("Low-volatility regime", "low", SERIES_COLORS[0], "circle"),
        ("High-volatility regime", "high", SERIES_COLORS[1], "diamond"),
    ):
        figure.add_trace(
            go.Scatter(
                x=[p[key] for p in ordered],
                y=labels,
                mode="markers",
                name=name,
                marker={"color": color, "size": 8, "symbol": symbol},
                hovertemplate="%{y}<br>" + name + ": r = %{x:.3f}<extra></extra>",
            )
        )
    figure.update_layout(
        height=max(220, 26 * len(ordered) + 130),
        xaxis_title="Pearson correlation of daily returns",
    )
    return figure
