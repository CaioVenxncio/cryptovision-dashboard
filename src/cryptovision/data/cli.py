"""Command-line interface for historical datasets.

Usage: `cryptovision-data <command> ...` or `python -m cryptovision.data <command> ...`.
Only `collect --yes` performs network requests; every other command is offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from cryptovision.data import pipeline, synthetic
from cryptovision.data.config import DatasetConfigError, load_dataset_config
from cryptovision.data.errors import DataPipelineError
from cryptovision.data.provenance import DatasetManifest, read_manifest
from cryptovision.data.schemas import DatasetKind
from cryptovision.data.sources.binance import BinanceVisionSource
from cryptovision.data.storage import read_parquet
from cryptovision.data.validate import validate_dataset
from cryptovision.providers.errors import ProviderError

DEFAULT_DATA_DIR = Path("data")


def _print_plan(plan: pipeline.DatasetPlan) -> None:
    config = plan.config
    print(f"Dataset:       {config.id} v{config.version}")
    print(f"Provider:      {config.provider} ({plan.retention})")
    print(
        f"Assets:        {', '.join(a.pair or a.coingecko_id or a.asset_id for a in config.assets)}"
    )
    print(f"Quote:         {config.quote_currency}   Frequency: {config.frequency}")
    print(f"Period:        {plan.start} to {plan.end} (inclusive, UTC days)")
    print(f"Requests:      {plan.estimated_requests} (API credits: {plan.api_credits})")
    print(f"Output:        {plan.output_dir}")


def _print_manifest(directory: Path, manifest: DatasetManifest) -> None:
    validation = manifest.validation
    print(f"Dataset:       {manifest.dataset_id} v{manifest.dataset_version}")
    print(f"Location:      {directory}")
    print(f"Status:        {manifest.status}")
    print(f"Provider:      {manifest.provider}  synthetic={manifest.synthetic}")
    print(f"Retention:     {manifest.retention}  expires_at={manifest.expires_at}")
    print(f"Kind:          {manifest.kind}  quote={manifest.quote_currency}")
    print(f"Requested:     {manifest.requested_period.start} to {manifest.requested_period.end}")
    print(f"Actual:        {manifest.actual_period.start} to {manifest.actual_period.end}")
    print(
        f"Rows:          {validation['valid_rows']} valid, {validation['rejected_rows']} rejected"
    )
    print(
        f"Issues:        {validation['fatal_count']} fatal, {validation['error_count']} errors, "
        f"{validation['warning_count']} warnings"
    )
    print(f"Content hash:  {manifest.content_sha256}")
    print(f"Attribution:   {manifest.attribution}")


def _print_issues(validation: dict) -> None:
    for issue in validation["issues"]:
        asset = f" [{issue['asset_id']}]" if issue["asset_id"] else ""
        examples = f" e.g. {', '.join(issue['examples'])}" if issue["examples"] else ""
        print(
            f"  {issue['severity'].upper():7} {issue['code']}{asset} x{issue['count']}: "
            f"{issue['message']}{examples}"
        )


def cmd_plan(args: argparse.Namespace) -> int:
    config, _ = load_dataset_config(args.config)
    _print_plan(pipeline.plan_dataset(config, args.data_dir))
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    config, config_hash = load_dataset_config(args.config)
    plan = pipeline.plan_dataset(config, args.data_dir)
    _print_plan(plan)
    if config.provider == "synthetic":
        print("Synthetic datasets are created with the 'synthetic' command.")
        return 2

    existing = pipeline.existing_result(plan, force=args.force, now=datetime.now(UTC))
    if existing is not None:
        print(f"Reusing unexpired cache at {existing.path} (no requests made).")
        return 0
    if not args.yes and not args.offline:
        print("\nDry run only. Re-run with --yes to perform the requests above.")
        return 0

    if config.provider == "coingecko":
        # Checked before any request so that no API credits are spent.
        print(f"\n{pipeline.COINGECKO_PERSISTENCE_DISABLED}")
        return 2

    progress = print if args.verbose else (lambda _: None)
    source = BinanceVisionSource(args.data_dir / "raw")
    collected = pipeline.collect_binance(plan, source, offline=args.offline, progress=progress)

    # An expired ephemeral cache is replaced; archival datasets only with --force.
    result = pipeline.store_dataset(
        plan, collected, config_sha256=config_hash, replace=args.force or config.is_ephemeral
    )
    print()
    _print_manifest(result.path, result.manifest)
    _print_issues(result.manifest.validation)
    return 0 if result.manifest.status == "research_ready" else 1


def cmd_show(args: argparse.Namespace) -> int:
    manifest = read_manifest(args.dataset)
    _print_manifest(args.dataset, manifest)
    if args.issues:
        _print_issues(manifest.validation)
    if args.json:
        print(json.dumps(manifest.model_dump(mode="json"), indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    checks = pipeline.verify_dataset(args.dataset, data_dir=args.data_dir if args.sources else None)
    for check in checks:
        print(f"  {'OK  ' if check.ok else 'FAIL'} {check.name}: {check.detail}")
    failed = sum(1 for check in checks if not check.ok)
    print(f"{len(checks) - failed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Re-run validation on the stored data with the rules recorded in the manifest."""
    from cryptovision.data.config import DatasetConfig

    manifest = read_manifest(args.dataset)
    config = DatasetConfig.model_validate(manifest.config["resolved"])
    kind = DatasetKind(manifest.kind)
    frame = read_parquet(args.dataset / manifest.files["data"].path, kind)
    start = manifest.requested_period.start
    end = manifest.requested_period.end
    if start is None or end is None:
        print("Manifest has no requested period.")
        return 2
    result = validate_dataset(
        frame,
        kind=kind,
        asset_ids=[asset.asset_id for asset in config.assets],
        start=start,
        end=end,
        rules=config.validation,
    )
    report = result.report.to_dict()
    print(
        f"research_ready={report['research_ready']} valid_rows={report['valid_rows']} "
        f"rejected_rows={report['rejected_rows']}"
    )
    _print_issues(report)
    return 0 if result.report.research_ready else 1


