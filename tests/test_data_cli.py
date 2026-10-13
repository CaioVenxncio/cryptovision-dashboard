"""CLI commands. None of these tests reach the network."""

from __future__ import annotations

from pathlib import Path

import pytest

from cryptovision.data.cli import main
from cryptovision.data.sources.binance import BASE_URL, archive_path
from tests.data_helpers import checksum_text, kline_rows, kline_zip, month_days
from tests.test_data_pipeline import BINANCE_TOML

CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs" / "datasets"
SYNTHETIC_DIR = Path("synthetic") / "synthetic-ohlcv-clean-seed42" / "1.0.0"


def run(capsys, *args: str) -> tuple[int, str]:
    code = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_plan_is_offline(capsys, tmp_path, mocked_api):
    code, out = run(
        capsys,
        "--data-dir",
        tmp_path,
        "plan",
        CONFIG_DIR / "binance-spot-1d-top10-20210103.toml",
    )
    assert code == 0
    assert "Requests:      1080 (API credits: 0)" in out
    assert "2021-01-01 to 2025-12-31" in out
    assert len(mocked_api.calls) == 0


def test_collect_without_yes_is_a_dry_run(capsys, tmp_path, mocked_api):
    code, out = run(
        capsys, "--data-dir", tmp_path, "collect", CONFIG_DIR / "coingecko-daily-365d.toml"
    )
    assert code == 0
    assert "Dry run only" in out
    assert "API credits: 9" in out
    assert len(mocked_api.calls) == 0
    assert not (tmp_path / "cache").exists()


def test_coingecko_collect_without_key_fails_safely(capsys, tmp_path, mocked_api):
    code, out = run(
        capsys,
        "--data-dir",
        tmp_path,
        "collect",
        CONFIG_DIR / "coingecko-daily-365d.toml",
        "--yes",
    )
    assert code == 1
    assert "No CoinGecko API key configured" in out
    assert len(mocked_api.calls) == 0


def test_coingecko_cannot_be_collected_offline(capsys, tmp_path):
    code, out = run(
        capsys,
        "--data-dir",
        tmp_path,
        "collect",
        CONFIG_DIR / "coingecko-daily-365d.toml",
        "--offline",
    )
    assert code == 2
    assert "cannot be collected offline" in out


def test_synthetic_show_verify_validate_list(capsys, tmp_path):
    code, out = run(capsys, "--data-dir", tmp_path, "synthetic", "--days", "15")
    assert code == 0
    assert "research_ready" in out and "synthetic=True" in out
    dataset = tmp_path / SYNTHETIC_DIR

    code, out = run(capsys, "show", dataset, "--issues", "--json")
    assert code == 0 and '"synthetic": true' in out

    code, out = run(capsys, "verify", dataset)
    assert code == 0 and "4 passed, 0 failed" in out

    code, out = run(capsys, "validate", dataset)
    assert code == 0 and "research_ready=True" in out

    code, out = run(capsys, "--data-dir", tmp_path, "list")
    assert "synthetic-ohlcv-clean-seed42 v1.0.0  research_ready" in out

    code, out = run(capsys, "--data-dir", tmp_path, "synthetic", "--days", "15")
    assert code == 1 and "already exists" in out

    code, out = run(capsys, "--data-dir", tmp_path, "synthetic", "--days", "15", "--force")
    assert code == 0


def test_verify_and_validate_report_failures(capsys, tmp_path):
    run(capsys, "--data-dir", tmp_path, "synthetic", "--days", "15", "--anomalies")
    dataset = tmp_path / "synthetic" / "synthetic-ohlcv-anomalies-seed42" / "1.0.0"

    code, out = run(capsys, "validate", dataset)
    assert code == 1 and "FATAL" in out

    (dataset / "data.parquet").write_bytes(b"tampered")
    code, out = run(capsys, "verify", dataset)
    assert code == 1 and "FAIL file:data" in out and "FAIL content_sha256" in out


def test_offline_binance_rebuild_from_local_archives(capsys, tmp_path, mocked_api):
    config = tmp_path / "binance.toml"
    config.write_text(BINANCE_TOML, encoding="utf-8")
    raw = tmp_path / "raw" / "binance_vision"
    for month in ("2024-01", "2024-02"):
        relative = archive_path("BTCUSDT", month)
        name = relative.rsplit("/", 1)[-1]
        first, days = month_days(month)
        data = kline_zip(kline_rows(first, days), name=name.replace(".zip", ".csv"))
        (raw / relative).parent.mkdir(parents=True, exist_ok=True)
        (raw / relative).write_bytes(data)
        (raw / f"{relative}.CHECKSUM").write_text(checksum_text(data, name))

    code, out = run(capsys, "--data-dir", tmp_path, "collect", config, "--offline", "--verbose")

    assert code == 0, out
    assert "BTCUSDT 2024-01: reused" in out
    assert "Status:        research_ready" in out
    assert len(mocked_api.calls) == 0
    code, out = run(
        capsys,
        "--data-dir",
        tmp_path,
        "verify",
        tmp_path / "datasets" / "test-binance" / "1.0.0",
        "--sources",
    )
    assert code == 0 and "6 passed" in out


def test_binance_collect_downloads_when_confirmed(capsys, tmp_path, mocked_api):
    config = tmp_path / "binance.toml"
    config.write_text(BINANCE_TOML, encoding="utf-8")
    for month in ("2024-01", "2024-02"):
        relative = archive_path("BTCUSDT", month)
        name = relative.rsplit("/", 1)[-1]
        first, days = month_days(month)
        data = kline_zip(kline_rows(first, days), name=name.replace(".zip", ".csv"))
        mocked_api.get(f"{BASE_URL}/{relative}", body=data)
        mocked_api.get(f"{BASE_URL}/{relative}.CHECKSUM", body=checksum_text(data, name))

    code, out = run(capsys, "--data-dir", tmp_path, "collect", config, "--yes")

    assert code == 0, out
    assert len(mocked_api.calls) == 4


def test_purge_expired_and_errors(capsys, tmp_path):
    code, out = run(capsys, "--data-dir", tmp_path, "purge-expired")
    assert code == 0 and "0 expired cache(s) removed." in out

    code, out = run(capsys, "--data-dir", tmp_path, "list")
    assert "No datasets" in out

    code, out = run(capsys, "plan", tmp_path / "missing.toml")
    assert code == 1 and "Cannot read" in out

    code, out = run(capsys, "show", tmp_path / "nowhere")
    assert code == 1 and "file not found" in out


def test_collect_rejects_synthetic_configs(capsys, tmp_path):
    config = tmp_path / "s.toml"
    config.write_text(
        BINANCE_TOML.replace('provider = "binance_vision"', 'provider = "synthetic"'),
        encoding="utf-8",
    )
    code, out = run(capsys, "--data-dir", tmp_path, "collect", config)
    assert code == 2 and "synthetic" in out


@pytest.mark.parametrize("argv", [[], ["unknown"]])
def test_usage_errors_exit(argv):
    with pytest.raises(SystemExit):
        main(argv)


def test_module_entry_point_runs_offline(tmp_path):
    import subprocess
    import sys

    completed = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [sys.executable, "-m", "cryptovision.data", "--data-dir", str(tmp_path), "list"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0
    assert "No datasets" in completed.stdout
