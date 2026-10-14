"""Offline demo: synthetic data for all three pages, no API key or downloads needed.

`cryptovision-demo` builds (once) a synthetic historical dataset and a synthetic
Research Lab bundle under `.demo/`, then starts the app with
CRYPTOVISION_DEMO=1. Everything produced here is labelled synthetic; the
Market Explorer shows a generated snapshot instead of calling CoinGecko.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from cryptovision.data import pipeline
from cryptovision.data.synthetic import generate_synthetic_ohlcv, synthetic_config
from cryptovision.models import MarketCoin, MarketSnapshot

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEMO_ROOT = PROJECT_ROOT / ".demo"
DEMO_PROVIDER = "Synthetic demo"
DEMO_SEED = 42
DEMO_START = date(2023, 1, 1)
DEMO_DAYS = 730
DEMO_ASSETS = 40
CONFIG_NAME = "demo-volatility-correlation-v1"


def demo_market_snapshot(now: datetime | None = None, seed: int = DEMO_SEED) -> MarketSnapshot:
    """A deterministic synthetic market snapshot (40 assets) for the Market Explorer."""
    now = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    rng = np.random.default_rng(seed)
    market_caps = np.sort(rng.lognormal(mean=22.5, sigma=1.6, size=DEMO_ASSETS))[::-1]
    prices = rng.lognormal(mean=1.5, sigma=2.8, size=DEMO_ASSETS)
    coins = []
    for index in range(DEMO_ASSETS):
        change = float(np.round(rng.normal(0, 3.5), 4))
        market_cap = float(market_caps[index])
        coins.append(
            MarketCoin(
                id=f"synthetic-asset-{index + 1:02d}",
                symbol=f"SYN{index + 1:02d}",
                name=f"Synthetic Asset {index + 1:02d}",
                current_price=float(prices[index]),
                market_cap=market_cap,
                market_cap_rank=index + 1,
                total_volume=market_cap * float(rng.uniform(0.01, 0.2)),
                price_change_percentage_24h=change,
                market_cap_change_24h=market_cap * change / 100 / (1 + change / 100),
                last_updated=now - timedelta(minutes=int(rng.integers(1, 10))),
            )
        )
    return MarketSnapshot(
        provider=DEMO_PROVIDER,
        endpoint="generated",
        vs_currency="usd",
        fetched_at=now,
        coins=tuple(coins),
    )


@dataclass(frozen=True)
class DemoPaths:
    root: Path
    data_dir: Path
    results_dir: Path
    config: Path


def _write_research_files(root: Path, manifest) -> Path:
    """A demo protocol + config for the synthetic dataset, frozen like a real study."""
    from cryptovision.research.protocol import freeze, lock_path

    protocol = root / "research" / "protocols" / f"{CONFIG_NAME}.md"
    config = root / "configs" / "experiments" / f"{CONFIG_NAME}.toml"
    protocol.parent.mkdir(parents=True, exist_ok=True)
    config.parent.mkdir(parents=True, exist_ok=True)
    protocol.write_text(
        "# Demo protocol (synthetic data)\n\n"
        "Generated automatically by `cryptovision-demo` to demonstrate the Research Lab "
        "workflow on synthetic data. It is not a study, its results are not findings, and it "
        "is unrelated to the empirical protocol in research/protocols/.\n",
        encoding="utf-8",
    )
    assets = ", ".join(f'"{a["asset_id"]}"' for a in manifest.assets)
    config.write_text(
        f"""[experiment]
id = "demo-volatility-correlation"
protocol_version = "1.0"
protocol_path = "research/protocols/{CONFIG_NAME}.md"
description = "Demo on synthetic data. Not a study."

[dataset]
id = "{manifest.dataset_id}"
version = "{manifest.dataset_version}"
content_sha256 = "{manifest.content_sha256}"
assets = [{assets}]
start = {manifest.requested_period.start}
end = {manifest.requested_period.end}

[primary]
estimand = "raw"
fallback_estimand = "devolatilized"
return_type = "log"
correlation = "pearson"
proxy = "mean_asset_volatility"
proxy_asset = ""
lookback_days = 30
threshold = "full_sample_quantile"
quantile = 0.5
trailing_days = 365
evaluation_start = {manifest.requested_period.start}
min_days_per_regime = 180

