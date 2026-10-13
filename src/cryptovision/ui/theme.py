"""Shared visual constants for the Streamlit interface."""

from __future__ import annotations

APP_NAME = "CryptoVision"
PAGE_ICON = "📊"

POSITIVE_COLOR = "#1a7f37"
NEGATIVE_COLOR = "#cf222e"
ACCENT_COLOR = "#6200EE"
NEUTRAL_LINE_COLOR = "#888888"

CHART_HEIGHT = 450


# Percent changes are displayed with two decimals; colors follow the displayed value.
CHANGE_DISPLAY_DECIMALS = 2


def change_color_css(value: float) -> str:
    """CSS for a percent change: green when positive, red when negative.

    The sign is taken after rounding to the displayed precision, so a value
    shown as `0.00%` is never colored.
    """
    rounded = round(value, CHANGE_DISPLAY_DECIMALS)
    if rounded > 0:
        return f"color: {POSITIVE_COLOR}"
    if rounded < 0:
        return f"color: {NEGATIVE_COLOR}"
    return ""
