"""Offline demo: deterministic, clearly synthetic, no network."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from cryptovision.demo import (
    DEMO_ASSETS,
    DEMO_PROVIDER,
    demo_environment,
    demo_market_snapshot,
    main,
    prepare_demo,
)
from cryptovision.research import artifacts
from cryptovision.research.exceptions import ArtifactError
from cryptovision.ui.research_view import load_bundle

NOW = datetime(2026, 10, 13, 12, 30, 45, tzinfo=UTC)


def test_demo_snapshot_is_deterministic_and_labelled():
    first, second = demo_market_snapshot(NOW), demo_market_snapshot(NOW)
    assert first == second
    assert first.provider == DEMO_PROVIDER
    assert len(first.coins) == DEMO_ASSETS
    assert all(coin.name.startswith("Synthetic Asset") for coin in first.coins)
    caps = [coin.market_cap for coin in first.coins]
    assert caps == sorted(caps, reverse=True)
    assert [coin.market_cap_rank for coin in first.coins] == list(range(1, DEMO_ASSETS + 1))
    assert first.fetched_at == NOW.replace(second=0)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """Build the demo once (synthetic dataset + demo research bundle, ~20 s)."""
    return prepare_demo(tmp_path_factory.mktemp("demo"), progress=lambda _: None)


def test_prepare_demo_builds_labelled_synthetic_artifacts(demo, mocked_api):
    manifests = list((demo.data_dir / "synthetic").glob("*/*/manifest.json"))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text(encoding="utf-8"))["synthetic"] is True

    bundles = [p for p, m in artifacts.list_bundles(demo.results_dir) if m["kind"] == "experiment"]
    assert len(bundles) == 1
    results = json.loads((bundles[0] / "results.json").read_text(encoding="utf-8"))
    assert results["synthetic_data"] is True
    assert (
        (bundles[0] / "report.md").read_text(encoding="utf-8").startswith("> **SYNTHETIC DATA.**")
    )
    assert len(mocked_api.calls) == 0


def test_prepare_demo_is_idempotent(demo):
    before = sorted(p.name for p in demo.results_dir.rglob("*"))
    again = prepare_demo(demo.root, progress=lambda _: None)
    assert again == demo
    assert sorted(p.name for p in demo.results_dir.rglob("*")) == before


def test_demo_environment_and_prepare_only(demo):
    environment = demo_environment(demo)
    assert environment["CRYPTOVISION_DEMO"] == "1"
    assert environment["CRYPTOVISION_DATA_DIR"] == str(demo.data_dir)
    assert environment["CRYPTOVISION_RESULTS_DIR"] == str(demo.results_dir)
    assert main(["--root", str(demo.root), "--prepare-only"]) == 0


def test_bundle_cannot_reference_files_outside_results_dir(tmp_path):
    results_dir = tmp_path / "results"
    bundle = results_dir / "exp" / "run"
    artifacts.write_bundle(
        bundle,
        {
            "results.json": artifacts.canonical_json({"simulation": {"bundle": "../../outside"}}),
            "regimes.csv": b"date,proxy,threshold,regime,in_sample\n",
            "report.md": b"x",
        },
        {"kind": "experiment"},
    )
    with pytest.raises(ArtifactError, match="outside the results directory"):
        load_bundle(bundle, results_dir)