def cmd_synthetic(args: argparse.Namespace) -> int:
    config = synthetic.synthetic_config(
        start=args.start, days=args.days, seed=args.seed, with_anomalies=args.anomalies
    )
    frame = synthetic.generate_synthetic_ohlcv(
        start=args.start, days=args.days, seed=args.seed, with_anomalies=args.anomalies
    )
    plan = pipeline.plan_dataset(config, args.data_dir)
    config_hash = hashlib.sha256(
        json.dumps(config.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    collected = pipeline.CollectedData(
        frame=frame,
        source={
            "name": "CryptoVision synthetic generator",
            "generator": "cryptovision.data.synthetic.generate_synthetic_ohlcv",
            "seed": args.seed,
            "with_anomalies": args.anomalies,
        },
        attribution=pipeline.SYNTHETIC_ATTRIBUTION,
        license_notes=pipeline.SYNTHETIC_LICENSE_NOTES,
    )
    result = pipeline.store_dataset(plan, collected, config_sha256=config_hash, replace=args.force)
    _print_manifest(result.path, result.manifest)
    _print_issues(result.manifest.validation)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    datasets = pipeline.list_datasets(args.data_dir)
    if not datasets:
        print(f"No datasets under {args.data_dir}.")
    for directory, manifest in datasets:
        print(
            f"{manifest.dataset_id} v{manifest.dataset_version}  {manifest.status}  "
            f"{manifest.retention}  {directory}"
        )
    return 0


def cmd_purge_expired(args: argparse.Namespace) -> int:
    removed = pipeline.purge_expired(args.data_dir)
    for directory in removed:
        print(f"Removed expired cache {directory}")
    print(f"{len(removed)} expired cache(s) removed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cryptovision-data", description="Historical dataset operations for CryptoVision."
    )
    parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Data directory (default: ./data)"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan", help="Show what a collection would do (offline).")
    plan.add_argument("config", type=Path)
    plan.set_defaults(handler=cmd_plan)

    collect = commands.add_parser("collect", help="Collect a dataset (network only with --yes).")
    collect.add_argument("config", type=Path)
    collect.add_argument("--yes", action="store_true", help="Perform the network requests.")
    collect.add_argument(
        "--offline", action="store_true", help="Rebuild from local raw files only."
    )
    collect.add_argument("--force", action="store_true", help="Replace an existing dataset.")
    collect.add_argument("--verbose", action="store_true", help="Print per-file progress.")
    collect.set_defaults(handler=cmd_collect)

    show = commands.add_parser("show", help="Show a dataset manifest.")
    show.add_argument("dataset", type=Path)
    show.add_argument("--issues", action="store_true", help="List validation issues.")
    show.add_argument("--json", action="store_true", help="Print the full manifest as JSON.")
    show.set_defaults(handler=cmd_show)

    verify = commands.add_parser("verify", help="Recompute and compare dataset hashes.")
    verify.add_argument("dataset", type=Path)
    verify.add_argument(
        "--sources", action="store_true", help="Also verify raw source files in --data-dir."
    )
    verify.set_defaults(handler=cmd_verify)

    validate = commands.add_parser("validate", help="Re-run validation on a stored dataset.")
    validate.add_argument("dataset", type=Path)
    validate.set_defaults(handler=cmd_validate)

    synth = commands.add_parser("synthetic", help="Generate a synthetic dataset (offline).")
    synth.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    synth.add_argument("--days", type=int, default=90)
    synth.add_argument("--seed", type=int, default=42)
    synth.add_argument("--anomalies", action="store_true", help="Inject documented defects.")
    synth.add_argument("--force", action="store_true", help="Replace an existing dataset.")
    synth.set_defaults(handler=cmd_synthetic)

    listing = commands.add_parser("list", help="List datasets in the data directory.")
    listing.set_defaults(handler=cmd_list)

    purge = commands.add_parser("purge-expired", help="Delete expired CoinGecko caches.")
    purge.set_defaults(handler=cmd_purge_expired)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (DatasetConfigError, DataPipelineError, ProviderError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: file not found: {exc.filename}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
