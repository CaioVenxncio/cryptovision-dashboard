"""Shared enums and result metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

import cryptovision

DEFAULT_ANNUALIZATION_FACTOR = 365
MISSING_DATA_POLICY = (
    "calendar-complete daily index; missing prices stay missing (no interpolation or "
    "forward-fill); a return is defined only between two consecutive calendar days with "
    "observed prices; statistics use the observations that are present"
)


class ReturnType(StrEnum):
    SIMPLE = "simple"
    LOG = "log"


class CorrelationMethod(StrEnum):
    PEARSON = "pearson"
    SPEARMAN = "spearman"


@dataclass(frozen=True)
class AnalysisContext:
    """Where the data came from. Copied from the dataset manifest when available."""

    dataset_id: str
    dataset_version: str
    provider: str
    quote_currency: str
    frequency: str
    price_column: str
    synthetic: bool = False
    content_sha256: str | None = None
    pairs: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultMetadata:
    """Interpretation and reproducibility details attached to every result."""

    context: AnalysisContext
    assets: tuple[str, ...]
    start: date | None
    end: date | None
    calculation: str
    return_type: ReturnType | None = None
    method: CorrelationMethod | None = None
    window: int | None = None
    min_observations: int | None = None
    annualization_factor: int | None = None
    sample_counts: dict[str, int] = field(default_factory=dict)
    missing_data_policy: str = MISSING_DATA_POLICY
    software_version: str = cryptovision.__version__

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("return_type", "method"):
            if data[key] is not None:
                data[key] = str(data[key])
        for key in ("start", "end"):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return data
