from __future__ import annotations

import zipfile
from datetime import UTC, date, datetime
from io import BytesIO

import pytest

from cryptovision.data.config import AssetSpec
from cryptovision.data.errors import (
    MissingSourceFileError,
    SourceFormatError,
    SourceIntegrityError,
)
from cryptovision.data.sources.binance import (
    BASE_URL,
    BinanceVisionSource,
    archive_path,
    months_between,
    parse_checksum,
    parse_kline_archive,
)
from cryptovision.providers.http_client import HttpJsonClient, RetryPolicy
from tests.data_helpers import MS, US, checksum_text, kline_rows, kline_zip

ASSET = AssetSpec(asset_id="bitcoin", symbol="BTC", pair="BTCUSDT")
NAME = "BTCUSDT-1d-2024-01"
VALID_ROW = kline_rows(date(2024, 1, 1), 1)[0]
RELATIVE = archive_path("BTCUSDT", "2024-01")


def parse(data: bytes):
    return parse_kline_archive(data, asset=ASSET, quote_currency="USDT")


def test_months_between_spans_year_boundary():
    assert months_between(date(2024, 11, 15), date(2025, 2, 1)) == [
        "2024-11",
        "2024-12",
        "2025-01",
        "2025-02",
    ]
    assert months_between(date(2024, 1, 1), date(2024, 1, 31)) == ["2024-01"]


def test_archive_path_template():
    assert RELATIVE == "data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-01.zip"


def test_parse_checksum():
    digest = "a" * 64
    assert parse_checksum(f"{digest}  {NAME}.zip\n", f"{NAME}.zip") == digest
    assert parse_checksum(f"{digest.upper()} *{NAME}.zip", f"{NAME}.zip") == digest
    with pytest.raises(SourceFormatError, match="names"):
        parse_checksum(f"{digest}  other.zip", f"{NAME}.zip")
    with pytest.raises(SourceFormatError, match="Unreadable"):
        parse_checksum("not a checksum", f"{NAME}.zip")


@pytest.mark.parametrize("unit", [MS, US], ids=["milliseconds", "microseconds"])
def test_parse_detects_timestamp_unit(unit):
    frame = parse(kline_zip(kline_rows(date(2024, 12, 31), 2, unit=unit), name=f"{NAME}.csv"))

    assert frame["timestamp_utc"].tolist() == [
        datetime(2024, 12, 31, tzinfo=UTC),
        datetime(2025, 1, 1, tzinfo=UTC),
    ]
    assert frame["close_time_utc"].iloc[0].strftime("%H:%M:%S") == "23:59:59"
    assert str(frame["timestamp_utc"].dtype) == "datetime64[us, UTC]"


def test_parse_maps_columns_without_conversion():
    frame = parse(kline_zip(kline_rows(date(2024, 1, 1), 1), name=f"{NAME}.csv"))
    row = frame.iloc[0]

    assert (row["open"], row["high"], row["low"], row["close"]) == (100.0, 102.0, 98.0, 101.0)
    assert row["volume_base"] == 10.5  # base-asset units
    assert row["volume_quote"] == pytest.approx(10.5 * 101)  # USDT, not USD
    assert row["trade_count"] == 42
    assert row["quote_currency"] == "USDT"
    assert row["exchange"] == "binance"
    assert row["pair"] == "BTCUSDT"


def test_parse_skips_optional_header():
    frame = parse(kline_zip(kline_rows(date(2024, 1, 1), 3), name=f"{NAME}.csv", header=True))
    assert len(frame) == 3


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"PK\x03\x04truncated", "Corrupt or incomplete"),
        (kline_zip([["1704067200000", "1", "2"]], name="a.csv"), "columns"),
        (kline_zip([[*VALID_ROW[:1], "x", *VALID_ROW[2:]]], name="a.csv"), "Non-numeric open"),
        (kline_zip([["17040", *["1"] * 11]], name="a.csv"), "neither milliseconds"),
        (kline_zip([VALID_ROW, ["abc", *VALID_ROW[1:]]], name="a.csv"), "Non-integer"),
        (kline_zip([], name="a.csv", header=True), "no data rows"),
    ],
    ids=["truncated", "short-row", "bad-number", "bad-unit", "bad-timestamp", "header-only"],
)
def test_parse_rejects_malformed_archives(data, message):
    with pytest.raises(SourceFormatError, match=message):
        parse(data)


def test_parse_requires_exactly_one_csv():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.csv", "")
        archive.writestr("b.csv", "")
    with pytest.raises(SourceFormatError, match="one CSV"):
        parse(buffer.getvalue())


