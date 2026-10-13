"""End-to-end pipeline behavior with mocked providers and synthetic data."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from cryptovision.data import pipeline
from cryptovision.data.config import DatasetConfig, load_dataset_config
from cryptovision.data.errors import (
    DatasetExistsError,
    DatasetExpiredError,
    DatasetIntegrityError,
    DatasetNotReadyError,
)
from cryptovision.data.provenance import MANIFEST_FILENAME, read_manifest
from cryptovision.data.sources.binance import BASE_URL, BinanceVisionSource, archive_path
from cryptovision.data.synthetic import generate_synthetic_ohlcv, synthetic_config
from cryptovision.providers.http_client import HttpJsonClient, RetryPolicy
from tests.data_helpers import checksum_text, kline_rows, kline_zip, month_days

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)

BINANCE_TOML = """
[dataset]
id = "test-binance"
version = "1.0.0"
description = "Mocked Binance dataset built from synthetic archives."
provider = "binance_vision"
quote_currency = "USDT"
start = 2024-01-01
end = 2024-02-29

[dataset.selection]
rule = "test"

[[dataset.assets]]
asset_id = "bitcoin"
symbol = "BTC"
pair = "BTCUSDT"
"""


def store_synthetic(data_dir: Path, *, anomalies: bool = False, replace: bool = False):
    config = synthetic_config(start=date(2024, 1, 1), days=20, seed=1, with_anomalies=anomalies)
    frame = generate_synthetic_ohlcv(
        start=date(2024, 1, 1), days=20, seed=1, with_anomalies=anomalies
    )
    plan = pipeline.plan_dataset(config, data_dir)
    collected = pipeline.CollectedData(frame=frame, source={"name": "synthetic"})
    return pipeline.store_dataset(plan, collected, config_sha256="c" * 64, replace=replace)


# --- Synthetic datasets, manifests and safety -------------------------------------------


def test_synthetic_dataset_manifest(tmp_path):
    result = store_synthetic(tmp_path)
    manifest = result.manifest

    assert result.path == tmp_path / "synthetic" / manifest.dataset_id / "1.0.0"
    assert manifest.synthetic is True
    assert manifest.status == "research_ready"
    assert manifest.retention == "archival" and manifest.expires_at is None
    assert manifest.files["data"].rows == 60
    assert manifest.actual_period.start == date(2024, 1, 1)
    assert manifest.actual_period.end == date(2024, 1, 20)
    assert manifest.config["sha256"] == "c" * 64
    assert manifest.config["resolved"]["provider"] == "synthetic"
    assert set(manifest.software) >= {"schema_version", "transformation_version", "pyarrow"}
    assert "content_sha256" in manifest.hash_definitions
    assert sorted(p.name for p in result.path.iterdir()) == [
        "data.parquet",
        "manifest.json",
        "rejected.parquet",
    ]


def test_failed_validation_is_stored_but_marked(tmp_path):
    result = store_synthetic(tmp_path, anomalies=True)
    assert result.manifest.status == "failed_validation"
    assert result.manifest.files["rejected"].rows == 4
    with pytest.raises(DatasetNotReadyError):
        pipeline.load_dataset(result.path)
    loaded = pipeline.load_dataset(result.path, require_research_ready=False)
    assert len(loaded.frame) == result.manifest.files["data"].rows


def test_existing_dataset_is_never_overwritten_without_force(tmp_path):
    first = store_synthetic(tmp_path)
    with pytest.raises(DatasetExistsError):
        store_synthetic(tmp_path)
    assert read_manifest(first.path).created_at == first.manifest.created_at

    replaced = store_synthetic(tmp_path, replace=True)
    assert replaced.path == first.path
    assert not [p for p in replaced.path.parent.iterdir() if p.name.startswith(".")]


def test_interrupted_write_leaves_no_partial_dataset(tmp_path, monkeypatch):
    def crash(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "write_manifest", crash)
    with pytest.raises(KeyboardInterrupt):
        store_synthetic(tmp_path)

    root = tmp_path / "synthetic"
    assert not list(root.glob("**/" + MANIFEST_FILENAME))
    assert not list(root.glob("**/*.parquet"))


def test_load_dataset_offline(tmp_path):
    result = store_synthetic(tmp_path)
    loaded = pipeline.load_dataset(result.path)
    assert len(loaded.frame) == 60
    assert loaded.manifest.content_sha256 == result.manifest.content_sha256


def test_verify_detects_tampering(tmp_path):
    result = store_synthetic(tmp_path)
    assert all(check.ok for check in pipeline.verify_dataset(result.path))

    data_file = result.path / "data.parquet"
    data_file.write_bytes(data_file.read_bytes() + b"\x00")

    failed = {check.name for check in pipeline.verify_dataset(result.path) if not check.ok}
    assert "file:data" in failed
    with pytest.raises(DatasetIntegrityError):
        pipeline.load_dataset(result.path)


def test_verify_detects_manifest_content_mismatch(tmp_path):
    result = store_synthetic(tmp_path)
    manifest_path = result.path / MANIFEST_FILENAME
    document = json.loads(manifest_path.read_text())
    document["content_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(document))

    failed = {check.name for check in pipeline.verify_dataset(result.path) if not check.ok}
    assert failed == {"content_sha256"}


def test_verify_reports_missing_files(tmp_path):
    result = store_synthetic(tmp_path)
    (result.path / "rejected.parquet").unlink()
    checks = {check.name: check for check in pipeline.verify_dataset(result.path)}
    assert checks["file:rejected"].ok is False
    assert checks["file:rejected"].detail == "missing"


# --- Binance collection with mocked archives -----------------------------------------


def register_months(mocked_api, months: list[str], *, skip: set[str] = frozenset()) -> None:
    for month in months:
        relative = archive_path("BTCUSDT", month)
        name = relative.rsplit("/", 1)[-1]
        if month in skip:
            mocked_api.get(f"{BASE_URL}/{relative}", status=404)
            continue
        first, days = month_days(month)
        data = kline_zip(kline_rows(first, days), name=name.replace(".zip", ".csv"))
        mocked_api.get(f"{BASE_URL}/{relative}", body=data)
        mocked_api.get(f"{BASE_URL}/{relative}.CHECKSUM", body=checksum_text(data, name))


@pytest.fixture
def binance_config(tmp_path) -> tuple[DatasetConfig, str]:
    path = tmp_path / "binance.toml"
    path.write_text(BINANCE_TOML, encoding="utf-8")
    return load_dataset_config(path)


def make_source(data_dir: Path) -> BinanceVisionSource:
    http = HttpJsonClient(
        BASE_URL, headers={}, timeout_seconds=5, retry_policy=RetryPolicy(max_retries=0)
    )
    return BinanceVisionSource(data_dir / "raw", http=http, sleep=lambda _: None)


def test_binance_plan_counts_requests_without_network(binance_config, tmp_path, mocked_api):
    config, _ = binance_config
    plan = pipeline.plan_dataset(config, tmp_path / "data")

    assert plan.estimated_requests == 4  # 2 months x (zip + checksum)
    assert plan.api_credits == 0
    assert plan.output_dir == tmp_path / "data" / "datasets" / "test-binance" / "1.0.0"
    assert len(mocked_api.calls) == 0


def test_binance_collection_and_offline_rebuild_are_identical(binance_config, tmp_path, mocked_api):
    config, config_hash = binance_config
    data_dir = tmp_path / "data"
    register_months(mocked_api, ["2024-01", "2024-02"])
    plan = pipeline.plan_dataset(config, data_dir)

    collected = pipeline.collect_binance(plan, make_source(data_dir), offline=False)
    first = pipeline.store_dataset(plan, collected, config_sha256=config_hash, replace=False)

    manifest = first.manifest
    assert manifest.status == "research_ready"
    assert manifest.files["data"].rows == 60
    assert len(manifest.source_files) == 2
    assert all(f.checksum_verified for f in manifest.source_files)
    assert manifest.attribution.startswith("Market data: Binance Vision")
    assert "CC BY-NC-SA 4.0" in manifest.license_notes
    downloads = len(mocked_api.calls)
    assert downloads == 4

    rebuilt_collected = pipeline.collect_binance(plan, make_source(data_dir), offline=True)
    rebuilt = pipeline.store_dataset(
        plan, rebuilt_collected, config_sha256=config_hash, replace=True
    )

    assert len(mocked_api.calls) == downloads  # offline rebuild used local raw files only
    assert all(f.reused_local_copy for f in rebuilt.manifest.source_files)
    assert rebuilt.manifest.content_sha256 == manifest.content_sha256
    checks = pipeline.verify_dataset(rebuilt.path, data_dir=data_dir)
    assert all(check.ok for check in checks)
    assert sum(check.name.startswith("source:") for check in checks) == 2


def test_missing_source_month_makes_dataset_not_ready(binance_config, tmp_path, mocked_api):
    config, config_hash = binance_config
    data_dir = tmp_path / "data"
    register_months(mocked_api, ["2024-01", "2024-02"], skip={"2024-02"})
    plan = pipeline.plan_dataset(config, data_dir)

    collected = pipeline.collect_binance(plan, make_source(data_dir), offline=False)
    result = pipeline.store_dataset(plan, collected, config_sha256=config_hash, replace=False)

    issue_codes = {issue["code"] for issue in result.manifest.validation["issues"]}
    assert {"missing_source_file", "missing_observations"} <= issue_codes
    assert result.manifest.status == "failed_validation"


def test_offline_collection_without_any_raw_files(binance_config, tmp_path):
    config, config_hash = binance_config
    plan = pipeline.plan_dataset(config, tmp_path / "data")

    collected = pipeline.collect_binance(plan, make_source(tmp_path / "data"), offline=True)
    result = pipeline.store_dataset(plan, collected, config_sha256=config_hash, replace=False)

    assert result.manifest.status == "failed_validation"
    assert result.manifest.files["data"].rows == 0


# --- Ephemeral CoinGecko caches -------------------------------------------------------


COINGECKO_CONFIG = {
    "id": "cg-test",
    "version": "1.0.0",
    "description": "mocked",
    "provider": "coingecko",
    "quote_currency": "USD",
    "lookback_days": 120,
    "selection": {"rule": "test"},
    "assets": [{"asset_id": "bitcoin", "symbol": "BTC", "coingecko_id": "bitcoin"}],
}


def coingecko_chart(start: date, days: int, now: datetime) -> dict:
    stamps = [
        int(
            datetime.combine(start + timedelta(days=i), datetime.min.time(), UTC).timestamp() * 1000
        )
        for i in range(days)
    ]
    stamps.append(int(now.timestamp() * 1000))  # provisional intraday point
    return {
        "prices": [[s, 100.0 + i] for i, s in enumerate(stamps)],
        "market_caps": [[s, 1e9] for s in stamps],
        "total_volumes": [[s, 1e7] for s in stamps],
    }


def test_coingecko_cache_expires_after_24_hours(client, mocked_api, tmp_path):
    config = DatasetConfig.model_validate(COINGECKO_CONFIG)
    plan = pipeline.plan_dataset(config, tmp_path, now=NOW)
    assert plan.api_credits == 1 and plan.retention == "ephemeral"
    assert plan.output_dir == tmp_path / "cache" / "coingecko" / "cg-test"
    mocked_api.get(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        json=coingecko_chart(plan.start, 120, NOW),
    )

    collected = pipeline.collect_coingecko(plan, client)
    result = pipeline.store_dataset(
        plan,
        collected,
        config_sha256="x" * 64,
        replace=False,
        now=NOW,
        allow_unencrypted_coingecko_cache=True,
    )

    manifest = result.manifest
    assert manifest.retention == "ephemeral"
    assert manifest.status == "research_ready"
    assert manifest.files["data"].rows == 120
    assert manifest.files["rejected"].rows == 1
    assert manifest.attribution.startswith("Powered by CoinGecko")
    assert "24 hours" in manifest.license_notes
    expires = manifest.expires_at
    assert expires is not None

    # Reused while valid, rebuilt once expired.
    reused = pipeline.existing_result(plan, force=False, now=expires - timedelta(seconds=1))
    assert reused is not None and reused.reused
    assert pipeline.existing_result(plan, force=False, now=expires) is None
    assert pipeline.existing_result(plan, force=True, now=NOW) is None

    pipeline.load_dataset(result.path, now=expires - timedelta(seconds=1))
    with pytest.raises(DatasetExpiredError):
        pipeline.load_dataset(result.path, now=expires)

    assert pipeline.purge_expired(tmp_path, now=expires - timedelta(seconds=1)) == []
    assert pipeline.purge_expired(tmp_path, now=expires) == [result.path]
    assert not result.path.exists()


def test_existing_archival_dataset_requires_force(tmp_path):
    result = store_synthetic(tmp_path)
    config = synthetic_config(start=date(2024, 1, 1), days=20, seed=1, with_anomalies=False)
    plan = pipeline.plan_dataset(config, tmp_path)
    with pytest.raises(DatasetExistsError):
        pipeline.existing_result(plan, force=False, now=NOW)
    assert pipeline.existing_result(plan, force=True, now=NOW) is None
    assert result.path.exists()


def test_list_datasets_skips_staging_directories(tmp_path):
    store_synthetic(tmp_path)
    hidden = tmp_path / "synthetic" / ".staging-x"
    hidden.mkdir()
    (hidden / MANIFEST_FILENAME).write_text("{}")
    listed = pipeline.list_datasets(tmp_path)
    assert len(listed) == 1
