"""Binance Vision public spot kline archives.

Archive layout (https://github.com/binance/binance-public-data):
`data/spot/monthly/klines/{PAIR}/{interval}/{PAIR}-{interval}-{YYYY-MM}.zip`, each
with a `.CHECKSUM` file holding its SHA-256. Each zip holds one headerless CSV
with 12 columns. Spot timestamps are milliseconds before 2025-01-01 and
microseconds from then on, so the unit is detected per value.

Terms: CC BY-NC-SA 4.0; academic research is a permitted use (Binance Vision
terms §3.1, §4.1). Prices are Binance exchange prices in the pair's quote
asset (e.g. USDT), not aggregated USD prices.
"""

from __future__ import annotations

import csv
import io
import re
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from cryptovision.data.config import AssetSpec
from cryptovision.data.errors import (
    MissingSourceFileError,
    SourceFormatError,
    SourceIntegrityError,
)
from cryptovision.data.provenance import SourceFile
from cryptovision.data.schemas import DatasetKind, column_names
from cryptovision.data.storage import atomic_write_bytes, normalize_dtypes, sha256_bytes
from cryptovision.providers.errors import ProviderRequestError
from cryptovision.providers.http_client import HttpJsonClient, RetryPolicy

BASE_URL = "https://data.binance.vision"
ARCHIVE_TEMPLATE = "data/spot/monthly/klines/{pair}/{interval}/{pair}-{interval}-{month}.zip"
PROVIDER_ID = "binance_vision"
EXCHANGE = "binance"
ATTRIBUTION = "Market data: Binance Vision (https://data.binance.vision)."
LICENSE_NOTES = (
    "Binance Vision datasets are licensed under CC BY-NC-SA 4.0 with additional Binance "
    "Vision terms. Non-commercial academic research is permitted. Do not sell, sub-license "
    "or host the data. Derivative works must credit Binance Vision. "
    "See https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md"
)

_MIN_COLUMNS = 11
_MICROSECONDS_THRESHOLD = 10**15
_MILLISECONDS_THRESHOLD = 10**12
_CHECKSUM_PATTERN = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(\S+)\s*$")


def months_between(start: date, end: date) -> list[str]:
    """Calendar months touched by the inclusive period, as YYYY-MM strings."""
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def archive_path(pair: str, month: str, interval: str = "1d") -> str:
    return ARCHIVE_TEMPLATE.format(pair=pair, interval=interval, month=month)


def parse_checksum(text: str, expected_filename: str) -> str:
    """Extract the hex digest from a `sha256sum`-style CHECKSUM file."""
    match = _CHECKSUM_PATTERN.match(text.strip())
    if not match:
        raise SourceFormatError(f"Unreadable checksum file for {expected_filename}.")
    digest, filename = match.groups()
    if filename != expected_filename:
        raise SourceFormatError(f"Checksum file names {filename}, expected {expected_filename}.")
    return digest.lower()


def _timestamp(raw: str, label: str) -> datetime:
    try:
        value = int(raw)
    except ValueError:
        raise SourceFormatError(f"Non-integer {label}: {raw!r}") from None
    if value >= _MICROSECONDS_THRESHOLD:
        return datetime.fromtimestamp(value / 1_000_000, tz=UTC)
    if value >= _MILLISECONDS_THRESHOLD:
        return datetime.fromtimestamp(value / 1_000, tz=UTC)
    raise SourceFormatError(f"{label} {value} is neither milliseconds nor microseconds.")


def _number(raw: str, label: str) -> float:
    try:
        return float(raw)
    except ValueError:
        raise SourceFormatError(f"Non-numeric {label}: {raw!r}") from None


