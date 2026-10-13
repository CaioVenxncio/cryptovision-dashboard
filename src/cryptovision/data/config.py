"""Dataset configuration files (TOML) and their validation."""

from __future__ import annotations

import hashlib
import tomllib
from datetime import date
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from cryptovision.data.schemas import DatasetKind

SLUG_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"

Provider = Literal["binance_vision", "coingecko", "synthetic"]

PROVIDER_KINDS: dict[str, DatasetKind] = {
    "binance_vision": DatasetKind.OHLCV,
    "coingecko": DatasetKind.PRICE_SERIES,
    "synthetic": DatasetKind.OHLCV,
}


class DatasetConfigError(Exception):
    """A dataset configuration file is missing, unreadable or invalid."""


class AssetSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_id: str = Field(pattern=SLUG_PATTERN)
    symbol: str = Field(min_length=1)
    pair: str | None = Field(default=None, pattern=r"^[A-Z0-9]+$")
    coingecko_id: str | None = Field(default=None, pattern=SLUG_PATTERN)


class Exclusion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    reason: str


class SelectionInfo(BaseModel):
    """How the asset universe was chosen. Recorded verbatim in manifests."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str
    reference: str | None = None
    snapshot_date: date | None = None
    excluded: tuple[Exclusion, ...] = ()


class ValidationRules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Fraction of expected daily observations per asset that may be missing
    # before the dataset is not research-ready.
    max_missing_fraction: float = Field(default=0.005, ge=0, le=1)
    # Longest run of consecutive missing observations tolerated per asset.
    max_consecutive_missing: int = Field(default=3, ge=0)


class DatasetConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=SLUG_PATTERN)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str
    provider: Provider
    frequency: Literal["1d"] = "1d"
    quote_currency: str = Field(pattern=r"^[A-Z]{3,5}$")
    start: date | None = None
    end: date | None = None
    lookback_days: int | None = Field(default=None, ge=91, le=365)
    assets: tuple[AssetSpec, ...] = Field(min_length=1)
    selection: SelectionInfo
    validation: ValidationRules = ValidationRules()

    @property
    def kind(self) -> DatasetKind:
        return PROVIDER_KINDS[self.provider]

    @property
    def is_ephemeral(self) -> bool:
        """CoinGecko data may only be cached briefly (API terms §6.1.1)."""
        return self.provider == "coingecko"

    @model_validator(mode="after")
    def _check_provider_requirements(self) -> Self:
        ids = [asset.asset_id for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("asset_id values must be unique")

        if self.provider == "coingecko":
            if self.lookback_days is None:
                raise ValueError("coingecko datasets require lookback_days")
            if self.start is not None or self.end is not None:
                raise ValueError("coingecko datasets use lookback_days, not start/end")
            if any(asset.coingecko_id is None for asset in self.assets):
                raise ValueError("every coingecko asset requires coingecko_id")
            return self

        if self.start is None or self.end is None:
            raise ValueError(f"{self.provider} datasets require start and end dates")
        if self.end < self.start:
            raise ValueError("end must not be before start")
        if self.lookback_days is not None:
            raise ValueError("lookback_days is only valid for coingecko datasets")
        if self.provider == "binance_vision":
            if any(asset.pair is None for asset in self.assets):
                raise ValueError("every binance_vision asset requires pair")
            for asset in self.assets:
                if not (asset.pair or "").endswith(self.quote_currency):
                    raise ValueError(
                        f"pair {asset.pair} is not quoted in {self.quote_currency}; "
                        "quote currencies are never converted implicitly"
                    )
        return self


def config_sha256(raw: bytes) -> str:
    """SHA-256 of the configuration file bytes with line endings normalized to LF."""
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def load_dataset_config(path: Path) -> tuple[DatasetConfig, str]:
    """Load and validate a TOML dataset configuration. Returns the config and its hash."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DatasetConfigError(f"Cannot read dataset config {path}: {exc.strerror}") from None
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise DatasetConfigError(f"Invalid TOML in {path}: {exc}") from None
    try:
        config = DatasetConfig.model_validate(document.get("dataset", {}))
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'dataset'}: {error['msg']}"
            for error in exc.errors(include_input=False)
        )
        raise DatasetConfigError(f"Invalid dataset config {path}: {problems}") from None
    return config, config_sha256(raw)
