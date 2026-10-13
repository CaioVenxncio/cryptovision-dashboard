# Data Methodology

How CryptoVision acquires, normalizes, validates and stores historical market data. See [data-sources.md](data-sources.md) for provider evaluation and [reproducibility.md](reproducibility.md) for hashing and rebuild guarantees.

## Dataset configurations

Every dataset is defined by a TOML file in `configs/datasets/`. The configuration is validated before any request is made.

| Field | Meaning |
|---|---|
| `id`, `version` | Dataset identity. A new version is required to change an archived dataset. |
| `provider` | `binance_vision`, `coingecko` or `synthetic` |
| `quote_currency` | Must match each Binance pair suffix. It is never converted. |
| `start`, `end` | Inclusive UTC-day period (Binance and synthetic datasets) |
| `lookback_days` | 91–365 days (CoinGecko only) |
| `assets` | `asset_id`, `symbol`, plus `pair` (Binance) or `coingecko_id` |
| `selection` | The universe rule, its reference, the snapshot date and every exclusion with its reason |
| `validation` | `max_missing_fraction` and `max_consecutive_missing` thresholds |

Unknown keys are rejected, so a misspelled field or an accidental secret fails validation instead of being silently ignored.

## Research universe

The research dataset `binance-spot-1d-top10-20210103` uses a rule fixed in advance:

1. Start from the CoinMarketCap historical snapshot dated **2021-01-03** ([reference](https://coinmarketcap.com/historical/20210103/)), the start of the study period.
2. Exclude stablecoins (USDT rank 3, USDC rank 11) and wrapped tokens (WBTC rank 12).
3. Keep the first 10 remaining assets: BTC, ETH, LTC, XRP, DOT, BCH, ADA, BNB, LINK and BSV (rank 13).
4. Include an asset only if a Binance USDT spot pair has daily archives for every month of 2021-01 to 2025-12.

BSV has no Binance USDT archives because it was delisted from Binance in 2019, so the final universe has **9 assets**.

**Why this rule?** Choosing assets by their rank at the *start* of the period, instead of today's leaders, limits look-ahead selection. It does not remove survivorship bias. Step 4 still excludes an asset that a single exchange delisted, and every included asset survived on Binance until at least 2025-12. The exclusions are recorded in the configuration and in every manifest so the bias stays visible.

These 9 assets represent large-cap cryptocurrencies as traded on Binance against USDT. They do not represent the cryptocurrency market as a whole.

## Normalized schemas

The two schemas are never merged into one table, because they measure different things.

**`ohlcv`** (Binance Vision, synthetic):

| Column | Type | Notes |
|---|---|---|
| `timestamp_utc` | timestamp[us, UTC] | Candle open time (00:00 UTC) |
| `close_time_utc` | timestamp[us, UTC] | Candle close time (23:59:59.999… UTC) |
| `asset_id`, `symbol`, `pair` | string | |
| `exchange`, `provider` | string | `binance`, `binance_vision` |
| `quote_currency` | string | e.g. `USDT` |
| `frequency` | string | `1d` |
| `open`, `high`, `low`, `close` | float64 | In the quote currency |
| `volume_base` | float64 | Units of the base asset |
| `volume_quote` | float64 | Units of the quote currency (USDT, not USD) |
| `trade_count` | int64 (nullable) | |
| `taker_buy_volume_base`, `taker_buy_volume_quote` | float64 | |

**`price_series`** (CoinGecko):

| Column | Type | Notes |
|---|---|---|
| `timestamp_utc` | timestamp[us, UTC] | 00:00 UTC sampling instant |
| `asset_id`, `symbol`, `provider`, `quote_currency`, `frequency` | string | |
| `price`, `market_cap`, `volume_24h` | float64 (nullable) | Aggregated, in `quote_currency` |

Schema version: `1.0` (`cryptovision.data.schemas.SCHEMA_VERSION`).

## Normalization rules

- **Timestamps:** stored as UTC with microsecond precision. Binance millisecond and microsecond timestamps are detected per value. CoinGecko milliseconds are converted exactly.
- **No implicit conversions:** no currency conversion, and no market capitalization is derived for providers that do not publish it.
- **Nulls:** missing provider values stay null. They are never replaced with zero, and missing days are never interpolated or forward-filled.
- **Rejecting malformed files:** a corrupt, truncated or schema-changed provider file raises an error instead of being partially parsed.

## Validation

`cryptovision.data.validate.validate_dataset` runs these checks in order. Rows that are removed are written to `rejected.parquet` with a `rejection_reason`, and every action is recorded as an issue in the manifest.

| Check | Severity | Action |
|---|---|---|
| Required columns missing | fatal | Dataset unusable |
| Unexpected extra columns | warning | Columns dropped |
| Rows out of chronological order | warning | Sorted |
| Asset not in config | error | Rows rejected |
| Null timestamp | error | Rows rejected |
| Provisional intraday point after the last full day | warning | Row rejected |
| Any other timestamp not at 00:00 UTC | error | Row rejected |
| Outside requested period | warning | Rows rejected |
| Identical duplicate | warning | Extra copies rejected |
| Conflicting duplicate (same asset and day, different values) | error | All copies rejected |
| Null price | error | Row rejected |
| Price ≤ 0 | error | Row rejected |
| High below open/close, or low above open/close | error | Row rejected |
| Negative volume or trade count | warning | Value set to null; row kept |
| CoinGecko market cap ≤ 0 (published as 0 when unknown) | warning | Value set to null; row kept |
| Null secondary value | warning | Kept as null |
| Binance archive not published for a month | error | Recorded; affects coverage |
| Asset with no valid rows | fatal | |
| Missing days above `max_missing_fraction`, or a gap longer than `max_consecutive_missing` | fatal | Gaps are reported, never filled |
| Missing days within the thresholds | warning | |

A dataset is **research-ready** only if no fatal issue exists. Datasets that fail validation are still stored with `status: failed_validation` for inspection, but `load_dataset` refuses them unless the caller explicitly opts in.

The default thresholds are 0.5% missing days and at most 3 consecutive missing days per asset. Analyses that need complete panels must still handle missing days explicitly.

## Storage

- **Format:** Parquet (pyarrow) with zstd compression and a fixed Arrow schema. Rows are sorted by `(asset_id, timestamp_utc)`.
- **Atomic writes:** each file is written to a temporary file and renamed into place. A dataset directory is assembled in a hidden staging directory and renamed only after its manifest is written, so an interrupted run leaves no directory that looks complete.
- **Overwrite protection:** existing archival datasets are never overwritten without `--force`; normally a new version is created instead.
- **Raw archive cache:** Binance zips are kept under `data/raw/binance_vision/` and re-verified against their checksums on reuse.

## Synthetic data

`cryptovision.data.synthetic` generates seeded, correlated geometric random walks for three assets: `synthetic-a`, `synthetic-b` and `synthetic-c`.

- **Labelling:** the data uses provider and exchange `synthetic`, quote currency `SYNTH` and `synthetic: true` in the manifest.
- **Defect injection:** an optional mode injects documented defects (missing days, duplicates, a zero price, a null volume, reversed rows) to exercise validation.
- **Not market data:** synthetic data must never be presented as market observations.
