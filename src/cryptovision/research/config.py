"""Experiment configuration (TOML) and analysis specifications."""

from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from cryptovision.research.exceptions import ExperimentConfigError

Estimand = Literal["raw", "devolatilized"]


def other_estimand(estimand: Estimand) -> Estimand:
    return "devolatilized" if estimand == "raw" else "raw"


class AnalysisSpec(BaseModel):
    """Everything that defines one estimate of the regime difference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    estimand: Estimand
    return_type: Literal["log", "simple"] = "log"
    correlation: Literal["pearson", "spearman"] = "pearson"
    proxy: Literal["mean_asset_volatility", "asset_volatility"] = "mean_asset_volatility"
    proxy_asset: str = ""
    lookback_days: int = Field(default=30, ge=10, le=365)
    threshold: Literal["full_sample_quantile", "trailing_quantile"] = "full_sample_quantile"
    quantile: float = Field(default=0.5, gt=0, lt=1)
    trailing_days: int = Field(default=365, ge=30)
    evaluation_start: date
    min_days_per_regime: int = Field(default=180, ge=30)
    mean_block_length: int = Field(default=20, ge=1)
    exclude_assets: tuple[str, ...] = ()
    contemporaneous: bool = False

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.proxy == "asset_volatility" and not self.proxy_asset:
            raise ValueError("proxy 'asset_volatility' requires proxy_asset")
        if self.proxy == "mean_asset_volatility" and self.proxy_asset:
            raise ValueError("proxy_asset is only used with proxy 'asset_volatility'")
        return self


class ExperimentInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    protocol_version: str
    protocol_path: str
    description: str


class DatasetPin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assets: tuple[str, ...] = Field(min_length=2)
    start: date
    end: date


class PrimarySection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    estimand: Estimand
    fallback_estimand: Estimand
    return_type: Literal["log", "simple"]
    correlation: Literal["pearson", "spearman"]
    proxy: Literal["mean_asset_volatility", "asset_volatility"]
    proxy_asset: str = ""
    lookback_days: int
    threshold: Literal["full_sample_quantile", "trailing_quantile"]
    quantile: float
    trailing_days: int
    evaluation_start: date
    min_days_per_regime: int


class BootstrapSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal["stationary"]
    replications: int = Field(ge=200, le=20_000)
    mean_block_length: int = Field(ge=1)
    confidence_level: float = Field(gt=0.5, lt=1)
    seed: int = Field(ge=0)
    max_rejected_fraction: float = Field(ge=0, le=0.5)


class RobustnessCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    id: str
    label: str

    @property
    def overrides(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class Illustration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    label: str
    contemporaneous: bool = True


class SimulationSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    n_assets: int = Field(ge=2, le=20)
    n_days: int = Field(ge=200)
    short_n_days: int = Field(ge=200)
    replications: int = Field(ge=10)
    bootstrap_replications: int = Field(ge=99)
    mean_block_length: int = Field(ge=1)
    block_sensitivity: tuple[int, ...] = ()
    pseudo_true_days: int = Field(ge=10_000)
    seed: int = Field(ge=0)
    daily_scale: float = Field(gt=0)


class GateSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_null_rejection_rate: float = Field(gt=0, lt=1)
    max_abs_pseudo_true_null: float = Field(gt=0, lt=1)
    min_coverage: float = Field(gt=0, lt=1)


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment: ExperimentInfo
    dataset: DatasetPin
    primary: PrimarySection
    bootstrap: BootstrapSettings
    robustness: tuple[RobustnessCheck, ...] = ()
    illustration: Illustration | None = None
    simulation: SimulationSettings
    gate: GateSettings

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [check.id for check in self.robustness]
        if len(ids) != len(set(ids)):
            raise ValueError("robustness ids must be unique")
        if self.primary.estimand == self.primary.fallback_estimand:
            raise ValueError("fallback_estimand must differ from estimand")
        # Fail early on overrides that would not produce a valid specification.
        for estimand in (self.primary.estimand, self.primary.fallback_estimand):
            for check in self.robustness:
                spec = self.robustness_spec(check, primary_estimand=estimand)
                self._check_assets(spec, check.id)
            self._check_assets(self.primary_spec(estimand), "primary")
        return self

    def _check_assets(self, spec: AnalysisSpec, where: str) -> None:
        unknown = set(spec.exclude_assets) - set(self.dataset.assets)
        if unknown:
            raise ValueError(f"{where}: excluded assets not in the universe: {sorted(unknown)}")
        if len(self.dataset.assets) - len(spec.exclude_assets) < 2:
            raise ValueError(f"{where}: fewer than two assets remain")
        if spec.proxy == "asset_volatility" and spec.proxy_asset not in self.dataset.assets:
            raise ValueError(f"{where}: proxy_asset {spec.proxy_asset!r} not in the universe")

    def primary_spec(self, estimand: Estimand | None = None) -> AnalysisSpec:
        values = self.primary.model_dump(exclude={"fallback_estimand"})
        if estimand is not None:
            values["estimand"] = estimand
        return AnalysisSpec(**values, mean_block_length=self.bootstrap.mean_block_length)

    def robustness_spec(
        self, check: RobustnessCheck, *, primary_estimand: Estimand
    ) -> AnalysisSpec:
        overrides = check.overrides
        if overrides.get("estimand") == "alternative":
            overrides["estimand"] = other_estimand(primary_estimand)
        base = self.primary_spec(primary_estimand).model_dump()
        unknown = set(overrides) - set(base)
        if unknown:
            raise ValueError(f"{check.id}: unknown override keys {sorted(unknown)}")
        if "exclude_assets" in overrides:
            overrides["exclude_assets"] = tuple(overrides["exclude_assets"])
        return AnalysisSpec(**{**base, **overrides})

    def illustration_spec(self, *, primary_estimand: Estimand) -> AnalysisSpec | None:
        if self.illustration is None:
            return None
        return self.primary_spec(primary_estimand).model_copy(update={"contemporaneous": True})


def load_experiment_config(path: Path) -> ExperimentConfig:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ExperimentConfigError(f"Cannot read {path}: {exc.strerror}") from None
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ExperimentConfigError(f"Invalid TOML in {path}: {exc}") from None
    try:
        return ExperimentConfig.model_validate(document)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in error['loc']) or 'config'}: {error['msg']}"
            for error in exc.errors(include_input=False)
        )
        raise ExperimentConfigError(f"Invalid experiment config {path}: {problems}") from None
