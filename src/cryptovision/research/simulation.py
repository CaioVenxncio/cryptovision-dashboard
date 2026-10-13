"""Synthetic method validation (protocol §10).

Each scenario generates multivariate daily returns with a known dependence
structure, applies the same regime rule and stationary bootstrap as the
empirical analysis, and records whether the 95% interval excludes zero
(rejection), whether it covers the pseudo-true value, bias and width.

The pseudo-true value of an estimand under a process is approximated by the
estimator on one long path (`pseudo_true_days`). For processes with constant
conditional correlation the *substantive* null is "no dependence change"; the
gate checks both that the estimand is ~0 there and that intervals do not
reject too often.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from cryptovision.research.bootstrap import bootstrap_regime_deltas
from cryptovision.research.config import AnalysisSpec, Estimand, GateSettings, SimulationSettings
from cryptovision.research.estimands import regime_delta
from cryptovision.research.exceptions import InsufficientSampleError
from cryptovision.research.experiment import prepare_sample

GARCH_ALPHA, GARCH_BETA = 0.08, 0.90
BURN_IN = 500
SIMULATION_START = date(2000, 1, 1)
# With a 365-day sample the regimes hold ~167 days each, so the empirical
# 180-day minimum cannot be met by construction; the short-sample scenario
# uses this minimum instead (documented in the validation output).
SHORT_SAMPLE_MIN_DAYS = 60


@dataclass(frozen=True)
class Scenario:
    id: str
    description: str
    is_null: bool
    process: str
    params: dict[str, Any] = field(default_factory=dict)
    short: bool = False
    missing_fraction: float = 0.0


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("N1", "i.i.d. Gaussian, rho=0.5, constant volatility", True, "constant", {"rho": 0.5}),
    Scenario("N2", "Common GARCH(1,1) volatility, rho=0.5", True, "common_garch", {"rho": 0.5}),
    Scenario(
        "N3",
        "Common Markov volatility (x2.5, stay 0.99), rho=0.5",
        True,
        "common_markov",
        {"rho": 0.5, "scale": 2.5, "stay": 0.99},
    ),
    Scenario(
        "N4", "Asset-specific GARCH(1,1) volatility, rho=0.5", True, "asset_garch", {"rho": 0.5}
    ),
    Scenario("N5", "Common GARCH volatility, rho=-0.2", True, "common_garch", {"rho": -0.2}),
    Scenario("N6", "As N2, 365 days", True, "common_garch", {"rho": 0.5}, short=True),
    Scenario(
        "N7",
        "As N2, 5% of returns missing",
        True,
        "common_garch",
        {"rho": 0.5},
        missing_fraction=0.05,
    ),
    Scenario(
        "N8",
        "Common Markov volatility, stay 0.998 (very persistent)",
        True,
        "common_markov",
        {"rho": 0.5, "scale": 2.5, "stay": 0.998},
    ),
    Scenario("N9", "Common GARCH volatility, rho=0", True, "common_garch", {"rho": 0.0}),
    Scenario(
        "A1",
        "Markov state drives volatility (x2.5) and correlation (0.3 -> 0.6)",
        False,
        "markov_vol_corr",
        {"rho_low": 0.3, "rho_high": 0.6, "scale": 2.5, "stay": 0.99},
    ),
    Scenario(
        "A2",
        "One-factor model, factor variance x4 in the Markov high state",
        False,
        "factor_markov",
        {"factor_var_low": 0.5, "factor_var_high": 2.0, "stay": 0.99},
    ),
    Scenario(
        "A3",
        "Correlation switches 0.3/0.6 independently of constant volatility",
        False,
        "corr_switch",
        {"rho_low": 0.3, "rho_high": 0.6, "stay": 0.99},
    ),
)

BLOCK_SENSITIVITY_SCENARIOS = ("N2", "N3")


def _equicorrelation_factor(n_assets: int, rho: float) -> np.ndarray:
    matrix = np.full((n_assets, n_assets), rho)
    np.fill_diagonal(matrix, 1.0)
    return np.linalg.cholesky(matrix)


def _markov_states(n: int, stay: float, rng: np.random.Generator) -> np.ndarray:
    switches = rng.random(n) >= stay
    states = np.empty(n, dtype=bool)
    current = bool(rng.random() < 0.5)
    for t in range(n):
        if switches[t]:
            current = not current
        states[t] = current
    return states


def _garch_variance(shocks: np.ndarray) -> np.ndarray:
    """Unit-unconditional-variance GARCH(1,1) driven by standard normal shocks (1-D)."""
    omega = 1.0 - GARCH_ALPHA - GARCH_BETA
    h = np.empty(shocks.size)
    h[0] = 1.0
    for t in range(1, shocks.size):
        h[t] = omega + GARCH_ALPHA * h[t - 1] * shocks[t - 1] ** 2 + GARCH_BETA * h[t - 1]
    return h


def simulate_returns(
    scenario: Scenario, n_days: int, n_assets: int, scale: float, rng: np.random.Generator
) -> np.ndarray:
    """(n_days x n_assets) daily returns for a scenario."""
    p = scenario.params
    total = n_days + BURN_IN
    z = rng.standard_normal((total, n_assets))
    process = scenario.process

    if process in {"constant", "common_garch", "common_markov", "asset_garch"}:
        correlated = z @ _equicorrelation_factor(n_assets, p["rho"]).T
        if process == "constant":
            sigma = np.ones((total, 1))
        elif process == "common_garch":
            sigma = np.sqrt(_garch_variance(correlated[:, 0]))[:, None]
        elif process == "common_markov":
            sigma = np.where(_markov_states(total, p["stay"], rng), p["scale"], 1.0)[:, None]
        else:
            sigma = np.column_stack(
                [np.sqrt(_garch_variance(correlated[:, i])) for i in range(n_assets)]
            )
        returns = sigma * correlated
    elif process in {"markov_vol_corr", "corr_switch"}:
        states = _markov_states(total, p["stay"], rng)
        low = z @ _equicorrelation_factor(n_assets, p["rho_low"]).T
        high = z @ _equicorrelation_factor(n_assets, p["rho_high"]).T
        returns = np.where(states[:, None], high, low)
        if process == "markov_vol_corr":
            returns = returns * np.where(states, p["scale"], 1.0)[:, None]
    elif process == "factor_markov":
        states = _markov_states(total, p["stay"], rng)
        factor_sd = np.sqrt(np.where(states, p["factor_var_high"], p["factor_var_low"]))
        factor = factor_sd * rng.standard_normal(total)
        returns = factor[:, None] + z
    else:  # pragma: no cover - guarded by the scenario table
        raise ValueError(f"Unknown process {process}")

    returns = scale * returns[BURN_IN:]
    if scenario.missing_fraction > 0:
        returns = np.where(rng.random(returns.shape) < scenario.missing_fraction, np.nan, returns)
    return returns


def _frame(returns: np.ndarray) -> pd.DataFrame:
    index = pd.date_range(SIMULATION_START, periods=len(returns), freq="D", tz="UTC")
    return pd.DataFrame(
        returns, index=index, columns=[f"asset{i}" for i in range(returns.shape[1])]
    )


def simulation_spec(template: AnalysisSpec, scenario: Scenario) -> AnalysisSpec:
    update: dict[str, Any] = {"evaluation_start": SIMULATION_START}
    if scenario.short:
        update["min_days_per_regime"] = SHORT_SAMPLE_MIN_DAYS
    return template.model_copy(update=update)


def pseudo_true(
    scenario: Scenario,
    template: AnalysisSpec,
    settings: SimulationSettings,
    rng: np.random.Generator,
) -> dict[Estimand, float]:
    returns = simulate_returns(
        scenario, settings.pseudo_true_days, settings.n_assets, settings.daily_scale, rng
    )
    try:
        sample = prepare_sample(_frame(returns), simulation_spec(template, scenario))
    except InsufficientSampleError:
        # The regime rule cannot be applied to this process; recorded as NaN.
        return {"raw": math.nan, "devolatilized": math.nan}
    return {
        estimand: regime_delta(sample.values(estimand), sample.high, template.correlation)
        for estimand in ("raw", "devolatilized")
    }


@dataclass
class EstimandMetrics:
    pseudo_true: float
    rejection_rate: float
    coverage: float
    bias: float
    mean_estimate: float
    mean_width: float
    datasets: int

    @property
    def rejection_mc_se(self) -> float:
        rate = self.rejection_rate
        return math.sqrt(rate * (1 - rate) / self.datasets) if self.datasets else math.nan


@dataclass
class ScenarioResult:
    scenario: Scenario
    mean_block_length: int
    min_days_per_regime: int
    failed_datasets: int
    metrics: dict[str, EstimandMetrics]


def run_scenario(
    scenario: Scenario,
    template: AnalysisSpec,
    settings: SimulationSettings,
    *,
    mean_block_length: int,
    pseudo: dict[Estimand, float],
    seed_sequence: np.random.SeedSequence,
    replications: int | None = None,
    bootstrap_replications: int | None = None,
) -> ScenarioResult:
    spec = simulation_spec(template, scenario)
    n_days = settings.short_n_days if scenario.short else settings.n_days
    replications = replications or settings.replications
    bootstrap_replications = bootstrap_replications or settings.bootstrap_replications
    estimates: dict[str, list[tuple[float, float, float]]] = {"raw": [], "devolatilized": []}
    failed = 0
    for stream in seed_sequence.spawn(replications):
        rng = np.random.default_rng(stream)
        returns = simulate_returns(scenario, n_days, settings.n_assets, settings.daily_scale, rng)
        try:
            sample = prepare_sample(_frame(returns), spec)
        except InsufficientSampleError:
            failed += 1
            continue
        results = bootstrap_regime_deltas(
            [sample.raw, sample.devolatilized],
            sample.high,
            methods=[spec.correlation, spec.correlation],
            replications=bootstrap_replications,
            mean_block_length=mean_block_length,
            confidence_level=0.95,
            min_days_per_regime=spec.min_days_per_regime,
            rng=rng,
        )
        for estimand, result in zip(("raw", "devolatilized"), results, strict=True):
            estimates[estimand].append((result.estimate, result.ci_low, result.ci_high))

    metrics = {}
    for estimand, rows in estimates.items():
        array = np.array(rows, dtype="float64") if rows else np.empty((0, 3))
        array = array[np.all(np.isfinite(array), axis=1)]
        truth = pseudo[estimand]  # type: ignore[index]
        n = len(array)
        if n == 0:
            metrics[estimand] = EstimandMetrics(
                truth, math.nan, math.nan, math.nan, math.nan, math.nan, 0
            )
            continue
        est, low, high = array.T
        metrics[estimand] = EstimandMetrics(
            pseudo_true=truth,
            rejection_rate=float(np.mean((low > 0) | (high < 0))),
            coverage=float(np.mean((low <= truth) & (truth <= high))),
            bias=float(np.mean(est) - truth),
            mean_estimate=float(np.mean(est)),
            mean_width=float(np.mean(high - low)),
            datasets=n,
        )
    return ScenarioResult(
        scenario=scenario,
        mean_block_length=mean_block_length,
        min_days_per_regime=spec.min_days_per_regime,
        failed_datasets=failed,
        metrics=metrics,
    )


@dataclass
class GateEvaluation:
    estimand: Estimand
    passed: bool
    failures: list[str]


@dataclass
class ValidationResult:
    scenarios: list[ScenarioResult]
    block_sensitivity: list[ScenarioResult]
    gates: list[GateEvaluation]
    primary_estimand: Estimand | None  # None: no estimand validated -> descriptive only
    settings: dict[str, Any]

    @property
    def validated(self) -> bool:
        return self.primary_estimand is not None


def evaluate_gate(
    scenarios: list[ScenarioResult], estimand: Estimand, gate: GateSettings
) -> GateEvaluation:
    failures = []
    for result in scenarios:
        metrics = result.metrics[estimand]
        sid = result.scenario.id
        if metrics.datasets == 0 or not math.isfinite(metrics.pseudo_true):
            failures.append(
                f"{sid}: the regime rule could not be applied "
                f"({result.failed_datasets} datasets with too few classified days)"
            )
            continue
        if result.scenario.is_null:
            if abs(metrics.pseudo_true) > gate.max_abs_pseudo_true_null:
                failures.append(
                    f"G2 {sid}: pseudo-true {metrics.pseudo_true:+.4f} exceeds "
                    f"+/-{gate.max_abs_pseudo_true_null}"
                )
            elif metrics.rejection_rate > gate.max_null_rejection_rate:
                failures.append(
                    f"G1 {sid}: rejection rate {metrics.rejection_rate:.3f} > "
                    f"{gate.max_null_rejection_rate}"
                )
        if metrics.coverage < gate.min_coverage:
            failures.append(f"G3 {sid}: coverage {metrics.coverage:.3f} < {gate.min_coverage}")
    return GateEvaluation(estimand=estimand, passed=not failures, failures=failures)


def run_validation(
    template: AnalysisSpec,
    settings: SimulationSettings,
    gate: GateSettings,
    *,
    primary: Estimand,
    fallback: Estimand,
    scenarios: tuple[Scenario, ...] = SCENARIOS,
    progress=lambda _: None,
) -> ValidationResult:
    """Run every scenario, the block-length sensitivity, and the pre-specified gate decision."""
    root = np.random.SeedSequence(settings.seed)
    streams = root.spawn(len(scenarios))
    results, sensitivity = [], []
    for scenario, stream in zip(scenarios, streams, strict=True):
        truth_stream, data_stream = stream.spawn(2)
        pseudo = pseudo_true(scenario, template, settings, np.random.default_rng(truth_stream))
        result = run_scenario(
            scenario,
            template,
            settings,
            mean_block_length=settings.mean_block_length,
            pseudo=pseudo,
            seed_sequence=data_stream,
        )
        results.append(result)
        progress(f"{scenario.id}: done")
        if scenario.id in BLOCK_SENSITIVITY_SCENARIOS:
            for block in settings.block_sensitivity:
                # Same datasets (same seed sequence), different block length.
                sensitivity.append(
                    run_scenario(
                        scenario,
                        template,
                        settings,
                        mean_block_length=block,
                        pseudo=pseudo,
                        seed_sequence=np.random.SeedSequence(
                            data_stream.entropy, spawn_key=data_stream.spawn_key
                        ),
                    )
                )
                progress(f"{scenario.id} block {block}: done")

    gates = [evaluate_gate(results, estimand, gate) for estimand in (primary, fallback)]
    chosen: Estimand | None = None
    for evaluation in gates:
        if evaluation.passed:
            chosen = evaluation.estimand
            break
    return ValidationResult(
        scenarios=results,
        block_sensitivity=sensitivity,
        gates=gates,
        primary_estimand=chosen,
        settings={
            **settings.model_dump(),
            "short_sample_min_days_per_regime": SHORT_SAMPLE_MIN_DAYS,
            "garch": {"alpha": GARCH_ALPHA, "beta": GARCH_BETA},
            "burn_in": BURN_IN,
        },
    )


def validation_to_dict(result: ValidationResult) -> dict[str, Any]:
    def scenario_dict(item: ScenarioResult) -> dict[str, Any]:
        return {
            "id": item.scenario.id,
            "description": item.scenario.description,
            "is_null": item.scenario.is_null,
            "mean_block_length": item.mean_block_length,
            "min_days_per_regime": item.min_days_per_regime,
            "failed_datasets": item.failed_datasets,
            "metrics": {
                name: {**asdict(m), "rejection_mc_se": m.rejection_mc_se}
                for name, m in item.metrics.items()
            },
        }

    return {
        "settings": result.settings,
        "scenarios": [scenario_dict(item) for item in result.scenarios],
        "block_sensitivity": [scenario_dict(item) for item in result.block_sensitivity],
        "gates": [asdict(g) for g in result.gates],
        "primary_estimand": result.primary_estimand,
        "validated": result.validated,
    }
