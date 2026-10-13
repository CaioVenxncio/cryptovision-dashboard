# Historical Data Sources

This document records the evaluation behind CryptoVision's historical data design. It was assessed on 2026-10-13. Provider terms and limits change, so re-check the linked sources before relying on them.

## Summary

| | CoinGecko Demo API | Binance Vision public data |
|---|---|---|
| Role in CryptoVision | Live Market Explorer (in-memory cache only); storing history is **disabled** | **Archival** research datasets |
| What a price is | Aggregated price across venues, sampled at 00:00 UTC | One exchange's candle (open/high/low/close) for one pair |
| Quote currency | USD (and other fiat/crypto) | The pair's quote asset, e.g. USDT. **Not USD.** |
| Market capitalization | Yes | No |
| Volume | 24h aggregated volume in USD | Base-asset and quote-asset volume on Binance only |
| History available | About 1 year on the Demo plan | Since each pair's Binance listing (BTCUSDT since 2017-08) |
| Granularity used | Daily (automatic for ranges above 90 days) | Daily (`1d` candles) |
| Cost | 1 API credit per asset request; 10,000 credits per month | Free; no key |
| Integrity check | None published | SHA-256 `.CHECKSUM` file per archive |
| Storage and redistribution | Storage discouraged; caches must be refreshed every 24 hours | CC BY-NC-SA 4.0; academic research permitted; no hosting or sublicensing |
| Delisted assets | Not available as history once delisted | Only pairs that existed on Binance |

**Decision.** Archival, hash-pinned research datasets come only from Binance Vision. CoinGecko history is supported only as a short-lived local cache, which can be used for comparison but never archived. The two sources are stored in separate schemas and never merged.

## CoinGecko Demo API

