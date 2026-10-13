"""Sample preparation and analysis orchestration (no file writes, no network)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from cryptovision.analytics.data import load_price_panel
from cryptovision.analytics.models import AnalysisContext
from cryptovision.analytics.returns import compute_returns
from cryptovision.research.bootstrap import BootstrapResult, bootstrap_regime_deltas
from cryptovision.research.config import AnalysisSpec, BootstrapSettings, Estimand, ExperimentConfig
from cryptovision.research.estimands import RegimeEstimate, pair_count, regime_estimate
from cryptovision.research.exceptions import InsufficientSampleError, ResearchError
from cryptovision.research.regimes import (
    HIGH,
    RegimeClassification,
    classify_regimes,
    lagged_volatility,
    volatility_proxy,
)


@dataclass(frozen=True)
class PreparedSample:
    """Days usable for one specification: complete returns and a regime label."""

    spec: AnalysisSpec
    assets: tuple[str, ...]
    dates: pd.DatetimeIndex
    raw: np.ndarray
    devolatilized: np.ndarray
    high: np.ndarray
    classification: RegimeClassification
    excluded_incomplete: int

    def values(self, estimand: Estimand) -> np.ndarray:
        return self.raw if estimand == "raw" else self.devolatilized

    @property
    def n_days(self) -> int:
        return len(self.dates)


def prepare_sample(returns: pd.DataFrame, spec: AnalysisSpec) -> PreparedSample:
    """Build the evaluation sample from a calendar-indexed returns frame (columns = assets).

    Devolatilized returns divide each return by the asset's strictly-past
    volatility over `lookback_days`. A day is used only if it has a regime
    label and every asset has both a return and a devolatilized return
    (listwise deletion within the universe).
    """
    assets = tuple(a for a in returns.columns if a not in spec.exclude_assets)
    data = returns.loc[:, list(assets)]
    if spec.proxy == "asset_volatility" and spec.proxy_asset not in data.columns:
        raise ResearchError(f"Proxy asset {spec.proxy_asset!r} is not in the data.")

    evaluation = pd.Series(data.index.date >= spec.evaluation_start, index=data.index)
    proxy = volatility_proxy(data, spec)
    classification = classify_regimes(proxy, spec, evaluation)
    devolatilized = data / lagged_volatility(data, spec.lookback_days)

    labelled = classification.labels.notna()
    complete = data.notna().all(axis=1) & devolatilized.notna().all(axis=1)
    keep = labelled & complete
    high = (classification.labels[keep] == HIGH).to_numpy()
    sample = PreparedSample(
        spec=spec,
        assets=assets,
        dates=data.index[keep],
        raw=data[keep].to_numpy(dtype="float64"),
        devolatilized=devolatilized[keep].to_numpy(dtype="float64"),
        high=high,
        classification=classification,
        excluded_incomplete=int((labelled & ~complete).sum()),
    )
    n_high = int(high.sum())
    if min(n_high, len(high) - n_high) < spec.min_days_per_regime:
        raise InsufficientSampleError(
            f"Regimes have {n_high} high and {len(high) - n_high} low days; "
            f"at least {spec.min_days_per_regime} each are required."
        )
    return sample


@dataclass(frozen=True)
class AnalysisResult:
    analysis_id: str
    label: str
    spec: AnalysisSpec
    estimate: RegimeEstimate
    bootstrap: BootstrapResult
    first_day: date
    last_day: date
    excluded_incomplete: int
    assets: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def n_pairs(self) -> int:
        return pair_count(len(self.assets))


def analyze(
    sample: PreparedSample,
    *,
    analysis_id: str,
    label: str,
    settings: BootstrapSettings,
    rng: np.random.Generator,
) -> AnalysisResult:
    spec = sample.spec
    values = sample.values(spec.estimand)
    estimate = regime_estimate(values, sample.high, spec.correlation)
    (result,) = bootstrap_regime_deltas(
        [values],
        sample.high,
        methods=[spec.correlation],
        replications=settings.replications,
        mean_block_length=spec.mean_block_length,
        confidence_level=settings.confidence_level,
        min_days_per_regime=spec.min_days_per_regime,
        rng=rng,
    )
    warnings = []
    if result.rejected_fraction > settings.max_rejected_fraction:
        warnings.append(
            f"{result.rejected} of {result.replications} bootstrap replicates were rejected "
            f"({result.rejected_fraction:.1%}), above the "
            f"{settings.max_rejected_fraction:.0%} limit."
        )
    if not np.isfinite(estimate.delta):
        warnings.append("The estimate is undefined (a series is constant within a regime).")
    return AnalysisResult(
        analysis_id=analysis_id,
        label=label,
        spec=spec,
        estimate=estimate,
        bootstrap=result,
        first_day=sample.dates[0].date(),
        last_day=sample.dates[-1].date(),
        excluded_incomplete=sample.excluded_incomplete,
        assets=sample.assets,
        warnings=tuple(warnings),
    )


def load_returns(
    dataset_dir: Path, config: ExperimentConfig
) -> tuple[dict[str, pd.DataFrame], AnalysisContext]:
    """Log and simple returns from the pinned dataset, read once via the Phase 3/4 loaders.

    The dataset must match the id, version and content hash pinned in the
    configuration; the loader also re-verifies the stored file hashes.
    """
    panel = load_price_panel(
        dataset_dir,
        assets=list(config.dataset.assets),
        start=config.dataset.start,
        end=config.dataset.end,
    )
    if panel.context.content_sha256 != config.dataset.content_sha256:
        raise ResearchError(
            "The dataset content hash does not match the hash pinned in the experiment config "
            f"({panel.context.content_sha256} != {config.dataset.content_sha256})."
        )
    if (panel.context.dataset_id, panel.context.dataset_version) != (
        config.dataset.id,
        config.dataset.version,
    ):
        raise ResearchError("The dataset id or version does not match the experiment config.")
    returns = {kind: compute_returns(panel, kind).returns for kind in ("log", "simple")}
    return returns, panel.context


def locate_dataset(data_dir: Path, config: ExperimentConfig) -> Path:
    """Archival datasets live under `datasets/`, synthetic ones under `synthetic/`."""
    for group in ("datasets", "synthetic"):
        candidate = data_dir / group / config.dataset.id / config.dataset.version
        if (candidate / "manifest.json").exists():
            return candidate
    raise ResearchError(
        f"Dataset {config.dataset.id} v{config.dataset.version} not found under {data_dir}. "
        "Rebuild it with cryptovision-data (see docs/research-reproducibility.md)."
    )


@dataclass(frozen=True)
class ExperimentResult:
    primary_estimand: Estimand
    validated: bool
    primary: AnalysisResult
    robustness: tuple[AnalysisResult, ...]
    illustration: AnalysisResult | None
    primary_sample: PreparedSample


def run_experiment(
    config: ExperimentConfig,
    returns_by_type: dict[str, pd.DataFrame],
    *,
    primary_estimand: Estimand,
    validated: bool,
) -> ExperimentResult:
    """Run the primary analysis, the robustness grid and the illustration.

    Each analysis gets its own random stream derived from the configured seed
    (`SeedSequence(seed).spawn`), in a fixed order, so results do not depend
    on which analyses run before it.
    """
    settings = config.bootstrap
    checks = config.robustness
    streams = np.random.SeedSequence(settings.seed).spawn(2 + len(checks))

    def run(
        spec: AnalysisSpec, analysis_id: str, label: str, stream
    ) -> tuple[AnalysisResult, PreparedSample]:
        sample = prepare_sample(returns_by_type[spec.return_type], spec)
        result = analyze(
            sample,
            analysis_id=analysis_id,
            label=label,
            settings=settings,
            rng=np.random.default_rng(stream),
        )
        return result, sample

    primary, primary_sample = run(
        config.primary_spec(primary_estimand), "primary", "Primary analysis", streams[0]
    )
    robustness = tuple(
        run(
            config.robustness_spec(check, primary_estimand=primary_estimand),
            check.id,
            check.label,
            stream,
        )[0]
        for check, stream in zip(checks, streams[1:-1], strict=True)
    )
    illustration = None
    spec = config.illustration_spec(primary_estimand=primary_estimand)
    if spec is not None and config.illustration is not None:
        illustration = run(spec, config.illustration.id, config.illustration.label, streams[-1])[0]
    return ExperimentResult(
        primary_estimand=primary_estimand,
        validated=validated,
        primary=primary,
        robustness=robustness,
        illustration=illustration,
        primary_sample=primary_sample,
    )