[bootstrap]
method = "stationary"
replications = 500
mean_block_length = 20
confidence_level = 0.95
seed = {DEMO_SEED}
max_rejected_fraction = 0.01

[[robustness]]
id = "R2"
label = "Spearman correlation"
correlation = "spearman"

[[robustness]]
id = "R6"
label = "Mean block length 10"
mean_block_length = 10

[[robustness]]
id = "R11"
label = "Alternative estimand"
estimand = "alternative"

[illustration]
id = "I1"
label = "Contemporaneous 30-day window (includes day t)"
contemporaneous = true

[simulation]
n_assets = 3
n_days = 600
short_n_days = 300
replications = 20
bootstrap_replications = 99
mean_block_length = 20
block_sensitivity = [10]
pseudo_true_days = 20000
seed = {DEMO_SEED}
daily_scale = 0.03

[gate]
max_null_rejection_rate = 0.10
max_abs_pseudo_true_null = 0.02
min_coverage = 0.85
""",
        encoding="utf-8",
    )
    if not lock_path(config).exists():
        freeze(
            protocol_id="demo-volatility-correlation",
            protocol_version="1.0",
            files=[protocol, config],
            root=root,
            destination=lock_path(config),
            repository_head="demo",
            empirical_results_seen=False,
            reason="Demo protocol generated for synthetic data.",
        )
    return config


def prepare_demo(root: Path = DEFAULT_DEMO_ROOT, progress=print) -> DemoPaths:
    """Create the synthetic dataset and demo research bundle once; reuse them afterwards."""
    from cryptovision.research.cli import main as research_main

    data_dir, results_dir = root / "data", root / "results"
    config = synthetic_config(
        start=DEMO_START, days=DEMO_DAYS, seed=DEMO_SEED, with_anomalies=False
    )
    plan = pipeline.plan_dataset(config, data_dir)
    if not (plan.output_dir / "manifest.json").exists():
        progress("Generating synthetic historical dataset...")
        frame = generate_synthetic_ohlcv(start=DEMO_START, days=DEMO_DAYS, seed=DEMO_SEED)
        pipeline.store_dataset(
            plan,
            pipeline.CollectedData(
                frame=frame,
                source={"name": "CryptoVision synthetic generator", "seed": DEMO_SEED},
                attribution=pipeline.SYNTHETIC_ATTRIBUTION,
                license_notes=pipeline.SYNTHETIC_LICENSE_NOTES,
            ),
            config_sha256="0" * 64,
            replace=False,
        )
    manifest = pipeline.read_manifest(plan.output_dir)
    config_path = _write_research_files(root, manifest)

    if not any(results_dir.glob("demo-volatility-correlation/*/manifest.json")):
        common = [
            "--results-dir", str(results_dir), "--data-dir", str(data_dir),
            "--project-root", str(root),
        ]  # fmt: skip
        progress("Running the demo method validation (about a minute, once)...")
        if research_main([*common, "simulate", str(config_path)]) != 0:
            raise RuntimeError("Demo simulation failed.")
        progress("Running the demo experiment...")
        if research_main([*common, "run", str(config_path)]) != 0:
            raise RuntimeError("Demo experiment failed.")
    return DemoPaths(root=root, data_dir=data_dir, results_dir=results_dir, config=config_path)


def demo_environment(paths: DemoPaths) -> dict[str, str]:
    return {
        **os.environ,
        "CRYPTOVISION_DEMO": "1",
        "CRYPTOVISION_DATA_DIR": str(paths.data_dir),
        "CRYPTOVISION_RESULTS_DIR": str(paths.results_dir),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cryptovision-demo",
        description="Start CryptoVision offline with synthetic demo data (no API key needed).",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_DEMO_ROOT)
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--prepare-only", action="store_true", help="Build demo data and exit.")
    args = parser.parse_args(argv)

    paths = prepare_demo(args.root)
    print(f"Demo data ready in {paths.root}")
    if args.prepare_only:
        return 0
    command = [
        sys.executable, "-m", "streamlit", "run", str(PROJECT_ROOT / "app.py"),
        "--server.port", str(args.port),
    ]  # fmt: skip
    return subprocess.call(command, env=demo_environment(paths))  # noqa: S603 - fixed args


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