**Endpoint.** `GET /coins/{id}/market_chart?vs_currency=usd&days=N` ([docs](https://docs.coingecko.com/reference/coins-id-market-chart)).

- **Response:** three arrays, `prices`, `market_caps` and `total_volumes`, each made of `[timestamp, value]` pairs. The documentation says only "UNIX" time; the 13-digit example values and the observed responses are milliseconds.
- **Granularity:** without `interval`, 1 day of range gives 5-minute data, 2–90 days give hourly data, and above 90 days gives daily data at 00:00 UTC. CryptoVision uses this documented automatic rule and does not send `interval=daily`, so it does not depend on plan-specific behavior for that parameter.
- **Publication delay:** the last completed UTC day is available about 10 minutes after midnight.
- **Provisional last point:** the response ends with an intraday point for the current time. Observed on 2026-10-13: 366 points for `days=365`, namely 365 daily points plus one intraday point. CryptoVision drops that point with a recorded warning.
- **History:** the [pricing page](https://www.coingecko.com/en/api/pricing) lists about 1 year of daily and hourly history for the Demo plan, so requests are capped at 365 days.
- **Budget:** 10,000 calls per month. One request per asset.

**Terms** ([API Terms](https://www.coingecko.com/en/api_terms)):

- §6.1 discourages caching or storing Data.
- §6.1.1 says caches should be refreshed at least every 24 hours.
- §6.1.2 asks for strong encryption and security measures on stored Data.
- §6.2 prohibits duplicating, storing or deriving from Data except as expressly permitted.
- §4.4 requires a prominent "Powered by CoinGecko" attribution.

**Consequence.** A versioned CoinGecko dataset, kept for months and verified by hash, conflicts with §6.1.1 and §6.2. CryptoVision therefore implements:

- CoinGecko datasets marked `retention: ephemeral`, with `expires_at` 24 hours after retrieval.
- A loader that refuses expired caches.
- A `purge-expired` command that deletes them.
- No CoinGecko data committed to Git.

**Compliance disposition (Phase 5, 2026-10-13).**

- **Decision:** storing CoinGecko history on disk is **disabled**.
- **Why:**
  - §6.1.2 asks that "strong encryption and other security measures" be applied to stored Data, and the cache files are plain Parquet.
  - Expiry alone does not satisfy an encryption requirement.
  - Full-disk encryption is outside the application's control and is not necessarily what the terms mean.
  - Adding application-level encryption would need key management that cannot be justified for an optional comparison feature.
- **What changed:**
  - `cryptovision-data collect` refuses CoinGecko configurations before making any request.
  - `store_dataset` refuses to persist CoinGecko data unless a caller passes an explicit opt-in flag, which only the tests use.
  - The loader still refuses expired caches.
- **What is not affected:** the Market Explorer keeps fetched data only in process memory (Streamlit cache, at most 15 minutes), which is not stored Data on disk.
- **Residual risks:**
  - Caches created before this change may still exist on disk. They are expired and refused; delete them with `cryptovision-data purge-expired`.
  - Whether in-memory caching or Streamlit's internal handling counts as "storage" under the terms is a legal question this project does not answer.
  - Re-enabling persistence would need a reviewed encryption and retention design.

## Binance Vision

**Archives** ([repository](https://github.com/binance/binance-public-data)):

- **Layout:** `https://data.binance.vision/data/spot/monthly/klines/{PAIR}/1d/{PAIR}-1d-{YYYY-MM}.zip`, each with a `.CHECKSUM` (SHA-256) file.
- **Contents:** each zip holds one CSV with 12 columns: open time, open, high, low, close, base volume, close time, quote volume, trade count, taker-buy base volume, taker-buy quote volume, and an ignored column.
- **Timestamp units:** spot timestamps are milliseconds before 2025-01-01 and microseconds afterwards. CryptoVision detects the unit per value.
- **Headers:** the documentation does not state whether CSVs have a header row. CryptoVision accepts an optional header and rejects an archive that has no data rows.

**Coverage verified on 2026-10-13.** These counts come from the public S3 listing of monthly `1d` archives (`s3-ap-northeast-1.amazonaws.com/data.binance.vision`):

| Pair | First month | Last month | Months in 2021-01 – 2025-12 |
|---|---|---|---|
| BTCUSDT, ETHUSDT | 2017-08 | 2026-09 | 60 / 60 |
| LTCUSDT | 2017-12 | 2026-09 | 60 / 60 |
| XRPUSDT | 2018-05 | 2026-09 | 60 / 60 |
| ADAUSDT | 2018-04 | 2026-09 | 60 / 60 |
| BNBUSDT | 2017-11 | 2026-09 | 60 / 60 |
| LINKUSDT | 2019-01 | 2026-09 | 60 / 60 |
| BCHUSDT | 2019-11 | 2026-09 | 60 / 60 |
| DOTUSDT | 2020-08 | 2026-09 | 60 / 60 |
| BSVUSDT | — | — | 0 / 60 (no archives) |

The existence of an archive does not guarantee a candle for every day. The day-level completeness of each dataset is measured by validation and recorded in its manifest.

**Terms** ([TERMS_AND_CONDITIONS.md](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md)):

- §3.1: the data is licensed under CC BY-NC-SA 4.0.
- §4.1: permitted non-commercial uses include academic research.
- §4.3: the data must not be sold, sub-licensed or hosted.
- §4.5: derivative works must credit Binance Vision.
- §10.1, §10.3: the data comes with no warranty of accuracy or completeness.

**Interpretation for this project.** Downloading and analyzing the data locally for academic research is permitted. Committing raw or normalized Binance data to a public repository could amount to hosting or redistribution, so CryptoVision does not do it: `data/` is git-ignored. Published research outputs, such as tables and figures, should credit Binance Vision and carry a non-commercial license compatible with CC BY-NC-SA 4.0. If in doubt, seek legal advice; this document is not legal advice.

## Methodological consequences

- **USDT is not USD.** Binance prices are quoted in USDT, a stablecoin whose USD value has occasionally deviated from 1. CryptoVision never converts USDT to USD implicitly; the quote currency is stored on every row. Any conversion would need a documented USDT/USD series.
- **Exchange-specific prices.** A Binance close is one venue's last trade of the UTC day. It is not a market-wide price, and venue-specific events (outages, liquidity shocks) affect it.
- **Different sampling instants.** A CoinGecko daily point is a price *at* 00:00 UTC. A Binance daily close is the last trade *before* 00:00 UTC of the next day. Comparing the two needs explicit alignment, with Binance day D close compared to CoinGecko day D+1.
- **No market capitalization in Binance data.** Market-cap concentration measures cannot be computed from the archival dataset. Volume-based concentration is possible but measures Binance trading activity only.
