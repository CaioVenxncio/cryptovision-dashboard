"""Serialization of results and generation of the Markdown research report.

Interpretive sentences are produced by the decision rules of the frozen
protocol (§8, §9), not written by hand after seeing the results.
"""

from __future__ import annotations

import csv
import io
import math
from typing import Any

from cryptovision.research.experiment import AnalysisResult, ExperimentResult, PreparedSample

SMALLEST_EFFECT_OF_INTEREST = 0.05


def _round(value: float, digits: int = 4) -> str:
    return "n/a" if value is None or not math.isfinite(value) else f"{value:+.{digits}f}"


def analysis_to_dict(result: AnalysisResult, *, bonferroni_level: float | None) -> dict[str, Any]:
    estimate, boot = result.estimate, result.bootstrap
    pairs = []
    assets = result.assets
    for i in range(len(assets)):
        for j in range(i + 1, len(assets)):
            pairs.append(
                {
                    "asset_a": assets[i],
                    "asset_b": assets[j],
                    "high": float(estimate.corr_high[i, j]),
                    "low": float(estimate.corr_low[i, j]),
                    "difference": float(estimate.corr_high[i, j] - estimate.corr_low[i, j]),
                }
            )
    data: dict[str, Any] = {
        "id": result.analysis_id,
        "label": result.label,
        "spec": result.spec.model_dump(mode="json"),
        "assets": list(assets),
        "n_assets": len(assets),
        "n_pairs": result.n_pairs,
        "first_day": result.first_day.isoformat(),
        "last_day": result.last_day.isoformat(),
        "n_days": estimate.n_high + estimate.n_low,
        "n_high": estimate.n_high,
        "n_low": estimate.n_low,
        "excluded_incomplete_days": result.excluded_incomplete,
        "rho_high": estimate.rho_high,
        "rho_low": estimate.rho_low,
        "delta": estimate.delta,
        "confidence_level": boot.confidence_level,
        "ci_low": boot.ci_low,
        "ci_high": boot.ci_high,
        "excludes_zero": boot.excludes_zero,
        "standard_error": boot.standard_error,
        "replications": boot.replications,
        "rejected_replicates": boot.rejected,
        "mean_block_length": boot.mean_block_length,
        "pairs": pairs,
        "warnings": list(result.warnings),
    }
    if bonferroni_level is not None and boot.replicates.size >= 2:
        low, high = boot.interval(bonferroni_level)
        data["bonferroni"] = {
            "confidence_level": bonferroni_level,
            "ci_low": low,
            "ci_high": high,
            "excludes_zero": bool(low > 0 or high < 0),
        }
    return data


def interpret(
    primary: dict[str, Any], robustness: list[dict[str, Any]], validated: bool
) -> dict[str, str]:
    """Statements dictated by the protocol's decision rules."""
    delta = primary["delta"]
    level = round(primary["confidence_level"] * 100)
    if not validated:
        inference = (
            "The inference procedure did not pass the pre-specified simulation gate, so the "
            "interval is reported descriptively and no inferential statement is made."
        )
    elif primary["excludes_zero"]:
        inference = (
            f"The {level}% stationary-bootstrap interval excludes zero: evidence of a difference "
            "in average pairwise correlation between the regimes at the 5% level (approximate, "
            "conditional on the realized regime assignment)."
        )
    else:
        inference = (
            f"The {level}% stationary-bootstrap interval includes zero: no evidence of a "
            "difference with this design. This does not show that the correlations are equal."
        )
    magnitude = abs(delta) if math.isfinite(delta) else math.nan
    relevance = (
        f"The point estimate |Delta| = {magnitude:.3f} is "
        + ("at or above" if magnitude >= SMALLEST_EFFECT_OF_INTEREST else "below")
        + f" the pre-specified smallest effect of interest ({SMALLEST_EFFECT_OF_INTEREST})."
    )
    direction = "Exploratory (directional): the estimate is " + (
        "positive (higher average correlation in the high-volatility regime)."
        if delta > 0
        else "negative (lower average correlation in the high-volatility regime)."
        if delta < 0
        else "zero."
    )
    sign = math.copysign(1, delta) if delta else 0
    disagreeing = [
        item["id"]
        for item in robustness
        if item["delta"] is None
        or not math.isfinite(item["delta"])
        or math.copysign(1, item["delta"]) != sign
    ]
    robust = (
        "All pre-specified robustness estimates have the same sign as the primary estimate."
        if not disagreeing
        else "Robustness checks with a different sign or undefined estimate: "
        + ", ".join(disagreeing)
        + "."
    )
    return {
        "inference": inference,
        "relevance": relevance,
        "direction": direction,
        "robustness": robust,
    }


