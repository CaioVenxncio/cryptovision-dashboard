"""Presentation-layer number and time formatting.

Use these only when rendering. Analysis and exports keep raw numeric values.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

MISSING = "—"

_COMPACT_UNITS = ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K"))
_SMALL_VALUE_SIGNIFICANT_DIGITS = 4
_MAX_DECIMALS = 12


def format_usd(value: float | None, *, compact: bool = False) -> str:
    """Format a USD amount.

    - `compact=True` abbreviates values of 1,000 or more (`$1.23B`).
    - Values of 1 or more use two decimals with thousands separators.
    - Values below 1 keep four significant digits (`$0.00001234`) so very
      small prices are not shown as `$0.00`.
    - Negative values place the sign before the currency symbol (`-$5.00`).
    """
    if value is None or not math.isfinite(value):
        return MISSING
    sign = "-" if value < 0 else ""
    magnitude = abs(value)

    if compact:
        # Units are ordered largest first. A value that rounds up to 1,000 of one
        # unit is promoted to the next unit (999,999.999 -> $1.00M, not $1,000.00K).
        for index, (threshold, suffix) in enumerate(_COMPACT_UNITS):
            if magnitude < threshold:
                continue
            scaled = magnitude / threshold
            if round(scaled, 2) >= 1000 and index > 0:
                larger_threshold, larger_suffix = _COMPACT_UNITS[index - 1]
                return f"{sign}${magnitude / larger_threshold:,.2f}{larger_suffix}"
            return f"{sign}${scaled:,.2f}{suffix}"

    if magnitude == 0:
        return "$0.00"
    if round(magnitude, 2) >= 1:
        return f"{sign}${magnitude:,.2f}"

    decimals = -math.floor(math.log10(magnitude)) + _SMALL_VALUE_SIGNIFICANT_DIGITS - 1
    if decimals > _MAX_DECIMALS:
        return f"{sign}${magnitude:.{_SMALL_VALUE_SIGNIFICANT_DIGITS - 1}e}"
    return f"{sign}${magnitude:.{max(2, decimals)}f}"


def format_percent(value: float | None, *, decimals: int = 2) -> str:
    """Format a value that is already in percent units, with an explicit sign."""
    if value is None or not math.isfinite(value):
        return MISSING
    if round(value, decimals) == 0:
        return f"{0:.{decimals}f}%"
    return f"{value:+.{decimals}f}%"


def format_utc(moment: datetime | None) -> str:
    """Format a timestamp in UTC, e.g. `2026-10-13 19:55:02 UTC`."""
    if moment is None:
        return MISSING
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_age(seconds: float) -> str:
    """Describe an elapsed duration, e.g. `just now`, `4 min ago`, `2 h ago`."""
    seconds = max(0.0, seconds)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    return f"{int(seconds // 3600)} h ago"
