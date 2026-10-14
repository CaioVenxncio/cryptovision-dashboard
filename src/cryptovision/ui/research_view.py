"""Research Lab page: presents pre-computed, hash-verified result bundles.

The page never runs the experiment or the bootstrap; results are produced by
`cryptovision-research run` and only loaded here. Nothing can be changed
from the UI, so the frozen protocol cannot be altered.

Scientific communication rule: when the pre-specified validation gate failed,
the page says so next to the result, shows point estimates as descriptive,
and shows bootstrap intervals only on request, labelled as unvalidated
diagnostics.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from cryptovision.research import artifacts
from cryptovision.research.exceptions import ArtifactError
from cryptovision.ui import design, research_charts

FAILED_NOTICE = "Methodological validation failed — results are descriptive only."


def experiment_bundles(results_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not results_dir.exists():
        return []
    return [
        (path, manifest)
        for path, manifest in artifacts.list_bundles(results_dir)
        if manifest.get("kind") == "experiment"
    ]


def _inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


@dataclass(frozen=True)
class PreferredBundle:
    """A bundle selected by default, identified explicitly and checked against its metadata."""

    path: str  # relative to the results directory, with forward slashes
    experiment_id: str
    protocol_version: str
    protocol_fingerprint: str
    dataset_content_sha256: str
    simulation_bundle: str
    results_sha256: str  # hash of results.json recorded in the bundle manifest


# The final Phase 5 empirical result (see docs/research-reproducibility.md). Older
# bundles of the same study share its protocol and dataset metadata, so the final
# one is pinned explicitly; sort order and timestamps are never used to choose it.
FINAL_BUNDLE = PreferredBundle(
    path="volatility-correlation/v1.0-81fd40d77fd5ad96",
    experiment_id="volatility-correlation",
    protocol_version="1.0",
    protocol_fingerprint="bb7796d304e5ec482fd923db94fdd66b05d8e898c367ed9adcef29e375dfaea3",
    dataset_content_sha256="d2da4d6e7087d49b72f9b3e18a67aa72870714f3ef8a7723d4fcab62ab9d8d4e",
    simulation_bundle="simulations/volatility-correlation-v1.0/2f87de44f528d43b",
    results_sha256="b476495e8b5a75c2b5341e79d774062f47d719eebd7dd5dc999e3b0666db59b8",
)


@dataclass(frozen=True)
class DefaultSelection:
    index: int
    preferred_index: int | None = None  # set only when the preferred bundle is verified
    notice: str | None = None


def _preferred_problem(path: Path, manifest: dict[str, Any], preferred: PreferredBundle) -> str:
    """Why `path` cannot serve as the preferred bundle ("" if it can)."""
    expected = {
        "kind": "experiment",
        "experiment_id": preferred.experiment_id,
        "protocol_version": preferred.protocol_version,
        "protocol_fingerprint": preferred.protocol_fingerprint,
        "dataset_content_sha256": preferred.dataset_content_sha256,
        "simulation_bundle": preferred.simulation_bundle,
    }
    if any(manifest.get(key) != value for key, value in expected.items()) or (
        manifest.get("files", {}).get("results.json") != preferred.results_sha256
    ):
        return "does not match its recorded metadata"
    try:
        if not all(ok for _, ok, _ in artifacts.verify_bundle(path)):
            return "failed integrity verification"
    except (ArtifactError, OSError, ValueError, KeyError):
        return "failed integrity verification"
    return ""


def default_selection(
    bundles: list[tuple[Path, dict[str, Any]]],
    results_dir: Path,
    preferred: PreferredBundle | None = None,
) -> DefaultSelection:
    """Choose the bundle shown first.

    The preferred bundle is chosen when it is present and verified. Otherwise,
    if other bundles of the same study exist, the first of them is selected with
    a notice that it is not the final result. Bundles of other studies (such as
    the demo) keep the first-listed default without a notice.
    """
    preferred = preferred or FINAL_BUNDLE
    target = (results_dir / preferred.path).resolve()
    match = next((i for i, (path, _) in enumerate(bundles) if path.resolve() == target), None)
    if match is None:
        problem = "was not found"
    else:
        problem = _preferred_problem(*bundles[match], preferred)
        if not problem:
            return DefaultSelection(index=match, preferred_index=match)

    same_study = any(
        manifest.get("experiment_id") == preferred.experiment_id
        and manifest.get("protocol_version") == preferred.protocol_version
        for i, (_, manifest) in enumerate(bundles)
        if i != match
    )
    if match is None and not same_study:
        return DefaultSelection(index=0)
    others = [i for i in range(len(bundles)) if i != match]
    notice = f"The final study result (`{preferred.path}`) {problem}. " + (
        "The bundle selected below is **not** the final result; select a bundle explicitly."
        if others
        else "No other result bundle is available."
    )
    return DefaultSelection(index=others[0] if others else 0, notice=notice)


def load_bundle(path: Path, results_dir: Path) -> dict[str, Any]:
    """Load and verify a bundle. Raises ArtifactError if any file fails its hash."""
    failed = [name for name, ok, _ in artifacts.verify_bundle(path) if not ok]
    if failed:
        raise ArtifactError(f"Integrity check failed for: {', '.join(failed)}")
    results = artifacts.read_json(path, "results.json")
    simulation_dir = results_dir / results["simulation"]["bundle"]
    if not _inside(simulation_dir, results_dir):
        raise ArtifactError("The simulation reference points outside the results directory.")
    validation = (
        artifacts.read_json(simulation_dir, "validation.json")
        if (simulation_dir / "validation.json").exists()
        else None
    )
    return {
        "results": results,
        "validation": validation,
        "manifest": artifacts.read_manifest(path),
        "regimes": pd.read_csv(
            io.BytesIO((path / "regimes.csv").read_bytes()), parse_dates=["date"]
        ),
        "report": (path / "report.md").read_bytes(),
    }


def _numeric(table: pd.DataFrame, *, exclude: tuple[str, ...]) -> pd.DataFrame:
    """Missing values from JSON (None) become NaN so they display as a dash, not 'None'."""
    for column in table.columns:
        if column not in exclude:
            table[column] = pd.to_numeric(table[column], errors="coerce")
    return table


def _number_formats(
    table: pd.DataFrame, *, signed: tuple[str, ...], plain: tuple[str, ...]
) -> dict[str, object]:
    """Native number formats: values stay numeric and missing values render blank."""
    config: dict[str, object] = {}
    for column in table.columns:
        if column.startswith(signed):
            config[column] = st.column_config.NumberColumn(column, format="%+.4f")
        elif column.startswith(plain):
            config[column] = st.column_config.NumberColumn(column, format="%.4f")
    return config


def _analysis_table(analyses: list[dict[str, Any]], *, validated: bool) -> pd.DataFrame:
    interval = "95% interval" if validated else "Diagnostic interval (unvalidated)"
    rows = []
    for item in analyses:
        rows.append(
            {
                "ID": item["id"],
                "Analysis": item["label"],
                "Estimand": item["spec"]["estimand"],
                "Δ": item["delta"],
                f"{interval} low": item["ci_low"],
                f"{interval} high": item["ci_high"],
                "ρ̄ high": item["rho_high"],
                "ρ̄ low": item["rho_low"],
                "Days high": item["n_high"],
                "Days low": item["n_low"],
                "Assets": item["n_assets"],
            }
        )
    table = pd.DataFrame(rows).set_index("ID")
    return _numeric(table, exclude=("Analysis", "Estimand"))


def _simulation_table(validation: dict[str, Any], estimand: str) -> pd.DataFrame:
    rows = []
    for item in validation["scenarios"]:
        metrics = item["metrics"][estimand]
        rows.append(
            {
                "Scenario": f"{item['id']}: {item['description']}",
                "Null": "yes" if item["is_null"] else "no",
                "Pseudo-true Δ": metrics["pseudo_true"],
                "Rejection rate": metrics["rejection_rate"],
                "Coverage": metrics["coverage"],
                "Bias": metrics["bias"],
                "Datasets": metrics["datasets"],
            }
        )
    return _numeric(pd.DataFrame(rows).set_index("Scenario"), exclude=("Null",))


def _gate_reasons(validation: dict[str, Any] | None) -> list[str]:
    if not validation:
        return []
    return [
        f"{gate['estimand']}: {failure}"
        for gate in validation["gates"]
        for failure in gate["failures"]
    ]


def render(results_dir: Path) -> None:
    bundles = experiment_bundles(results_dir)
    if not bundles:
        design.page_header(
            "Research",
            "Research Lab",
            "Reproducible, pre-specified experiments on validated local datasets.",
        )
        st.info(
            "**No experiment results found.** Run `cryptovision-research simulate` and "
            "`cryptovision-research run` on configs/experiments/volatility-correlation-v1.toml "
            "(see docs/research-reproducibility.md), or start the offline demo with "
            "`cryptovision-demo`.",
            icon=":material/science:",
        )
        return

    header = st.container()
    default = default_selection(bundles, results_dir)
    labels = [f"{m['experiment_id']} v{m['protocol_version']} · {p.name}" for p, m in bundles]
    if default.preferred_index is not None:
        labels[default.preferred_index] += " · final result"
    index = st.selectbox(
        "Result bundle",
        range(len(bundles)),
        index=default.index,
        format_func=lambda i: labels[i],
    )
    if default.notice:
        st.warning(default.notice, icon=":material/warning:")
    path, _ = bundles[index]
    try:
        bundle = load_bundle(path, results_dir)
    except (ArtifactError, OSError, ValueError, KeyError) as exc:
        with header:
            design.page_header("Research", "Research Lab", "Result bundle unavailable.")
        st.error(f"This result bundle cannot be shown: {exc}", icon=":material/gpp_bad:")
        return

    results, validation, manifest = bundle["results"], bundle["validation"], bundle["manifest"]
    primary, lock = results["primary"], results["protocol_lock"]
    validated = bool(results["validated"])
    synthetic = bool(results.get("synthetic_data"))

    with header:
        tags = [("Validated", "live")] if validated else [("Descriptive only", "warn")]
        if synthetic:
            tags.insert(0, ("Synthetic", "warn"))
        design.page_header(
            "Research",
            "Research Lab",
            "A locally pre-specified study: do return correlations among major cryptocurrencies "
            "differ between high- and low-volatility regimes?",
            meta=[
                ("Protocol", f"{results['experiment_id']} v{results['protocol_version']}"),
                ("Frozen", str(lock.get("frozen_at"))),
                ("Dataset", results["dataset"]["id"]),
                ("Gate", "passed" if validated else "failed"),
                ("Estimand", results["primary_estimand"]),
            ],
            tags=tags,
        )
        if synthetic:
            design.demo_notice(
                "This bundle was computed on a synthetic dataset to demonstrate the workflow; "
                "it is not the empirical study."
            )

    if not validated:
        reasons = _gate_reasons(validation)
        st.error(
            f"**{FAILED_NOTICE}**\n\n"
            "The inference procedure was checked on synthetic data before the empirical run and "
            "did not meet its pre-specified criteria, so no inferential conclusion is drawn. "
            "Point estimates below describe this dataset only; bootstrap intervals are "
            "diagnostic outputs of an unvalidated procedure, not confidence intervals."
            + (
                f"\n\nGate failures: {'; '.join(reasons[:4])}" + (" …" if len(reasons) > 4 else "")
                if reasons
                else ""
            ),
            icon=":material/report:",
        )

    design.section("Question and design")
    left, right = st.columns(2, gap="large")
    left.markdown(
        "**Question.** Do correlations among major cryptocurrency returns differ between "
        "periods of relatively high and low market volatility?\n\n"
        "**Hypotheses.** H0: Δ = 0; H1: Δ ≠ 0 (two-sided). Δ > 0 is exploratory only.\n\n"
        "**Estimand.** Δ = average pairwise correlation on high-volatility days − average "
        f"pairwise correlation on low-volatility days ({primary['n_pairs']} pairs, "
        f"{primary['n_assets']} assets)."
    )
    right.markdown(
        "**Regimes.** A day is *high* if the mean of the assets' volatilities over the previous "
        "30 days (strictly past data) exceeds its sample median.\n\n"
        "**Inference.** Stationary block bootstrap of whole days, checked against a "
        "pre-specified simulation gate before any empirical inference.\n\n"
        f"**Data.** {primary['first_day']} to {primary['last_day']}; "
        + (
            "synthetic data."
            if synthetic
            else "Binance spot daily closes in USDT (Binance Vision, CC BY-NC-SA 4.0)."
        )
    )

    design.section(
        "Descriptive results",
        "Observed values in this dataset. " + ("" if validated else "Not an inferential result."),
    )
    cols = st.columns(4)
    cols[0].metric(
        "Observed Δ",
        f"{primary['delta']:+.4f}",
        help="High minus low average pairwise correlation (descriptive).",
    )
    cols[1].metric("Avg. correlation · high", f"{primary['rho_high']:.3f}")
    cols[2].metric("Avg. correlation · low", f"{primary['rho_low']:.3f}")
    cols[3].metric("Days high / low", f"{primary['n_high']} / {primary['n_low']}")
    st.caption(
        results["interpretation"]["relevance"]
        + (
            f" Unvalidated bootstrap interval (diagnostic only): [{primary['ci_low']:+.4f}, "
            f"{primary['ci_high']:+.4f}]."
            if not validated
            else f" 95% bootstrap interval: [{primary['ci_low']:+.4f}, {primary['ci_high']:+.4f}]."
        )
    )

    regimes = bundle["regimes"]
    high_share = (regimes["regime"] == "high").mean()
    design.section("Volatility regimes", "Shaded days were classified as high volatility.")
    design.chart(
        research_charts.regime_chart(regimes),
        summary=f"Volatility proxy over time with its threshold; {high_share:.0%} of classified "
        "days are in the high-volatility regime.",
        key="regimes",
    )

    pairs = primary["pairs"]
    higher = sum(p["difference"] > 0 for p in pairs)
    design.section("Pairwise correlations by regime")
    design.chart(
        research_charts.pair_comparison_chart(pairs),
        summary=f"For each asset pair, correlation in the low (circle) and high (diamond) "
        f"regime. {higher} of {len(pairs)} pairs are higher in the high-volatility regime "
        "(descriptive).",
        data=pd.DataFrame(pairs),
        key="pairs",
    )

    design.section(
        "Robustness checks",
        "Pre-specified sensitivity analyses; each changes one element of the design. They are "
        "not separate confirmatory tests.",
    )
    analyses = [primary, *results["robustness"]]
    show_intervals = st.toggle(
        "Show bootstrap intervals" + ("" if validated else " (unvalidated diagnostics)"),
        value=validated,
        help="Intervals from the bootstrap procedure. "
        + (
            ""
            if validated
            else "The procedure failed validation; do not read these as confidence intervals."
        ),
    )
    design.chart(
        research_charts.interval_chart(
            analyses, show_intervals=show_intervals, validated=validated
        ),
        summary=f"Point estimates of Δ for the primary analysis (diamond) and "
        f"{len(results['robustness'])} robustness checks. "
        + results["interpretation"]["robustness"],
        key="robustness",
    )
    table = _analysis_table(analyses, validated=validated)
    st.dataframe(
        table,
        width="stretch",
        placeholder="—",
        column_config=_number_formats(table, signed=("Δ", "95%", "Diagnostic"), plain=("ρ̄",)),
        alt="Primary and robustness estimates with regime averages and day counts.",
    )

    if validation is not None:
        design.section(
            "Validation gate",
            "The method was run on synthetic data with known answers before the empirical study.",
        )
        estimand = results["primary_estimand"]
        with st.expander("Simulation diagnostics (per scenario)", expanded=not validated):
            simulation = _simulation_table(validation, estimand)
            st.dataframe(
                simulation,
                width="stretch",
                placeholder="—",
                column_config=_number_formats(
                    simulation, signed=("Pseudo-true", "Bias"), plain=("Rejection", "Coverage")
                ),
                alt="Simulation scenarios with rejection rates, coverage and bias.",
            )
            for gate in validation["gates"]:
                status = "passed" if gate["passed"] else "failed"
                st.caption(
                    f"Gate for `{gate['estimand']}`: {status}"
                    + (" — " + "; ".join(gate["failures"]) if gate["failures"] else "")
                )

    design.section("Limitations")
    data_limitation = (
        "- Synthetic data generated for this demonstration; the numbers describe nothing real.\n"
        if synthetic
        else "- Binance spot closes in USDT for nine surviving assets; not aggregated USD "
        "prices or the whole market.\n"
    )
    st.markdown(
        data_limitation
        + "- The lagged proxy avoids classifying days by their own returns but not composition "
        "effects of volatility clustering, time confounding or structural change.\n"
        "- Bootstrap intervals hold regime labels fixed and ignore uncertainty in the threshold.\n"
        "- No causal interpretation. See docs/research-limitations.md."
    )

    design.section("Reproducibility")
    environment = manifest.get("environment", {})
    st.markdown(
        "Rebuild the dataset, re-validate and re-run with `cryptovision-research simulate` and "
        "`cryptovision-research run` (docs/research-reproducibility.md). This bundle's files "
        "were verified against its manifest when the page loaded."
    )
    with st.expander("Reproducibility metadata"):
        st.json(
            {
                "bundle": path.name,
                "protocol_version": results["protocol_version"],
                "protocol_frozen_at": lock.get("frozen_at"),
                "protocol_files": lock.get("files"),
                "dataset": results["dataset"]["id"],
                "dataset_content_sha256": results["dataset"]["content_sha256"],
                "simulation_bundle": results["simulation"]["bundle"],
                "seed": results.get("seed"),
                "git": environment.get("git"),
                "python": environment.get("python"),
                "created_at": manifest.get("created_at"),
            }
        )
    st.download_button(
        "Download research report (Markdown)",
        data=bundle["report"],
        file_name=f"{results['experiment_id']}-report.md",
        mime="text/markdown",
        icon=":material/description:",
        on_click="ignore",
    )
