"""Research Lab page: loads verified bundles only; never computes or changes the protocol."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from cryptovision.research import artifacts
from cryptovision.research.cli import main
from cryptovision.ui import research_charts
from cryptovision.ui.research_view import FAILED_NOTICE, experiment_bundles, load_bundle
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
