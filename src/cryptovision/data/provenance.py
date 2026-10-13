"""Dataset provenance manifests.

Four hashes with distinct meanings are recorded:

- `source_files[].sha256`: SHA-256 of each downloaded provider file (Binance
  zip archives). For Binance it is also checked against the provider's
  published `.CHECKSUM`.
- `files.<name>.sha256`: SHA-256 of the stored Parquet file bytes. Detects
  corruption or tampering of the local copy. Depends on the Parquet writer
  version, so it is not comparable across machines.
- `content_sha256`: SHA-256 of a canonical CSV serialization of the valid
  rows (see `storage.content_sha256`). Identical values give identical hashes
  regardless of Parquet encoding.
- `config.sha256`: SHA-256 of the configuration file (LF line endings).
"""

from __future__ import annotations

import json
import platform
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import pyarrow
from pydantic import BaseModel, ConfigDict, Field

import cryptovision
from cryptovision.data.storage import atomic_write_bytes
from cryptovision.models import UtcDatetime

MANIFEST_VERSION = "1.0"
MANIFEST_FILENAME = "manifest.json"
DATA_FILENAME = "data.parquet"
REJECTED_FILENAME = "rejected.parquet"

# Increment when normalization or validation logic changes the stored output.
TRANSFORMATION_VERSION = "1.0"

HASH_DEFINITIONS = {
    "source_files.sha256": "SHA-256 of each downloaded provider file, byte for byte.",
    "files.sha256": "SHA-256 of the stored file bytes; depends on the Parquet writer.",
    "content_sha256": (
        "SHA-256 of the canonical CSV form of data.parquet: rows sorted by "
        "(asset_id, timestamp_utc), schema column order, floats as Python repr, "
        "timestamps ISO 8601 UTC with microseconds, nulls empty, LF line endings."
    ),
    "config.sha256": "SHA-256 of the dataset configuration file with LF line endings.",
}


class SourceFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    local_path: str
    sha256: str
    size_bytes: int
    checksum_verified: bool
    retrieved_at: UtcDatetime
    reused_local_copy: bool = False


class StoredFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    sha256: str
    rows: int


class Period(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: date | None
    end: date | None


class DatasetManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest_version: str = MANIFEST_VERSION
    dataset_id: str
    dataset_version: str
    kind: str
    provider: str
    synthetic: bool = False
    retention: Literal["archival", "ephemeral"]
    expires_at: UtcDatetime | None = None
    status: Literal["research_ready", "failed_validation"]
    description: str
    source: dict[str, Any]
    assets: list[dict[str, Any]]
    selection: dict[str, Any]
    quote_currency: str
    frequency: str
    requested_period: Period
    actual_period: Period
    created_at: UtcDatetime
    retrieval_started_at: UtcDatetime | None = None
    retrieval_finished_at: UtcDatetime | None = None
    source_files: list[SourceFile] = Field(default_factory=list)
    config: dict[str, Any]
    files: dict[str, StoredFile]
    content_sha256: str
    validation: dict[str, Any]
    software: dict[str, str]
    attribution: str
    license_notes: str
    hash_definitions: dict[str, str] = Field(default_factory=lambda: dict(HASH_DEFINITIONS))

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at


def software_versions() -> dict[str, str]:
    from cryptovision.data.schemas import SCHEMA_VERSION

    return {
        "cryptovision": cryptovision.__version__,
        "schema_version": SCHEMA_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "pyarrow": pyarrow.__version__,
    }


def write_manifest(manifest: DatasetManifest, directory: Path) -> Path:
    path = directory / MANIFEST_FILENAME
    text = json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=False) + "\n"
    atomic_write_bytes(path, text.encode("utf-8"))
    return path


def read_manifest(directory: Path) -> DatasetManifest:
    path = directory / MANIFEST_FILENAME
    return DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
