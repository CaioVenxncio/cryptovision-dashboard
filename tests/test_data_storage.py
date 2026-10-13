from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from cryptovision.data import storage
from cryptovision.data.schemas import DatasetKind
from cryptovision.data.storage import (
    atomic_write_bytes,
    content_sha256,
    read_parquet,
    sha256_file,
    write_parquet,
)
from cryptovision.data.synthetic import generate_synthetic_ohlcv

KIND = DatasetKind.OHLCV


@pytest.fixture
def frame() -> pd.DataFrame:
    return generate_synthetic_ohlcv(start=date(2024, 1, 1), days=10, seed=3)


def test_parquet_round_trip_preserves_values_and_types(frame, tmp_path):
    path = tmp_path / "data.parquet"
    write_parquet(frame, KIND, path)

    loaded = read_parquet(path, KIND)

    assert str(loaded["timestamp_utc"].dtype) == "datetime64[us, UTC]"
    assert str(loaded["trade_count"].dtype) == "Int64"
    assert loaded["close"].dtype == "float64"
    assert content_sha256(loaded, KIND) == content_sha256(frame, KIND)
    expected = frame.sort_values(["asset_id", "timestamp_utc"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(loaded, expected, check_dtype=False)


def test_written_rows_are_deterministically_ordered(frame, tmp_path):
    write_parquet(frame.sample(frac=1, random_state=0), KIND, tmp_path / "a.parquet")
    write_parquet(frame, KIND, tmp_path / "b.parquet")
    assert sha256_file(tmp_path / "a.parquet") == sha256_file(tmp_path / "b.parquet")


def test_nulls_survive_round_trip(frame, tmp_path):
    frame.loc[0, "volume_base"] = None
    frame.loc[1, "trade_count"] = pd.NA
    write_parquet(frame, KIND, tmp_path / "d.parquet")
    loaded = read_parquet(tmp_path / "d.parquet", KIND)
    assert loaded["volume_base"].isna().sum() == 1
    assert loaded["trade_count"].isna().sum() == 1
    assert content_sha256(loaded, KIND) == content_sha256(frame, KIND)


def test_content_hash_ignores_row_order_but_detects_value_changes(frame):
    baseline = content_sha256(frame, KIND)
    assert content_sha256(frame.iloc[::-1], KIND) == baseline
    changed = frame.copy()
    changed.loc[0, "close"] = changed.loc[0, "close"] + 1e-9
    assert content_sha256(changed, KIND) != baseline


def test_reading_wrong_schema_fails(frame, tmp_path):
    path = tmp_path / "x.parquet"
    frame.drop(columns=["close"]).to_parquet(path)
    with pytest.raises(ValueError, match="schema"):
        read_parquet(path, KIND)


def test_atomic_write_keeps_previous_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "file.bin"
    atomic_write_bytes(path, b"original")

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(storage.os, "replace", failing_replace)
    with pytest.raises(OSError, match="disk full"):
        atomic_write_bytes(path, b"new content")

    assert path.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["file.bin"]


def test_atomic_write_creates_parent_directories(tmp_path):
    path = tmp_path / "a" / "b" / "c.bin"
    atomic_write_bytes(path, b"x")
    assert path.read_bytes() == b"x"
    assert os.listdir(path.parent) == ["c.bin"]