def test_partially_written_archive_is_detected():
    data = kline_zip(kline_rows(date(2024, 1, 1), 31), name=f"{NAME}.csv")
    with pytest.raises(SourceFormatError):
        parse(data[: len(data) // 2])


# --- Download, checksum verification and local reuse ----------------------------------


@pytest.fixture
def source(tmp_path):
    http = HttpJsonClient(
        BASE_URL,
        headers={},
        timeout_seconds=5,
        retry_policy=RetryPolicy(max_retries=0),
        sleep=lambda _: None,
    )
    return BinanceVisionSource(tmp_path / "raw", http=http, sleep=lambda _: None)


@pytest.fixture
def archive() -> bytes:
    return kline_zip(kline_rows(date(2024, 1, 1), 31), name=f"{NAME}.csv")


def register(mocked_api, data: bytes, checksum: str) -> None:
    mocked_api.get(f"{BASE_URL}/{RELATIVE}", body=data)
    mocked_api.get(f"{BASE_URL}/{RELATIVE}.CHECKSUM", body=checksum)


def test_download_verifies_and_stores_atomically(source, archive, mocked_api, tmp_path):
    register(mocked_api, archive, checksum_text(archive, f"{NAME}.zip"))

    data, record = source.fetch_archive("BTCUSDT", "2024-01", offline=False)

    assert data == archive
    assert record.checksum_verified and not record.reused_local_copy
    assert record.url == f"{BASE_URL}/{RELATIVE}"
    assert record.local_path == f"raw/binance_vision/{RELATIVE}"
    stored = tmp_path / "raw" / "binance_vision" / RELATIVE
    assert stored.read_bytes() == archive
    assert not list(stored.parent.glob("*.tmp"))


def test_verified_local_copy_is_reused_without_network(source, archive, mocked_api):
    register(mocked_api, archive, checksum_text(archive, f"{NAME}.zip"))
    source.fetch_archive("BTCUSDT", "2024-01", offline=False)
    calls = len(mocked_api.calls)

    _, record = source.fetch_archive("BTCUSDT", "2024-01", offline=True)

    assert record.reused_local_copy
    assert len(mocked_api.calls) == calls


def test_checksum_mismatch_is_rejected_and_not_stored(source, archive, mocked_api, tmp_path):
    register(mocked_api, archive, f"{'0' * 64}  {NAME}.zip")

    with pytest.raises(SourceIntegrityError):
        source.fetch_archive("BTCUSDT", "2024-01", offline=False)

    assert not (tmp_path / "raw" / "binance_vision" / RELATIVE).exists()


def test_corrupted_local_copy_is_redownloaded(source, archive, mocked_api, tmp_path):
    register(mocked_api, archive, checksum_text(archive, f"{NAME}.zip"))
    source.fetch_archive("BTCUSDT", "2024-01", offline=False)
    stored = tmp_path / "raw" / "binance_vision" / RELATIVE
    stored.write_bytes(b"corrupted")

    with pytest.raises(SourceIntegrityError, match="fails its checksum"):
        source.fetch_archive("BTCUSDT", "2024-01", offline=True)
    data, record = source.fetch_archive("BTCUSDT", "2024-01", offline=False)

    assert data == archive and not record.reused_local_copy
    assert stored.read_bytes() == archive


def test_offline_without_local_copy(source, mocked_api):
    with pytest.raises(MissingSourceFileError, match="offline"):
        source.fetch_archive("BTCUSDT", "2024-01", offline=True)
    assert len(mocked_api.calls) == 0


def test_unpublished_month_is_reported_as_missing(source, mocked_api):
    mocked_api.get(f"{BASE_URL}/{RELATIVE}", status=404)

    with pytest.raises(MissingSourceFileError, match="not published"):
        source.fetch_archive("BTCUSDT", "2024-01", offline=False)


def test_oversized_archives_and_members_are_rejected(monkeypatch):
    from cryptovision.data.sources import binance

    data = kline_zip(kline_rows(date(2024, 1, 1), 2), name=f"{NAME}.csv")
    monkeypatch.setattr(binance, "MAX_UNCOMPRESSED_BYTES", 10)
    with pytest.raises(SourceFormatError, match="expands to"):
        parse(data)
    monkeypatch.setattr(binance, "MAX_ARCHIVE_BYTES", 10)
    with pytest.raises(SourceFormatError, match="larger than"):
        parse(data)


def test_download_size_limit(mocked_api):
    from cryptovision.providers.errors import ResponseSchemaError

    http = HttpJsonClient(
        BASE_URL, headers={}, timeout_seconds=5, retry_policy=RetryPolicy(max_retries=0)
    )
    mocked_api.get(f"{BASE_URL}/big", body=b"x" * 100)
    with pytest.raises(ResponseSchemaError, match="exceeds 50 bytes"):
        http.get_bytes("big", max_bytes=50)
    assert http.get_bytes("big", max_bytes=1000) == b"x" * 100
