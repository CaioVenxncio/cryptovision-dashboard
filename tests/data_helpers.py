"""Builders for synthetic provider files used by the data pipeline tests.

Every value here is synthetic. Nothing is real market data.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, date, datetime, timedelta

MS = 1_000
US = 1_000_000


def kline_rows(
    start: date, days: int, *, unit: int = MS, base_price: float = 100.0
) -> list[list[str]]:
    """Synthetic Binance-style 12-column kline rows, one per day."""
    rows = []
    for offset in range(days):
        opened = datetime.combine(start + timedelta(days=offset), datetime.min.time(), UTC)
        tick = timedelta(milliseconds=1) if unit == MS else timedelta(microseconds=1)
        closed = opened + timedelta(days=1) - tick
        price = base_price + offset
        rows.append(
            [
                str(round(opened.timestamp() * unit)),
                f"{price:.2f}",
                f"{price + 2:.2f}",
                f"{price - 2:.2f}",
                f"{price + 1:.2f}",
                "10.5",
                str(round(closed.timestamp() * unit)),
                f"{10.5 * (price + 1):.4f}",
                "42",
                "5.25",
                f"{5.25 * (price + 1):.4f}",
                "0",
            ]
        )
    return rows


def kline_zip(rows: list[list[str]], *, name: str, header: bool = False) -> bytes:
    lines = []
    if header:
        lines.append(
            "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
            "taker_buy_volume,taker_buy_quote_volume,ignore"
        )
    lines.extend(",".join(row) for row in rows)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "\n".join(lines) + "\n")
    return buffer.getvalue()


def checksum_text(data: bytes, filename: str) -> str:
    return f"{hashlib.sha256(data).hexdigest()}  {filename}\n"


def month_days(month: str) -> tuple[date, int]:
    year, number = (int(part) for part in month.split("-"))
    first = date(year, number, 1)
    following = date(year + (number == 12), number % 12 + 1, 1)
    return first, (following - first).days
