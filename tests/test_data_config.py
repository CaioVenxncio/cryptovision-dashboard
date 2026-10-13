from __future__ import annotations

from pathlib import Path

import pytest

from cryptovision.data.config import (
    DatasetConfig,
    DatasetConfigError,
    config_sha256,
    load_dataset_config,
)
from cryptovision.data.schemas import DatasetKind

CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs" / "datasets"

BINANCE_TOML = """
[dataset]
id = "test-binance"
version = "1.0.0"
description = "test"
provider = "binance_vision"
quote_currency = "USDT"
start = 2024-01-01
end = 2024-02-29

[dataset.selection]
rule = "test rule"

[[dataset.assets]]
asset_id = "bitcoin"
symbol = "BTC"
pair = "BTCUSDT"
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "dataset.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("path", sorted(CONFIG_DIR.glob("*.toml")), ids=lambda p: p.name)
def test_shipped_configs_are_valid(path):
    config, digest = load_dataset_config(path)
    assert len(digest) == 64
    assert config.assets


def test_research_config_universe_and_exclusions():
    config, _ = load_dataset_config(CONFIG_DIR / "binance-spot-1d-top10-20210103.toml")
    assert [a.symbol for a in config.assets] == [
        "BTC", "ETH", "LTC", "XRP", "DOT", "BCH", "ADA", "BNB", "LINK"
    ]  # fmt: skip
    assert {e.symbol for e in config.selection.excluded} == {"USDT", "USDC", "WBTC", "BSV"}
    assert config.kind is DatasetKind.OHLCV
    assert not config.is_ephemeral


def test_coingecko_config_is_ephemeral():
    config, _ = load_dataset_config(CONFIG_DIR / "coingecko-daily-365d.toml")
    assert config.is_ephemeral
    assert config.kind is DatasetKind.PRICE_SERIES
    assert config.lookback_days == 365


def test_valid_binance_config(tmp_path):
    config, _ = load_dataset_config(write(tmp_path, BINANCE_TOML))
    assert config.start.isoformat() == "2024-01-01"
    assert config.validation.max_missing_fraction == 0.005


@pytest.mark.parametrize(
    ("replace", "message"),
    [
        (('pair = "BTCUSDT"', 'pair = "BTCBUSD"'), "never converted"),
        (('pair = "BTCUSDT"', ""), "requires pair"),
        (("end = 2024-02-29", "end = 2023-12-31"), "end must not be before start"),
        (("end = 2024-02-29", ""), "require start and end"),
        (('version = "1.0.0"', 'version = "v1"'), "version"),
        (('id = "test-binance"', 'id = "Bad ID"'), "id"),
        (('provider = "binance_vision"', 'provider = "kraken"'), "provider"),
    ],
)
def test_invalid_configs_are_rejected(tmp_path, replace, message):
    old, new = replace
    with pytest.raises(DatasetConfigError, match=message):
        load_dataset_config(write(tmp_path, BINANCE_TOML.replace(old, new)))


def test_unknown_keys_are_rejected(tmp_path):
    with pytest.raises(DatasetConfigError, match="Extra inputs are not permitted"):
        load_dataset_config(write(tmp_path, BINANCE_TOML + 'api_key = "x"\n'))


def test_duplicate_assets_rejected(tmp_path):
    text = (
        BINANCE_TOML + '\n[[dataset.assets]]\nasset_id = "bitcoin"\nsymbol = "B"\npair = "XUSDT"\n'
    )
    with pytest.raises(DatasetConfigError, match="unique"):
        load_dataset_config(write(tmp_path, text))


def test_coingecko_requires_lookback_and_ids():
    base = {
        "id": "cg",
        "version": "1.0.0",
        "description": "d",
        "provider": "coingecko",
        "quote_currency": "USD",
        "selection": {"rule": "r"},
        "assets": [{"asset_id": "bitcoin", "symbol": "BTC", "coingecko_id": "bitcoin"}],
    }
    with pytest.raises(ValueError, match="lookback_days"):
        DatasetConfig.model_validate(base)
    with pytest.raises(ValueError, match="coingecko_id"):
        DatasetConfig.model_validate(
            {**base, "lookback_days": 120, "assets": [{"asset_id": "b", "symbol": "B"}]}
        )
    with pytest.raises(ValueError, match="not start/end"):
        DatasetConfig.model_validate({**base, "lookback_days": 120, "start": "2024-01-01"})
    with pytest.raises(ValueError):
        DatasetConfig.model_validate({**base, "lookback_days": 400})


def test_lookback_only_for_coingecko(tmp_path):
    with pytest.raises(DatasetConfigError, match="only valid for coingecko"):
        load_dataset_config(
            write(
                tmp_path,
                BINANCE_TOML.replace("end = 2024-02-29", "end = 2024-02-29\nlookback_days = 100"),
            )
        )


def test_bad_toml_and_missing_file(tmp_path):
    with pytest.raises(DatasetConfigError, match="Invalid TOML"):
        load_dataset_config(write(tmp_path, "[dataset\n"))
    with pytest.raises(DatasetConfigError, match="Cannot read"):
        load_dataset_config(tmp_path / "missing.toml")


def test_config_hash_ignores_line_endings():
    assert config_sha256(b"a = 1\r\nb = 2\r\n") == config_sha256(b"a = 1\nb = 2\n")
    assert config_sha256(b"a = 1\n") != config_sha256(b"a = 2\n")
