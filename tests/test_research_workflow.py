"""Configuration, protocol freezing, simulation gate, artifacts, report and CLI (synthetic data)."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from cryptovision.data import pipeline
from cryptovision.data.synthetic import generate_synthetic_ohlcv, synthetic_config
from cryptovision.research import artifacts
from cryptovision.research.cli import main
from cryptovision.research.config import (
    ExperimentConfig,
    SimulationSettings,
    load_experiment_config,
    other_estimand,
)
from cryptovision.research.exceptions import (
    ArtifactError,
    ExperimentConfigError,
    ProtocolIntegrityError,
)
from cryptovision.research.protocol import (
    file_sha256,
    freeze,
    lock_path,
    read_lock,
    require_intact,
    verify_lock,
)
from cryptovision.research.reporting import interpret
from cryptovision.research.simulation import (
    SCENARIOS,
    EstimandMetrics,
    Scenario,
    ScenarioResult,
    evaluate_gate,
    simulate_returns,
)

REPO = Path(__file__).resolve().parents[1]
REAL_CONFIG = REPO / "configs" / "experiments" / "volatility-correlation-v1.toml"


# --- Configuration ------------------------------------------------------------------


def test_real_config_and_robustness_specs():
    config = load_experiment_config(REAL_CONFIG)
    assert config.experiment.protocol_version == "1.0"
    assert len(config.dataset.assets) == 9
    assert [c.id for c in config.robustness] == [f"R{i}" for i in range(1, 12)]
    primary = config.primary_spec()
    assert (primary.estimand, primary.lookback_days, primary.quantile) == ("raw", 30, 0.5)
    by_id = {c.id: c for c in config.robustness}
    assert config.robustness_spec(by_id["R2"], primary_estimand="raw").correlation == "spearman"
    assert config.robustness_spec(by_id["R6"], primary_estimand="raw").mean_block_length == 10
    assert config.robustness_spec(by_id["R10"], primary_estimand="raw").exclude_assets == (
        "binancecoin",
    )
    # R11 is always the estimand that is not primary.
    assert config.robustness_spec(by_id["R11"], primary_estimand="raw").estimand == "devolatilized"
    assert config.robustness_spec(by_id["R11"], primary_estimand="devolatilized").estimand == "raw"
    assert config.illustration_spec(primary_estimand="raw").contemporaneous is True
    assert other_estimand("raw") == "devolatilized"


def _document() -> dict:
    import tomllib

    return tomllib.loads(REAL_CONFIG.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["robustness"].append({"id": "R1", "label": "dup"}), "unique"),
        (
            lambda d: d["robustness"].append({"id": "X", "label": "x", "bogus": 1}),
            "unknown override",
        ),
        (
            lambda d: d["robustness"].append({"id": "X", "label": "x", "exclude_assets": ["zzz"]}),
            "not in the universe",
        ),
        (lambda d: d["primary"].update(fallback_estimand="raw"), "fallback"),
        (lambda d: d["primary"].update(proxy="asset_volatility", proxy_asset="zzz"), "proxy_asset"),
        (lambda d: d["bootstrap"].update(replications=10), "replications"),
        (lambda d: d["dataset"].update(content_sha256="abc"), "content_sha256"),
    ],
)
def test_invalid_configs_are_rejected(mutate, message):
    document = _document()
    mutate(document)
    with pytest.raises(ValueError, match=message):
        ExperimentConfig.model_validate(document)


def test_config_file_errors(tmp_path):
    with pytest.raises(ExperimentConfigError, match="Cannot read"):
        load_experiment_config(tmp_path / "missing.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("[experiment\n")
    with pytest.raises(ExperimentConfigError, match="Invalid TOML"):
        load_experiment_config(bad)
    bad.write_text("[experiment]\nid = 'x'\n")
    with pytest.raises(ExperimentConfigError, match="Invalid experiment config"):
        load_experiment_config(bad)


# --- Protocol freezing --------------------------------------------------------------


def test_real_protocol_lock_is_intact():
    lock = read_lock(lock_path(REAL_CONFIG))
    assert verify_lock(lock, REPO) == []
    assert lock.data["empirical_regime_statistics_seen_before_freeze"] is False
    assert len(lock.fingerprint) == 64


def test_freeze_verify_and_tamper_detection(tmp_path):
    protocol = tmp_path / "protocol.md"
    protocol.write_bytes(b"line one\r\nline two\r\n")
    lf_copy = tmp_path / "lf.md"
    lf_copy.write_bytes(b"line one\nline two\n")
    assert file_sha256(protocol) == file_sha256(lf_copy)  # line endings do not matter

    destination = tmp_path / "x.lock.json"
    lock = freeze(
        protocol_id="x",
        protocol_version="1.0",
        files=[protocol],
        root=tmp_path,
        destination=destination,
        repository_head="abc",
        empirical_results_seen=False,
    )
    assert verify_lock(lock, tmp_path) == []
    with pytest.raises(ProtocolIntegrityError, match="immutable"):
        freeze(
            protocol_id="x",
            protocol_version="1.0",
            files=[protocol],
            root=tmp_path,
            destination=destination,
            repository_head="abc",
            empirical_results_seen=False,
        )
    protocol.write_text("changed")
    assert verify_lock(lock, tmp_path) == ["protocol.md: modified after freezing"]
    with pytest.raises(ProtocolIntegrityError, match="new protocol version"):
        require_intact(lock, tmp_path)
    protocol.unlink()
    assert verify_lock(lock, tmp_path) == ["protocol.md: missing"]
    with pytest.raises(ProtocolIntegrityError, match="freeze the protocol"):
        read_lock(tmp_path / "missing.lock.json")


# --- Simulation ---------------------------------------------------------------------


SETTINGS = SimulationSettings(
    n_assets=3,
    n_days=600,
    short_n_days=300,
    replications=10,
    bootstrap_replications=99,
    mean_block_length=10,
    block_sensitivity=(5,),
    pseudo_true_days=10_000,
    seed=1,
    daily_scale=0.03,
)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_simulated_processes_have_expected_shapes(scenario):
    returns = simulate_returns(scenario, 400, 3, 0.03, np.random.default_rng(0))
    assert returns.shape == (400, 3)
    if scenario.missing_fraction:
        assert 0.02 < np.isnan(returns).mean() < 0.09
    else:
        assert np.isfinite(returns).all()


def test_simulated_constant_correlation_is_recovered():
    scenario = next(s for s in SCENARIOS if s.id == "N2")
    returns = simulate_returns(scenario, 50_000, 3, 0.03, np.random.default_rng(1))
    corr = np.corrcoef(returns.T)[np.triu_indices(3, 1)]
    np.testing.assert_allclose(corr, 0.5, atol=0.02)


def test_factor_scenario_has_state_dependent_correlation():
    scenario = Scenario(
        "A",
        "factor",
        False,
        "factor_markov",
        {"factor_var_low": 0.5, "factor_var_high": 2.0, "stay": 0.99},
    )
    returns = simulate_returns(scenario, 80_000, 2, 1.0, np.random.default_rng(2))
    # Unconditional mixture: average factor variance 1.25 -> corr = 1.25 / 2.25.
    assert np.corrcoef(returns.T)[0, 1] == pytest.approx(1.25 / 2.25, abs=0.02)


def _result(
    sid: str, is_null: bool, pseudo: float, rejection: float, coverage: float
) -> ScenarioResult:
    metrics = EstimandMetrics(pseudo, rejection, coverage, 0.0, pseudo, 0.1, 100)
    return ScenarioResult(Scenario(sid, sid, is_null, "constant"), 20, 180, 0, {"raw": metrics})


def test_gate_rules():
    from cryptovision.research.config import GateSettings

    gate = GateSettings(
        max_null_rejection_rate=0.10, max_abs_pseudo_true_null=0.02, min_coverage=0.85
    )
    passing = [_result("N1", True, 0.0, 0.05, 0.95), _result("A1", False, 0.2, 0.9, 0.9)]
    assert evaluate_gate(passing, "raw", gate).passed
    failures = evaluate_gate(
        [
            _result("N1", True, 0.0, 0.2, 0.9),  # G1
            _result("N2", True, 0.05, 0.0, 0.9),  # G2 (G1 not evaluated)
            _result("A1", False, 0.2, 0.9, 0.5),  # G3
            _result("N3", True, math.nan, math.nan, math.nan),  # inapplicable
        ],
        "raw",
        gate,
    ).failures
    assert [f.split(":")[0] for f in failures] == ["G1 N1", "G2 N2", "G3 A1", "N3"]


# --- Interpretation rules -----------------------------------------------------------


def _analysis(delta, low, high, aid="primary"):
    return {
        "id": aid,
        "delta": delta,
        "ci_low": low,
        "ci_high": high,
        "confidence_level": 0.95,
        "excludes_zero": low > 0 or high < 0,
    }


def test_interpretation_follows_decision_rules():
    robustness = [_analysis(0.05, 0.01, 0.1, "R1"), _analysis(-0.01, -0.05, 0.02, "R2")]
    positive = interpret(_analysis(0.08, 0.02, 0.14), robustness, True)
    assert "excludes zero" in positive["inference"]
    assert "at or above" in positive["relevance"]
    assert positive["direction"].startswith("Exploratory") and "positive" in positive["direction"]
    assert "R2" in positive["robustness"]

    null = interpret(_analysis(0.01, -0.03, 0.05), [], True)
    assert "no evidence of a difference" in null["inference"]
    assert "does not show that the correlations are equal" in null["inference"]
    assert "below" in null["relevance"]
    assert "same sign" in null["robustness"]

    unvalidated = interpret(_analysis(0.08, 0.02, 0.14), [], False)
    assert "no inferential statement" in unvalidated["inference"]


# --- Artifacts ----------------------------------------------------------------------


def test_bundles_are_atomic_immutable_and_verifiable(tmp_path):
    directory = tmp_path / "exp" / "run1"
    files = {"results.json": artifacts.canonical_json({"x": 1.5, "nan": math.nan}), "a.csv": b"1\n"}
    written = artifacts.write_bundle(directory, files, {"kind": "experiment"})
    assert written.created
    assert json.loads((directory / "results.json").read_text())["nan"] is None
    assert all(ok for _, ok, _ in artifacts.verify_bundle(directory))

    again = artifacts.write_bundle(directory, files, {"kind": "experiment"})
    assert not again.created and again.identical
    different = artifacts.write_bundle(directory, {**files, "a.csv": b"2\n"}, {})
    assert not different.identical and different.differences == ("a.csv: content differs",)
    assert (directory / "a.csv").read_bytes() == b"1\n"  # never overwritten

    (directory / "a.csv").write_bytes(b"tampered")
    (directory / "extra.txt").write_text("x")
    failed = {name for name, ok, _ in artifacts.verify_bundle(directory) if not ok}
    assert failed == {"a.csv", "extra.txt"}
    with pytest.raises(ArtifactError):
        artifacts.write_bundle(tmp_path / "y", {"manifest.json": b""}, {})
    with pytest.raises(ArtifactError):
        artifacts.read_manifest(tmp_path / "nowhere")
    assert artifacts.content_id({"a": 1}) == artifacts.content_id({"a": 1})
    assert artifacts.content_id({"a": 1}) != artifacts.content_id({"a": 2})


def test_failed_bundle_write_leaves_nothing(tmp_path, monkeypatch):
    def broken(path, data):
        raise OSError("disk full")

    monkeypatch.setattr(artifacts, "atomic_write_bytes", broken)
    with pytest.raises(OSError):
        artifacts.write_bundle(tmp_path / "run", {"a.txt": b"x"}, {})
    assert list(tmp_path.iterdir()) == []


# --- CLI end to end (synthetic) -------------------------------------------------------

PROTOCOL_TEXT = "# Test protocol\n\nSynthetic end-to-end test of the research workflow.\n"


@pytest.fixture
def project(tmp_path) -> dict:
    return build_project(tmp_path / "project")


def build_project(root: Path) -> dict:
    """A temporary project root with a synthetic dataset, a config and a frozen protocol."""
    data_dir = root / "data"
    days = 620
    syn_config = synthetic_config(start=date(2022, 1, 1), days=days, seed=5, with_anomalies=False)
    frame = generate_synthetic_ohlcv(start=date(2022, 1, 1), days=days, seed=5)
    plan = pipeline.plan_dataset(syn_config, data_dir)
    stored = pipeline.store_dataset(
        plan,
        pipeline.CollectedData(frame=frame, source={"name": "synthetic"}),
        config_sha256="0" * 64,
        replace=False,
    )
    document = _document()
    document["experiment"]["protocol_path"] = "research/protocols/test-v1.md"
    document["dataset"] = {
        "id": stored.manifest.dataset_id,
        "version": stored.manifest.dataset_version,
        "content_sha256": stored.manifest.content_sha256,
        "assets": ["synthetic-a", "synthetic-b", "synthetic-c"],
        "start": "2022-01-01",
        "end": str(plan.end),
    }
    document["primary"]["evaluation_start"] = "2022-01-01"
    document["bootstrap"]["replications"] = 200
    document["robustness"] = [
        {"id": "R2", "label": "Spearman correlation", "correlation": "spearman"},
        {"id": "R11", "label": "Alternative estimand", "estimand": "alternative"},
    ]
    document["simulation"] = SETTINGS.model_dump(mode="json")
    config_path = root / "configs" / "experiments" / "test-v1.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(_to_toml(document), encoding="utf-8")
    protocol = root / "research" / "protocols" / "test-v1.md"
    protocol.parent.mkdir(parents=True)
    protocol.write_text(PROTOCOL_TEXT, encoding="utf-8")
    freeze(
        protocol_id="volatility-correlation",
        protocol_version="1.0",
        files=[protocol, config_path],
        root=root,
        destination=lock_path(config_path),
        repository_head="test",
        empirical_results_seen=False,
    )
    return {"root": root, "config": config_path, "data": data_dir, "results": root / "results"}


def _to_toml(document: dict) -> str:
    def value(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int | float):
            return repr(v)
        if isinstance(v, list | tuple):
            return "[" + ", ".join(value(x) for x in v) + "]"
        if isinstance(v, date):
            return v.isoformat()
        text = str(v)
        if len(text) == 10 and text[4] == "-" and text[7] == "-" and text[:4].isdigit():
            return text  # TOML date
        return json.dumps(text)

    lines = []
    for section in (
        "experiment",
        "dataset",
        "primary",
        "bootstrap",
        "illustration",
        "simulation",
        "gate",
    ):
        lines.append(f"[{section}]")
        lines += [f"{k} = {value(v)}" for k, v in document[section].items()]
    for check in document["robustness"]:
        lines.append("[[robustness]]")
        lines += [f"{k} = {value(v)}" for k, v in check.items()]
    return "\n".join(lines) + "\n"


def cli(project, capsys, *args) -> tuple[int, str]:
    code = main(
        [
            "--results-dir",
            str(project["results"]),
            "--data-dir",
            str(project["data"]),
            "--project-root",
            str(project["root"]),
            *[str(a) for a in args],
        ]
    )
    out = capsys.readouterr()
    return code, out.out + out.err


def test_cli_end_to_end_on_synthetic_data(project, capsys):
    config = project["config"]
    code, out = cli(project, capsys, "validate", config)
    assert code == 0 and "Protocol intact." in out

    code, out = cli(project, capsys, "run", config)
    assert code == 1 and "Run 'simulate' first" in out

    code, out = cli(project, capsys, "simulate", config)
    assert code == 0, out
    assert "Simulation bundle" in out and "Decision" in out
    code, out = cli(project, capsys, "simulate", config)
    assert "already exist" in out

    code, out = cli(project, capsys, "plan", config)
    assert code == 0 and "Gate result:   present" in out

    code, out = cli(project, capsys, "run", config)
    assert code == 0, out
    assert "Primary (" in out and "Delta =" in out
    bundle = next(
        p for p, m in artifacts.list_bundles(project["results"]) if m["kind"] == "experiment"
    )
    results = json.loads((bundle / "results.json").read_text())
    assert results["synthetic_data"] is True
    assert results["primary"]["n_pairs"] == 3
    assert [r["id"] for r in results["robustness"]] == ["R2", "R11"]
    report = (bundle / "report.md").read_text(encoding="utf-8")
    assert report.startswith("> **SYNTHETIC DATA.**")
    assert "Forbes, K. J., & Rigobon, R. (2002)" in report

    # Rerunning reproduces byte-identical result files without overwriting.
    code, out = cli(project, capsys, "run", config)
    assert code == 0 and "identical results" in out

    code, out = cli(project, capsys, "verify", bundle)
    assert code == 0 and "0 failed" in out
    code, out = cli(project, capsys, "show", bundle)
    assert code == 0 and "primary" in out
    code, out = cli(project, capsys, "report", bundle)
    assert code == 0 and "## 8. Results" in out
    target = project["root"] / "report-copy.md"
    code, out = cli(project, capsys, "report", bundle, "--output", target)
    assert code == 0 and target.exists()
    code, out = cli(project, capsys, "report", bundle, "--output", bundle / "x.md")
    assert code == 1 and "outside the immutable bundle" in out
    code, out = cli(project, capsys, "list")
    assert "experiment" in out and "simulation" in out

    (bundle / "results.json").write_text("{}")
    code, out = cli(project, capsys, "verify", bundle)
    assert code == 1 and "FAIL results.json" in out


def test_cli_refuses_modified_protocol(project, capsys):
    protocol = project["root"] / "research" / "protocols" / "test-v1.md"
    protocol.write_text(PROTOCOL_TEXT + "edited after freezing\n", encoding="utf-8")
    code, out = cli(project, capsys, "validate", project["config"])
    assert code == 1 and "NOT intact" in out
    code, out = cli(project, capsys, "simulate", project["config"])
    assert code == 1 and "new protocol version" in out


def test_cli_errors(project, capsys, tmp_path):
    code, out = cli(project, capsys, "validate", tmp_path / "missing.toml")
    assert code == 1 and "Cannot read" in out
    code, out = cli(project, capsys, "list")
    assert "No result bundles" in out
    with pytest.raises(SystemExit):
        main([])


def test_canonical_json_handles_numpy_and_dates():
    data = {
        "int": np.int64(3),
        "float": np.float64(0.25),
        "inf": np.float64(np.inf),
        "flag": np.bool_(True),
        "array": np.array([1.0, np.nan]),
        "day": date(2024, 1, 2),
    }
    decoded = json.loads(artifacts.canonical_json(data))
    assert decoded == {
        "array": [1.0, None],
        "day": "2024-01-02",
        "flag": True,
        "float": 0.25,
        "inf": None,
        "int": 3,
    }
    with pytest.raises(TypeError):
        artifacts.canonical_json({"x": object()})


def test_git_state_outside_a_repository(tmp_path):
    assert artifacts.git_state(tmp_path) == {"commit": None, "working_tree_dirty": None}
    environment = artifacts.environment(REPO)
    assert set(environment) >= {"cryptovision", "python", "numpy", "pandas", "git"}
