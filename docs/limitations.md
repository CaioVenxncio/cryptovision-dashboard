# Limitations

Known limitations of CryptoVision's data and of research built on it. Read this before interpreting any result.

## Data and selection

- **Survivorship bias.**
  - The universe is selected by rank on 2021-01-03, then filtered to assets with Binance USDT archives for the whole period.
  - BSV, the 10th eligible asset, is excluded because Binance delisted it. Every included asset survived on Binance until at least 2025-12.
  - Results describe surviving large-cap assets on one exchange.
- **Selection-source dependence.** The ranking comes from one aggregator snapshot (CoinMarketCap). Other aggregators rank assets differently.
- **Exchange-specific prices.**
  - Binance prices and volumes reflect one venue, including its outages, listings and liquidity.
  - They are not market-wide prices, and Binance volume is not total market volume.
- **USDT denomination.** Prices are in USDT. USDT has occasionally traded away from 1 USD, so returns measured in USDT can differ from USD returns.
- **No market capitalization in archival data.**
  - Binance does not publish market cap, so market-cap concentration cannot be computed from the research dataset.
  - CoinGecko history (which includes market cap) is not stored at all, because persistence is disabled for compliance reasons.
- **Short CoinGecko history.** The Demo plan provides about one year, and the API terms prevent archiving it. CoinGecko data cannot support multi-year or reproducible studies in this project.
- **Provider revisions.** Providers may correct or remove historical data. Archived Binance datasets keep the exact files used, with checksums, but newly downloaded files may differ.

## Time and frequency

- **Calendar days.** Crypto trades 24/7, so daily data uses every calendar day (365 or 366 per year), not trading days. Annualization must use calendar-day conventions consistently.
- **UTC day boundary.** Daily candles close at 00:00 UTC, which is an arbitrary cut-off for a global market. Results at daily frequency may be sensitive to it.
- **Sampling instants differ between providers.** A Binance close is the last trade before 00:00 UTC; a CoinGecko point is a price at 00:00 UTC. Mixing them without explicit alignment introduces timing errors.
- **Missing days.**
  - Missing observations are reported, never filled.
  - Analyses must decide explicitly how to treat gaps, for example by computing pairwise statistics only on common days, and should report the effect.
  - Dropping days can bias volatility and correlation estimates.

## Research design (for Phases 4–5)

- **Small panel.** Nine assets over five years (about 1,826 daily observations per asset). Daily returns are serially dependent and heteroskedastic, so effective sample sizes are smaller than the row count.
- **Data snooping.**
  - The asset rule and period were fixed before any analysis.
  - Further choices (window lengths, regime thresholds) must be pre-registered or covered by sensitivity analysis, and the number of tests reported.
- **Correlation under high volatility.** Correlation coefficients depend on the volatility of the sample. Under a common-factor model, correlations measured in high-volatility periods are higher even with constant parameters (Forbes and Rigobon, 2002, *Journal of Finance* 57(5)), and selecting a sample on volatility can change measured correlation (Boyer, Gibson and Loretan, 1997/1999). See [research-methodology.md](research-methodology.md) for how the Research Lab handles this.
- **No causal claims.** The data supports descriptive and associational analysis only.

## Engineering

- **CoinGecko history persistence disabled.** CoinGecko API terms §6.1.2 ask for strong encryption of stored data. The cache was not encrypted, so storing CoinGecko history is disabled (see data-sources.md). Old expired caches should be deleted with `cryptovision-data purge-expired`.
- **Single-threaded downloads.** Binance archives are downloaded one request at a time with a short pause, so the first collection takes a long time: about 1,080 requests.
- **Byte-level hashes are version-dependent.** The SHA-256 of a stored Parquet file depends on the pyarrow version. Use `content_sha256` to compare datasets across machines.
- **Sequential timestamps assumed.** Validation checks daily data only (`frequency = "1d"`). Other frequencies are not supported yet.
