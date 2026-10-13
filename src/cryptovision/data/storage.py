"""Parquet storage, atomic file writes and content hashing."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import os
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from cryptovision.data.schemas import SCHEMAS, SORT_KEYS, DatasetKind

PARQUET_COMPRESSION = "zstd"
_HASH_CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via a temporary file in the same directory, then rename into place.

    A crash leaves either the previous file or no file, never a partial one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def to_table(frame: pd.DataFrame, kind: DatasetKind) -> pa.Table:
    """Convert a normalized frame to an Arrow table with the canonical schema and order."""
    schema = SCHEMAS[kind]
    ordered = frame.loc[:, schema.names].sort_values(list(SORT_KEYS), kind="stable")
    return pa.Table.from_pandas(ordered, schema=schema, preserve_index=False)


def write_parquet(frame: pd.DataFrame, kind: DatasetKind, path: Path) -> None:
    """Write deterministically ordered rows with a fixed schema, atomically."""
    buffer = pa.BufferOutputStream()
    pq.write_table(to_table(frame, kind), buffer, compression=PARQUET_COMPRESSION)
    atomic_write_bytes(path, buffer.getvalue().to_pybytes())


def read_parquet(path: Path, kind: DatasetKind) -> pd.DataFrame:
    """Read a dataset file, checking it has exactly the expected schema."""
    table = pq.read_table(path)
    expected = SCHEMAS[kind]
    if not table.schema.remove_metadata().equals(expected, check_metadata=False):
        raise ValueError(f"{path.name} does not match the {kind} schema version in use")
    return normalize_dtypes(table.to_pandas(), kind)


def normalize_dtypes(frame: pd.DataFrame, kind: DatasetKind) -> pd.DataFrame:
    """Give every column its canonical pandas dtype (nullable Int64 for integers)."""
    frame = frame.copy()
    for field in SCHEMAS[kind]:
        name = field.name
        if pa.types.is_timestamp(field.type):
            frame[name] = pd.to_datetime(frame[name], utc=True).astype("datetime64[us, UTC]")
        elif pa.types.is_integer(field.type):
            frame[name] = pd.to_numeric(frame[name], errors="coerce").astype("Int64")
        elif pa.types.is_floating(field.type):
            frame[name] = pd.to_numeric(frame[name], errors="coerce").astype("float64")
        else:
            frame[name] = frame[name].astype("object").where(frame[name].notna(), None)
    return frame


def _canonical_cell(value: object) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    if isinstance(value, pd.Timestamp):
        return value.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(value, float):
        return "" if math.isnan(value) else repr(value)
    return str(value)


def content_sha256(frame: pd.DataFrame, kind: DatasetKind) -> str:
    """Hash of the dataset *values*, independent of Parquet encoding and library versions.

    Definition: rows sorted by (asset_id, timestamp_utc); columns in schema order;
    serialized as CSV with a header row, `\\n` line endings, floats as Python
    `repr` (shortest round-trip form), timestamps as ISO 8601 UTC with
    microseconds, and nulls as empty fields; then SHA-256 of the UTF-8 bytes.
    """
    columns = SCHEMAS[kind].names
    ordered = frame.loc[:, columns].sort_values(list(SORT_KEYS), kind="stable")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in ordered.itertuples(index=False, name=None):
        writer.writerow([_canonical_cell(value) for value in row])
    return sha256_bytes(buffer.getvalue().encode("utf-8"))