def parse_kline_archive(
    data: bytes, *, asset: AssetSpec, quote_currency: str, frequency: str = "1d"
) -> pd.DataFrame:
    """Parse one kline zip archive into normalized OHLCV rows."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise SourceFormatError(f"Expected one CSV in the archive, found {len(members)}.")
        text = archive.read(members[0]).decode("utf-8")
    except (zipfile.BadZipFile, EOFError, UnicodeDecodeError) as exc:
        raise SourceFormatError(f"Corrupt or incomplete archive ({exc}).") from None

    rows = []
    for line_number, record in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not record:
            continue
        if line_number == 1 and not record[0].strip().isdigit():
            continue  # optional header row
        if len(record) < _MIN_COLUMNS:
            raise SourceFormatError(
                f"Line {line_number} has {len(record)} columns, expected at least {_MIN_COLUMNS}."
            )
        rows.append(
            {
                "timestamp_utc": _timestamp(record[0], "open time"),
                "close_time_utc": _timestamp(record[6], "close time"),
                "asset_id": asset.asset_id,
                "symbol": asset.symbol,
                "pair": asset.pair,
                "exchange": EXCHANGE,
                "provider": PROVIDER_ID,
                "quote_currency": quote_currency,
                "frequency": frequency,
                "open": _number(record[1], "open"),
                "high": _number(record[2], "high"),
                "low": _number(record[3], "low"),
                "close": _number(record[4], "close"),
                "volume_base": _number(record[5], "volume"),
                "volume_quote": _number(record[7], "quote volume"),
                "trade_count": int(_number(record[8], "trade count")),
                "taker_buy_volume_base": _number(record[9], "taker buy base volume"),
                "taker_buy_volume_quote": _number(record[10], "taker buy quote volume"),
            }
        )
    if not rows:
        raise SourceFormatError("The archive contains no data rows.")
    frame = pd.DataFrame(rows, columns=column_names(DatasetKind.OHLCV))
    return normalize_dtypes(frame, DatasetKind.OHLCV)


class BinanceVisionSource:
    """Downloads and verifies monthly kline archives, caching them under `raw_dir`.

    Verified archives are reused on later runs, so rebuilding a dataset needs no
    network access once its raw files exist.
    """

    def __init__(
        self,
        raw_dir: Path,
        *,
        http: HttpJsonClient | None = None,
        request_interval_seconds: float = 0.2,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._raw_dir = raw_dir
        self._http = http or HttpJsonClient(
            BASE_URL,
            headers={"User-Agent": "CryptoVision research pipeline"},
            timeout_seconds=30,
            retry_policy=RetryPolicy(max_retries=3),
        )
        self._interval = request_interval_seconds
        self._sleep = sleep
        self._clock = clock

    def local_path(self, relative: str) -> Path:
        return self._raw_dir / PROVIDER_ID / relative

    def fetch_archive(self, pair: str, month: str, *, offline: bool) -> tuple[bytes, SourceFile]:
        relative = archive_path(pair, month)
        filename = relative.rsplit("/", 1)[-1]
        url = f"{BASE_URL}/{relative}"
        zip_path = self.local_path(relative)
        checksum_path = zip_path.with_name(f"{filename}.CHECKSUM")

        if zip_path.exists() and checksum_path.exists():
            data = zip_path.read_bytes()
            expected = parse_checksum(checksum_path.read_text(encoding="utf-8"), filename)
            if sha256_bytes(data) == expected:
                return data, self._record(url, zip_path, data, reused=True)
            if offline:
                raise SourceIntegrityError(f"Local copy of {filename} fails its checksum.")
        elif offline:
            raise MissingSourceFileError(f"{filename} is not available locally (offline mode).")

        try:
            data = self._http.get_bytes(relative)
            self._sleep(self._interval)
            checksum_bytes = self._http.get_bytes(f"{relative}.CHECKSUM")
            self._sleep(self._interval)
        except ProviderRequestError as exc:
            if exc.status_code == 404:
                raise MissingSourceFileError(f"{filename} is not published by Binance.") from None
            raise
        checksum_text = checksum_bytes.decode("utf-8", errors="replace")
        expected = parse_checksum(checksum_text, filename)
        if sha256_bytes(data) != expected:
            raise SourceIntegrityError(f"{filename} does not match its published SHA-256.")
        atomic_write_bytes(zip_path, data)
        atomic_write_bytes(checksum_path, checksum_bytes)
        return data, self._record(url, zip_path, data, reused=False)

    def _record(self, url: str, path: Path, data: bytes, *, reused: bool) -> SourceFile:
        return SourceFile(
            url=url,
            local_path=path.relative_to(self._raw_dir.parent).as_posix(),
            sha256=sha256_bytes(data),
            size_bytes=len(data),
            checksum_verified=True,
            retrieved_at=self._clock(),
            reused_local_copy=reused,
        )
