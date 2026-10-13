from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest

from cryptovision.formatting import MISSING, format_age, format_percent, format_usd, format_utc


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (103934.0714, "$103,934.07"),
        (1.0, "$1.00"),
        (0.999999, "$1.00"),
        (0.2280566, "$0.2281"),
        (0.00001234, "$0.00001234"),
        (0.0000000000001234, "$1.234e-13"),
        (0, "$0.00"),
        (-1234.5, "-$1,234.50"),
        (-0.00005, "-$0.00005000"),
        (None, MISSING),
        (math.nan, MISSING),
        (math.inf, MISSING),
    ],
)
def test_format_usd(value, expected):
    assert format_usd(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2_064_680_469_344.88, "$2.06T"),
        (48_899_343_771.25, "$48.90B"),
        (-5_000_000_000, "-$5.00B"),
        (999_999.999, "$1.00M"),
        (1_500, "$1.50K"),
        (999.99, "$999.99"),
        (0.5, "$0.5000"),
    ],
)
def test_format_usd_compact(value, expected):
    assert format_usd(value, compact=True) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.51878, "+1.52%"),
        (-0.93469, "-0.93%"),
        (-0.001, "0.00%"),
        (0, "0.00%"),
        (None, MISSING),
        (math.nan, MISSING),
    ],
)
def test_format_percent(value, expected):
    assert format_percent(value) == expected


def test_format_utc_converts_offsets():
    moment = datetime(2026, 10, 13, 9, 0, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert format_utc(moment) == "2026-10-13 12:00:00 UTC"
    assert format_utc(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01 00:00:00 UTC"
    assert format_utc(None) == MISSING
    # Naive datetimes are interpreted as UTC, never as local time.
    assert format_utc(datetime(2026, 10, 13, 12, 0, 0)) == "2026-10-13 12:00:00 UTC"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(-5, "just now"), (59, "just now"), (60, "1 min ago"), (899, "14 min ago"), (7300, "2 h ago")],
)
def test_format_age(seconds, expected):
    assert format_age(seconds) == expected
