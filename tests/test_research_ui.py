"""Research Lab page: loads verified bundles only; never computes or changes the protocol."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from cryptovision.research import artifacts
from cryptovision.research.cli import main
from cryptovision.ui import research_charts, research_view
from cryptovision.ui.research_view import (
    FAILED_NOTICE,
    FINAL_BUNDLE,
    PreferredBundle,
    default_selection,
    experiment_bundles,
    load_bundle,
)
from tests.test_research_workflow import build_project

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")
PAGE = "views/research_lab.py"


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture(scope="module")
def results(tmp_path_factory) -> Path:
    """Simulate and run once per module (synthetic data). Tests must not modify it."""
    project = build_project(tmp_path_factory.mktemp("research") / "project")
    common = [
        "--results-dir",
        str(project["results"]),
        "--data-dir",
        str(project["data"]),
        "--project-root",
        str(project["root"]),
    ]
    assert main([*common, "simulate", str(project["config"])]) == 0
    assert main([*common, "run", str(project["config"])]) == 0
    return project["results"]


def open_page(monkeypatch, results_dir: Path) -> AppTest:
    monkeypatch.setenv("CRYPTOVISION_RESULTS_DIR", str(results_dir))
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    return at.switch_page(PAGE).run()


def test_empty_results_message(monkeypatch, tmp_path, mocked_api):
    at = open_page(monkeypatch, tmp_path / "none")
    assert not at.exception
    assert any("No experiment results found" in i.value for i in at.info)
    assert len(mocked_api.calls) == 0


def test_research_page_renders_bundle(monkeypatch, results, mocked_api):
    at = open_page(monkeypatch, results)

    assert not at.exception, at.exception
    assert any("synthetic data" in w.value for w in at.warning)
    # The failed gate is stated next to the result, verbatim.
    assert any(FAILED_NOTICE in e.value for e in at.error)
    text = "\n".join(m.value for m in at.markdown)
    for section in (
        "Question and design",
        "Descriptive results",
        "Volatility regimes",
        "Pairwise correlations by regime",
        "Robustness checks",
        "Validation gate",
        "Limitations",
        "Reproducibility",
    ):
        assert f"<h2>{section}</h2>" in text
    labels = [m.label for m in at.metric]
    assert labels == [
        "Observed Δ",
        "Avg. correlation · high",
        "Avg. correlation · low",
        "Days high / low",
    ]
    assert not any("interval" in label.lower() for label in labels)  # no CI as a headline
    # Intervals are hidden by default when the method is not validated.
    assert at.toggle[0].value is False
    assert "unvalidated" in at.toggle[0].label
    assert len(mocked_api.calls) == 0  # offline


def test_tampered_bundle_is_not_shown(monkeypatch, results, mocked_api, tmp_path):
    copy = tmp_path / "results"
    shutil.copytree(results, copy)
    bundle = experiment_bundles(copy)[0][0]
    (bundle / "regimes.csv").write_text("date,proxy")
    at = open_page(monkeypatch, copy)
    assert any("cannot be shown" in e.value for e in at.error)


def test_load_bundle_and_charts(results):
    path, _ = experiment_bundles(results)[0]
    bundle = load_bundle(path, results)
    assert bundle["validation"] is not None
    regimes = bundle["regimes"]
    assert set(regimes["regime"]) == {"high", "low"}
    assert pd.api.types.is_datetime64_any_dtype(regimes["date"])

    figure = research_charts.regime_chart(regimes)
    assert [t.name for t in figure.data][1:] == [
        "Volatility proxy (mean lagged 30-day)",
        "Threshold",
    ]

    analyses = [bundle["results"]["primary"], *bundle["results"]["robustness"]]
    forest = research_charts.interval_chart(analyses)
    assert list(forest.data[0].x) == [a["delta"] for a in analyses]
    assert forest.data[0].y[0].startswith("primary")

    pairs = research_charts.pair_comparison_chart(bundle["results"]["primary"]["pairs"])
    assert len(pairs.data[0].y) == 3


def test_experiment_bundles_skip_simulations(results):
    kinds = {m["kind"] for _, m in artifacts.list_bundles(results)}
    assert kinds == {"simulation", "experiment"}
    assert len(experiment_bundles(results)) == 1


# --- Default bundle selection ----------------------------------------------------------

STUDY = {
    "kind": "experiment",
    "experiment_id": "volatility-correlation",
    "protocol_version": "1.0",
    "protocol_fingerprint": "f" * 64,
    "dataset_content_sha256": "d" * 64,
}


def write_study_bundle(results_dir: Path, relative: str, *, simulation: str = "sim/a") -> Path:
    """A minimal experiment bundle; only its manifest metadata and hashes matter here."""
    path = results_dir / relative
    files = {"results.json": artifacts.canonical_json({"run": relative}), "report.md": b"r"}
    artifacts.write_bundle(path, files, {**STUDY, "simulation_bundle": simulation})
    return path


def preferred_for(path: Path, results_dir: Path) -> PreferredBundle:
    manifest = artifacts.read_manifest(path)
    return PreferredBundle(
        path=path.relative_to(results_dir).as_posix(),
        experiment_id=manifest["experiment_id"],
        protocol_version=manifest["protocol_version"],
        protocol_fingerprint=manifest["protocol_fingerprint"],
        dataset_content_sha256=manifest["dataset_content_sha256"],
        simulation_bundle=manifest["simulation_bundle"],
        results_sha256=manifest["files"]["results.json"],
    )


@pytest.fixture
def study(tmp_path):
    """Two valid bundles of one study; the final one sorts last."""
    results_dir = tmp_path / "results"
    older = write_study_bundle(results_dir, "volatility-correlation/v1.0-0000older")
    final = write_study_bundle(
        results_dir, "volatility-correlation/v1.0-ffffinal", simulation="sim/b"
    )
    return results_dir, older, final


def test_preferred_bundle_is_default_among_multiple_valid_bundles(study):
    results_dir, older, final = study
    bundles = experiment_bundles(results_dir)
    assert [p for p, _ in bundles] == [older, final]  # path order would pick the older one

    choice = default_selection(bundles, results_dir, preferred_for(final, results_dir))
    assert bundles[choice.index][0] == final
    assert choice.preferred_index == choice.index
    assert choice.notice is None
    assert len(bundles) == 2


def test_missing_preferred_bundle_is_reported_not_replaced_silently(study):
    results_dir, older, final = study
    preferred = dataclasses.replace(
        preferred_for(final, results_dir), path="volatility-correlation/v1.0-missing"
    )
    bundles = experiment_bundles(results_dir)
    choice = default_selection(bundles, results_dir, preferred)
    assert choice.preferred_index is None
    assert "was not found" in choice.notice
    assert "**not** the final result" in choice.notice


def test_tampered_preferred_bundle_is_not_default(study):
    results_dir, older, final = study
    preferred = preferred_for(final, results_dir)
    (final / "report.md").write_bytes(b"changed")
    bundles = experiment_bundles(results_dir)
    choice = default_selection(bundles, results_dir, preferred)
    assert bundles[choice.index][0] == older
    assert choice.preferred_index is None
    assert "failed integrity verification" in choice.notice
    assert "**not** the final result" in choice.notice


def test_preferred_bundle_with_other_metadata_is_not_default(study):
    results_dir, older, final = study
    preferred = dataclasses.replace(preferred_for(final, results_dir), results_sha256="0" * 64)
    choice = default_selection(experiment_bundles(results_dir), results_dir, preferred)
    assert choice.preferred_index is None
    assert "does not match its recorded metadata" in choice.notice


def test_only_an_invalid_preferred_bundle(tmp_path):
    results_dir = tmp_path / "results"
    final = write_study_bundle(results_dir, "volatility-correlation/v1.0-final")
    preferred = preferred_for(final, results_dir)
    (final / "extra.txt").write_text("not in manifest")
    choice = default_selection(experiment_bundles(results_dir), results_dir, preferred)
    assert choice.index == 0 and choice.preferred_index is None
    assert "No other result bundle is available" in choice.notice


def test_other_studies_keep_first_listed_default_without_notice(tmp_path):
    # The demo uses its own experiment id; its behavior is unchanged.
    results_dir = tmp_path / "results"
    path = results_dir / "demo-volatility-correlation" / "v1.0-x"
    artifacts.write_bundle(path, {"report.md": b"r"}, {**STUDY, "experiment_id": "demo-x"})
    choice = default_selection(experiment_bundles(results_dir), results_dir)
    assert choice == research_view.DefaultSelection(index=0)


def test_final_bundle_pin_matches_local_results_when_present():
    results_dir = Path(__file__).resolve().parents[1] / "research" / "results"
    if not (results_dir / FINAL_BUNDLE.path / "manifest.json").exists():
        pytest.skip("final research bundle not available locally")
    bundles = experiment_bundles(results_dir)
    choice = default_selection(bundles, results_dir)
    assert choice.notice is None
    assert bundles[choice.index][0] == (results_dir / FINAL_BUNDLE.path)


def test_page_selects_preferred_bundle_and_keeps_others(monkeypatch, results, mocked_api, tmp_path):
    copy = tmp_path / "results"
    shutil.copytree(results, copy)
    final = experiment_bundles(copy)[0][0]
    write_study_bundle(copy, "aaa-older/v1.0-0")  # sorts first, same study id
    monkeypatch.setattr(research_view, "FINAL_BUNDLE", preferred_for(final, copy))

    at = open_page(monkeypatch, copy)
    assert not at.exception, at.exception
    box = at.selectbox[0]
    assert len(box.options) == 2
    assert box.value == 1 and box.options[1].endswith("· final result")
    assert any(FAILED_NOTICE in e.value for e in at.error)
    assert not any("final study result" in w.value for w in at.warning)


def test_page_warns_when_final_bundle_is_missing(monkeypatch, results, mocked_api, tmp_path):
    copy = tmp_path / "results"
    shutil.copytree(results, copy)
    final = experiment_bundles(copy)[0][0]
    missing = dataclasses.replace(preferred_for(final, copy), path="nowhere/v1.0-x")
    monkeypatch.setattr(research_view, "FINAL_BUNDLE", missing)

    at = open_page(monkeypatch, copy)
    assert not at.exception, at.exception
    assert any("was not found" in w.value for w in at.warning)
