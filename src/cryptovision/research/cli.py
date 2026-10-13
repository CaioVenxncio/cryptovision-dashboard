"""`cryptovision-research`: offline commands for the Research Lab.

Nothing runs on import. `simulate` and `run` are the only commands that
compute statistics; both write immutable result bundles and never overwrite.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cryptovision.analytics.exceptions import AnalyticsError
from cryptovision.data.errors import DataPipelineError
from cryptovision.research import artifacts
from cryptovision.research.config import ExperimentConfig, load_experiment_config
from cryptovision.research.exceptions import GateNotPassedError, ResearchError
from cryptovision.research.experiment import load_returns, locate_dataset, run_experiment
from cryptovision.research.protocol import (
    file_sha256,
    lock_path,
    read_lock,
    require_intact,
    verify_lock,
)
from cryptovision.research.report_document import render_report
from cryptovision.research.reporting import (
    experiment_to_dict,
    regimes_csv,
    robustness_csv,
)
from cryptovision.research.simulation import run_validation, validation_to_dict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
QUICK_REPLICATIONS, QUICK_BOOTSTRAP = 20, 99


def _root(config_path: Path) -> Path:
    return config_path.resolve().parents[2]


def _load(config_path: Path) -> tuple[ExperimentConfig, Any, Path]:
    config = load_experiment_config(config_path)
    root = _root(config_path)
    lock = read_lock(lock_path(config_path))
    return config, lock, root


def simulation_payload(config: ExperimentConfig, lock, *, quick: bool) -> dict[str, Any]:
    return {
        "protocol_fingerprint": lock.fingerprint,
        "simulation": config.simulation.model_dump(mode="json"),
        "gate": config.gate.model_dump(mode="json"),
        "template": config.primary_spec().model_dump(mode="json"),
        "estimands": [config.primary.estimand, config.primary.fallback_estimand],
        "software": artifacts.environment(PROJECT_ROOT)["cryptovision"],
        "quick": quick,
    }


def simulation_dir(results_dir: Path, config: ExperimentConfig, lock, *, quick: bool) -> Path:
    payload = simulation_payload(config, lock, quick=quick)
    folder = f"{config.experiment.id}-v{config.experiment.protocol_version}"
    return results_dir / "simulations" / folder / artifacts.content_id(payload)


def cmd_validate(args: argparse.Namespace) -> int:
    config, lock, root = _load(args.config)
    problems = verify_lock(lock, root)
    print(f"Config valid: {config.experiment.id} protocol v{config.experiment.protocol_version}")
    print(f"Robustness checks: {len(config.robustness)}")
    print(f"Protocol lock: {lock.path} (frozen {lock.frozen_at})")
    for problem in problems:
        print(f"  CHANGED {problem}")
    print("Protocol intact." if not problems else "Protocol NOT intact.")
    return 0 if not problems else 1


def cmd_plan(args: argparse.Namespace) -> int:
    config, lock, root = _load(args.config)
    require_intact(lock, root)
    spec = config.primary_spec()
    sim = config.simulation
    print(f"Experiment:    {config.experiment.id} (protocol v{config.experiment.protocol_version})")
    print(f"Frozen:        {lock.frozen_at}  fingerprint {lock.fingerprint[:16]}")
    print(f"Dataset:       {config.dataset.id} v{config.dataset.version}")
    print(f"               content {config.dataset.content_sha256}")
    print(f"Assets:        {', '.join(config.dataset.assets)}")
    print(
        f"Primary:       estimand={spec.estimand} (fallback {config.primary.fallback_estimand}), "
        f"{spec.return_type} returns, {spec.correlation}, proxy={spec.proxy} "
        f"{spec.lookback_days}d, threshold={spec.threshold} q={spec.quantile}"
    )
    print(
        f"Bootstrap:     stationary, B={config.bootstrap.replications}, mean block "
        f"{config.bootstrap.mean_block_length}, {config.bootstrap.confidence_level:.0%}, "
        f"seed {config.bootstrap.seed}"
    )
    print(f"Robustness:    {', '.join(f'{c.id} {c.label}' for c in config.robustness)}")
    print(
        f"Simulation:    {sim.replications} datasets x {sim.bootstrap_replications} replicates "
        f"per scenario, seed {sim.seed}"
    )
    sim_dir = simulation_dir(args.results_dir, config, lock, quick=False)
    print(f"Gate result:   {'present' if sim_dir.exists() else 'missing'} ({sim_dir})")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    config, lock, root = _load(args.config)
    require_intact(lock, root)
    settings = config.simulation
    if args.quick:
        settings = settings.model_copy(
            update={"replications": QUICK_REPLICATIONS, "bootstrap_replications": QUICK_BOOTSTRAP}
        )
    directory = simulation_dir(args.results_dir, config, lock, quick=args.quick)
    if directory.exists():
        print(f"Simulation results already exist: {directory}")
        return 0
    started = time.perf_counter()
    validation = run_validation(
        config.primary_spec(),
        settings,
        config.gate,
        primary=config.primary.estimand,
        fallback=config.primary.fallback_estimand,
        progress=print if args.verbose else (lambda _: None),
    )
    data = validation_to_dict(validation)
    data["quick"] = args.quick
    data["runtime_seconds"] = round(time.perf_counter() - started, 1)
    written = artifacts.write_bundle(
        directory,
        {
            "validation.json": artifacts.canonical_json(
                {k: v for k, v in data.items() if k != "runtime_seconds"}
            )
        },
        {
            "kind": "simulation",
            "experiment_id": config.experiment.id,
            "protocol_version": config.experiment.protocol_version,
            "protocol_fingerprint": lock.fingerprint,
            "quick": args.quick,
            "runtime_seconds": data["runtime_seconds"],
            "environment": artifacts.environment(PROJECT_ROOT),
        },
    )
    print(f"Simulation bundle: {written.path} ({data['runtime_seconds']} s)")
    for gate in data["gates"]:
        print(f"  Gate {gate['estimand']}: {'passed' if gate['passed'] else 'FAILED'}")
        for failure in gate["failures"]:
            print(f"    {failure}")
    chosen = data["primary_estimand"]
    print(f"Decision: {'primary estimand ' + chosen if chosen else 'descriptive only'}")
    if args.quick:
        print("Quick mode: reduced settings; not usable as the gate for 'run'.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config, lock, root = _load(args.config)
    require_intact(lock, root)
    sim_dir = simulation_dir(args.results_dir, config, lock, quick=False)
    if not sim_dir.exists():
        raise GateNotPassedError(
            "No full simulation result for this frozen protocol. Run 'simulate' first."
        )
    validation = artifacts.read_json(sim_dir, "validation.json")
    estimand = validation["primary_estimand"] or config.primary.estimand
    validated = bool(validation["validated"])

    dataset_dir = locate_dataset(args.data_dir, config)
    started = time.perf_counter()
    returns_by_type, context = load_returns(dataset_dir, config)
    experiment = run_experiment(
        config, returns_by_type, primary_estimand=estimand, validated=validated
    )
    simulation_ref = {
        "bundle": sim_dir.relative_to(args.results_dir).as_posix(),
        "primary_estimand": validation["primary_estimand"],
        "validated": validated,
        "gates": validation["gates"],
    }
    results = experiment_to_dict(
        experiment,
        config=config.model_dump(mode="json"),
        lock=lock.data,
        simulation=simulation_ref,
        synthetic_data=context.synthetic,
    )
    runtime = round(time.perf_counter() - started, 1)
    run_id = artifacts.content_id(
        {
            "protocol_fingerprint": lock.fingerprint,
            "dataset": config.dataset.content_sha256,
            "simulation": sim_dir.name,
            "software": artifacts.environment(PROJECT_ROOT)["cryptovision"],
        }
    )
    directory = (
        args.results_dir / config.experiment.id / f"v{config.experiment.protocol_version}-{run_id}"
    )
    manifest = {
        "kind": "experiment",
        "experiment_id": config.experiment.id,
        "protocol_version": config.experiment.protocol_version,
        "protocol_fingerprint": lock.fingerprint,
        "dataset_content_sha256": config.dataset.content_sha256,
        "simulation_bundle": simulation_ref["bundle"],
        "runtime_seconds": runtime,
        "environment": artifacts.environment(PROJECT_ROOT),
    }
    files = {
        "results.json": artifacts.canonical_json(results),
        "regimes.csv": regimes_csv(experiment.primary_sample),
        "robustness.csv": robustness_csv(results),
        "config.toml": args.config.read_bytes().replace(b"\r\n", b"\n"),
        "protocol.lock.json": artifacts.canonical_json(lock.data),
    }
    files["report.md"] = render_report(results, validation, manifest).encode("utf-8")
    written = artifacts.write_bundle(directory, files, manifest)
    if written.created:
        print(f"Result bundle: {written.path} ({runtime} s)")
    else:
        print(f"A bundle for these inputs already exists: {written.path}")
        print(
            "Reproduction check: "
            + (
                "identical results."
                if written.identical
                else "DIFFERENT: " + "; ".join(written.differences)
            )
        )
    primary = results["primary"]
    print(
        f"Primary ({estimand}{'' if validated else ', NOT validated'}): "
        f"Delta = {primary['delta']:+.4f}, 95% interval "
        f"[{primary['ci_low']:+.4f}, {primary['ci_high']:+.4f}], "
        f"days {primary['n_high']} high / {primary['n_low']} low"
    )
    print(results["interpretation"]["inference"])
    return 0 if written.created or written.identical else 1


def cmd_verify(args: argparse.Namespace) -> int:
    checks = artifacts.verify_bundle(args.bundle)
    for name, ok, detail in checks:
        print(f"  {'OK  ' if ok else 'FAIL'} {name}: {detail}")
    manifest = artifacts.read_manifest(args.bundle)
    if manifest.get("kind") == "experiment":
        lock_data = artifacts.read_json(args.bundle, "protocol.lock.json")
        for name, digest in lock_data["files"].items():
            path = args.project_root / name
            current = path.exists() and file_sha256(path) == digest
            detail = "matches lock" if current else "changed or missing"
            checks.append((f"protocol:{name}", current, detail))
            print(f"  {'OK  ' if current else 'FAIL'} protocol:{name}: {detail}")
    failed = sum(1 for _, ok, _ in checks if not ok)
    print(f"{len(checks) - failed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def cmd_show(args: argparse.Namespace) -> int:
    manifest = artifacts.read_manifest(args.bundle)
    print(json.dumps({k: v for k, v in manifest.items() if k != "files"}, indent=2))
    if manifest.get("kind") == "experiment":
        results = artifacts.read_json(args.bundle, "results.json")
        for item in [results["primary"], *results["robustness"]]:
            print(
                f"  {item['id']:8} {item['label'][:45]:45} Delta {item['delta']:+.4f} "
                f"[{item['ci_low']:+.4f}, {item['ci_high']:+.4f}]"
            )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    results = artifacts.read_json(args.bundle, "results.json")
    manifest = artifacts.read_manifest(args.bundle)
    validation = artifacts.read_json(
        args.results_dir / results["simulation"]["bundle"], "validation.json"
    )
    text = render_report(results, validation, manifest)
    if args.output:
        if args.output.resolve().parent == args.bundle.resolve():
            raise ResearchError("Write the report outside the immutable bundle.")
        args.output.write_text(text, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    bundles = artifacts.list_bundles(args.results_dir)
    if not bundles:
        print(f"No result bundles under {args.results_dir}.")
    for path, manifest in bundles:
        print(f"{manifest.get('kind', '?'):10} {manifest.get('created_at', '')}  {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cryptovision-research", description="Offline Research Lab commands."
    )
    parser.add_argument("--results-dir", type=Path, default=artifacts.DEFAULT_RESULTS_DIR)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Root against which frozen protocol files are verified.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    for name, handler, help_text in (
        ("validate", cmd_validate, "Validate a config and check its protocol lock."),
        ("plan", cmd_plan, "Show the frozen experiment plan."),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("config", type=Path)
        sub.set_defaults(handler=handler)

    simulate = commands.add_parser("simulate", help="Run the synthetic validation and gate.")
    simulate.add_argument("config", type=Path)
    simulate.add_argument("--quick", action="store_true", help="Reduced settings for smoke tests.")
    simulate.add_argument("--verbose", action="store_true")
    simulate.set_defaults(handler=cmd_simulate)

    run = commands.add_parser("run", help="Run the frozen experiment on the local dataset.")
    run.add_argument("config", type=Path)
    run.set_defaults(handler=cmd_run)

    for name, handler, help_text in (
        ("verify", cmd_verify, "Verify a result bundle's hashes and protocol."),
        ("show", cmd_show, "Show a result bundle's metadata and estimates."),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("bundle", type=Path)
        sub.set_defaults(handler=handler)

    report = commands.add_parser("report", help="Render the report of a result bundle.")
    report.add_argument("bundle", type=Path)
    report.add_argument("--output", type=Path, help="Write to a file outside the bundle.")
    report.set_defaults(handler=cmd_report)

    listing = commands.add_parser("list", help="List result bundles.")
    listing.set_defaults(handler=cmd_list)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ResearchError, DataPipelineError, AnalyticsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: file not found: {exc.filename}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