def experiment_to_dict(
    experiment: ExperimentResult,
    *,
    config: dict[str, Any],
    lock: dict[str, Any],
    simulation: dict[str, Any],
    synthetic_data: bool = False,
) -> dict[str, Any]:
    n_checks = len(experiment.robustness)
    bonferroni = 1 - (1 - config["bootstrap"]["confidence_level"]) / n_checks if n_checks else None
    primary = analysis_to_dict(experiment.primary, bonferroni_level=None)
    robustness = [analysis_to_dict(r, bonferroni_level=bonferroni) for r in experiment.robustness]
    return {
        "experiment_id": config["experiment"]["id"],
        "protocol_version": config["experiment"]["protocol_version"],
        "protocol_lock": lock,
        "dataset": config["dataset"],
        "synthetic_data": synthetic_data,
        "primary_estimand": experiment.primary_estimand,
        "validated": experiment.validated,
        "simulation": simulation,
        "primary": primary,
        "robustness": robustness,
        "illustration": (
            analysis_to_dict(experiment.illustration, bonferroni_level=None)
            if experiment.illustration
            else None
        ),
        "bonferroni_confidence_level": bonferroni,
        "seed": config["bootstrap"]["seed"],
        "interpretation": interpret(primary, robustness, experiment.validated),
    }


def regimes_csv(sample: PreparedSample) -> bytes:
    classification = sample.classification
    used = set(sample.dates)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["date", "proxy", "threshold", "regime", "in_sample"])
    for day in classification.proxy.index:
        label = classification.labels.loc[day]
        if not isinstance(label, str):
            continue
        writer.writerow(
            [
                day.strftime("%Y-%m-%d"),
                repr(float(classification.proxy.loc[day])),
                repr(float(classification.threshold.loc[day])),
                label,
                int(day in used),
            ]
        )
    return buffer.getvalue().encode("utf-8")


def robustness_csv(results: dict[str, Any]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "id",
            "label",
            "estimand",
            "delta",
            "ci_low",
            "ci_high",
            "bonferroni_low",
            "bonferroni_high",
            "rho_high",
            "rho_low",
            "n_high",
            "n_low",
            "n_assets",
        ]
    )
    for item in [results["primary"], *results["robustness"]]:
        bonferroni = item.get("bonferroni", {})
        writer.writerow(
            [
                item["id"],
                item["label"],
                item["spec"]["estimand"],
                repr(item["delta"]),
                repr(item["ci_low"]),
                repr(item["ci_high"]),
                repr(bonferroni.get("ci_low")) if bonferroni else "",
                repr(bonferroni.get("ci_high")) if bonferroni else "",
                repr(item["rho_high"]),
                repr(item["rho_low"]),
                item["n_high"],
                item["n_low"],
                item["n_assets"],
            ]
        )
    return buffer.getvalue().encode("utf-8")


# --- Markdown -----------------------------------------------------------------------


def _rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def validation_table(validation: dict[str, Any]) -> str:
    lines = [
        "| Scenario | Null | Estimand | Pseudo-true | Rejection rate (MC s.e.) | Coverage "
        "| Bias | Mean width | Datasets |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for item in validation["scenarios"]:
        for name, m in item["metrics"].items():
            rejection = _rate(m["rejection_rate"])
            if m["rejection_rate"] is not None:
                rejection += f" ({m['rejection_mc_se']:.3f})"
            lines.append(
                f"| {item['id']}: {item['description']} | {'yes' if item['is_null'] else 'no'} "
                f"| {name} | {_round(m['pseudo_true'])} | {rejection} | {_rate(m['coverage'])} "
                f"| {_round(m['bias'])} | {_round(m['mean_width'])} | {m['datasets']} |"
            )
    return "\n".join(lines)


def block_sensitivity_table(validation: dict[str, Any]) -> str:
    lines = [
        "| Scenario | Block length | Estimand | Rejection rate | Coverage | Mean width |",
        "|---|---|---|---|---|---|",
    ]
    for item in validation["block_sensitivity"]:
        for name, m in item["metrics"].items():
            if m["rejection_rate"] is None:
                continue
            lines.append(
                f"| {item['id']} | {item['mean_block_length']} | {name} "
                f"| {_rate(m['rejection_rate'])} | {_rate(m['coverage'])} "
                f"| {_round(m['mean_width'])} |"
            )
    return "\n".join(lines)


def gate_summary(validation: dict[str, Any]) -> str:
    lines = []
    for gate in validation["gates"]:
        status = "passed" if gate["passed"] else "failed"
        lines.append(f"- **{gate['estimand']}**: {status}")
        lines.extend(f"  - {failure}" for failure in gate["failures"])
    chosen = validation["primary_estimand"]
    lines.append(
        f"- **Decision:** primary estimand `{chosen}`."
        if chosen
        else "- **Decision:** no estimand passed; empirical results are descriptive only."
    )
    return "\n".join(lines)


def _analysis_row(item: dict[str, Any]) -> str:
    bonferroni = item.get("bonferroni")
    adj = f"[{bonferroni['ci_low']:+.4f}, {bonferroni['ci_high']:+.4f}]" if bonferroni else "—"
    return (
        f"| {item['id']} | {item['label']} | {item['spec']['estimand']} | {_round(item['delta'])} "
        f"| [{item['ci_low']:+.4f}, {item['ci_high']:+.4f}] | {adj} | {item['rho_high']:.4f} "
        f"| {item['rho_low']:.4f} | {item['n_high']}/{item['n_low']} | {item['n_assets']} |"
    )
