"""Research Lab page: presents pre-computed, hash-verified result bundles.

The page never runs the experiment or the bootstrap; results are produced by
`cryptovision-research run` and only loaded here. Nothing can be changed
from the UI, so the frozen protocol cannot be altered.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from cryptovision.research import artifacts
from cryptovision.research.exceptions import ArtifactError
from cryptovision.ui import research_charts


def experiment_bundles(results_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not results_dir.exists():
        return []
    return [
        (path, manifest)
        for path, manifest in artifacts.list_bundles(results_dir)
        if manifest.get("kind") == "experiment"
    ]


def load_bundle(path: Path, results_dir: Path) -> dict[str, Any]:
    """Load and verify a bundle. Raises ArtifactError if any file fails its hash."""
    failed = [name for name, ok, _ in artifacts.verify_bundle(path) if not ok]
    if failed:
        raise ArtifactError(f"Integrity check failed for: {', '.join(failed)}")
    results = artifacts.read_json(path, "results.json")
    simulation_dir = results_dir / results["simulation"]["bundle"]
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


def _status(results: dict[str, Any]) -> None:
    primary = results["primary"]
    if not results["validated"]:
        st.error(
            "The inference procedure did not pass the pre-specified simulation gate. "
            "All numbers on this page are descriptive only."
        )
    elif primary["excludes_zero"]:
        st.success(results["interpretation"]["inference"])
    else:
        st.info(results["interpretation"]["inference"])


def _numeric(table: pd.DataFrame, *, exclude: tuple[str, ...]) -> pd.DataFrame:
    """Missing values from JSON (None) become NaN so they display as a dash, not 'None'."""
    for column in table.columns:
        if column not in exclude:
            table[column] = pd.to_numeric(table[column], errors="coerce")
    return table


def _analysis_table(analyses: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in analyses:
        bonferroni = item.get("bonferroni") or {}
        rows.append(
            {
                "ID": item["id"],
                "Analysis": item["label"],
                "Estimand": item["spec"]["estimand"],
                "Δ": item["delta"],
                "95% low": item["ci_low"],
                "95% high": item["ci_high"],
                "Bonferroni low": bonferroni.get("ci_low"),
                "Bonferroni high": bonferroni.get("ci_high"),
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
                "Null": item["is_null"],
                "Pseudo-true Δ": metrics["pseudo_true"],
                "Rejection rate": metrics["rejection_rate"],
                "Coverage": metrics["coverage"],
                "Bias": metrics["bias"],
                "Datasets": metrics["datasets"],
            }
        )
    return _numeric(pd.DataFrame(rows).set_index("Scenario"), exclude=("Null",))


def render(results_dir: Path) -> None:
    st.title("CryptoVision")
    st.markdown("#### Research Lab")
    st.caption(
        "Results of a locally pre-specified study, loaded from verified result bundles. "
        "Nothing on this page recomputes statistics or changes the frozen protocol."
    )

    bundles = experiment_bundles(results_dir)
    if not bundles:
        st.info(
            f"No experiment results found in `{results_dir}`. Run "
            "`cryptovision-research simulate configs\\experiments\\volatility-correlation-v1.toml` "
            "and then `cryptovision-research run ...` (see docs/research-reproducibility.md)."
        )
        return

    labels = [f"{m['experiment_id']} v{m['protocol_version']} · {p.name}" for p, m in bundles]
    index = st.sidebar.selectbox(
        "Result bundle", range(len(bundles)), format_func=lambda i: labels[i]
    )
    path, _ = bundles[index]
    try:
        bundle = load_bundle(path, results_dir)
    except (ArtifactError, OSError, ValueError, KeyError) as exc:
        st.error(f"This result bundle cannot be shown: {exc}")
        return

    results, validation, manifest = bundle["results"], bundle["validation"], bundle["manifest"]
    primary = results["primary"]
    lock = results["protocol_lock"]

    if results.get("synthetic_data"):
        st.warning(
            "Synthetic data: this bundle was computed on a synthetic dataset. The numbers are "
            "not market observations or empirical findings."
        )
    _status(results)

    st.subheader("Research question")
    st.markdown(
        "Do correlations among major cryptocurrency returns differ between periods of relatively "
        "high and low market volatility?\n\n"
        "- **Estimand:** Δ = average pairwise correlation (high-volatility days) − average "
        "pairwise correlation (low-volatility days); primary estimand "
        f"`{results['primary_estimand']}`.\n"
        "- **H0:** Δ = 0 · **H1:** Δ ≠ 0 (two-sided). Δ > 0 is exploratory only.\n"
        "- **Regimes:** a strictly-past proxy (mean of the assets' 30-day lagged volatilities) "
        "split at its sample median.\n"
        "- **Inference:** stationary block bootstrap of whole days (mean block 20), 95% percentile "
        "interval, no p-value."
    )

    st.subheader("Primary result")
    cols = st.columns(4)
    cols[0].metric("Δ", f"{primary['delta']:+.4f}")
    cols[1].metric("95% interval", f"[{primary['ci_low']:+.3f}, {primary['ci_high']:+.3f}]")
    cols[2].metric("ρ̄ high / low", f"{primary['rho_high']:.3f} / {primary['rho_low']:.3f}")
    cols[3].metric("Days high / low", f"{primary['n_high']} / {primary['n_low']}")
    st.caption(
        f"{primary['n_assets']} assets, {primary['n_pairs']} unique pairs, "
        f"{primary['first_day']} to {primary['last_day']}, Binance spot closes in USDT. "
        + results["interpretation"]["relevance"]
    )

    st.subheader("Volatility regimes")
    st.plotly_chart(research_charts.regime_chart(bundle["regimes"]), width="stretch")

    st.subheader("Pairwise correlations by regime")
    st.plotly_chart(research_charts.pair_comparison_chart(primary["pairs"]), width="stretch")

    st.subheader("Primary and robustness estimates")
    analyses = [primary, *results["robustness"]]
    st.plotly_chart(research_charts.interval_chart(analyses), width="stretch")
    st.dataframe(
        _analysis_table(analyses).style.format(
            {
                column: "{:+.4f}"
                for column in ("Δ", "95% low", "95% high", "Bonferroni low", "Bonferroni high")
            }
            | {"ρ̄ high": "{:.4f}", "ρ̄ low": "{:.4f}"},
            na_rep="—",
        ),
        width="stretch",
    )
    st.caption(
        "Robustness checks are pre-specified sensitivity analyses, not separate confirmatory "
        f"tests. {results['interpretation']['robustness']}"
    )

    if validation is not None:
        st.subheader("Simulation validation (method gate)")
        estimand = results["primary_estimand"]
        st.dataframe(
            _simulation_table(validation, estimand).style.format(
                {
                    "Pseudo-true Δ": "{:+.4f}",
                    "Rejection rate": "{:.3f}",
                    "Coverage": "{:.3f}",
                    "Bias": "{:+.4f}",
                },
                na_rep="—",
            ),
            width="stretch",
        )
        for gate in validation["gates"]:
            text = f"Gate for `{gate['estimand']}`: {'passed' if gate['passed'] else 'failed'}"
            if gate["failures"]:
                text += " — " + "; ".join(gate["failures"])
            st.caption(text)

    st.subheader("Limitations")
    st.markdown(
        "- Binance spot closes in USDT for nine surviving assets; not aggregated USD prices or "
        "the whole market.\n"
        "- The lagged proxy avoids selecting days by their own returns but not composition effects "
        "of volatility clustering, time confounding or structural change.\n"
        "- Bootstrap intervals hold regime labels fixed and ignore uncertainty in the threshold.\n"
        "- No causal interpretation; see the report for all threats to validity."
    )

    with st.expander("Reproducibility metadata"):
        environment = manifest.get("environment", {})
        st.json(
            {
                "bundle": str(path),
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
                "integrity": "all files match the bundle manifest",
            }
        )

    st.download_button(
        "Download research report (Markdown)",
        data=bundle["report"],
        file_name=f"{results['experiment_id']}-report.md",
        mime="text/markdown",
        on_click="ignore",
    )
