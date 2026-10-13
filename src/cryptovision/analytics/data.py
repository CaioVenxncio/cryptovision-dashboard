"""Load validated datasets into price panels.

This is the only entry point for real observations. It goes through
`cryptovision.data.pipeline.load_dataset`, so datasets that are tampered
with, not research-ready or expired are refused.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from cryptovision.analytics.alignment import PricePanel, build_price_panel
from cryptovision.analytics.models import AnalysisContext
from cryptovision.data.pipeline import load_dataset
from cryptovision.data.provenance import DatasetManifest
from cryptovision.data.schemas import DatasetKind

PRICE_COLUMNS = {DatasetKind.OHLCV: "close", DatasetKind.PRICE_SERIES: "price"}


def context_from_manifest(manifest: DatasetManifest) -> AnalysisContext:
    kind = DatasetKind(manifest.kind)
    return AnalysisContext(
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        provider=manifest.provider,
        quote_currency=manifest.quote_currency,
        frequency=manifest.frequency,
        price_column=PRICE_COLUMNS[kind],
        synthetic=manifest.synthetic,
        content_sha256=manifest.content_sha256,
        pairs={asset["asset_id"]: asset["pair"] for asset in manifest.assets if asset.get("pair")},
    )


def load_price_panel(
    directory: Path,
    *,
    assets: list[str] | tuple[str, ...] | None = None,
    start: date | None = None,
    end: date | None = None,
    verify: bool = True,
    now: datetime | None = None,
) -> PricePanel:
    """Load a research-ready dataset and build a calendar-complete price panel."""
    loaded = load_dataset(directory, require_research_ready=True, verify=verify, now=now)
    context = context_from_manifest(loaded.manifest)
    return build_price_panel(
        loaded.frame,
        price_column=context.price_column,
        context=context,
        assets=assets,
        start=start,
        end=end,
    )
