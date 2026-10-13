# Analytics Methodology

Definitions, assumptions and edge-case behavior of `cryptovision.analytics`. Every rule below is enforced in code and covered by tests (`tests/test_analytics_*.py`).

These analytics are **descriptive**. They summarize past observations of a specific dataset. They are not forecasts, confirmatory research results or investment advice. Hypothesis testing belongs to the planned Research Lab (Phase 5).

## 1. Inputs and alignment

Real observations enter only through `cryptovision.analytics.data.load_price_panel`. It calls the Phase 3 loader, which:

- verifies the file hashes and the content hash;
- refuses datasets that are not research-ready;
- refuses expired CoinGecko caches.

`build_price_panel` then turns long-format rows into a **price panel**:

- one column per asset;
- a **calendar-complete** daily index in UTC, with every calendar day from the first to the last day of the selection.

**Alignment policy.**

| Situation | Behavior |
|---|---|
| More than one provider, quote currency or frequency in the input | `IncompatibleDataError`. Nothing is converted. |
| Frequency other than `1d` | `IncompatibleDataError` |
| Timestamp not at 00:00 UTC (mixed daily boundaries), naive timestamp or missing timestamp | `IncompatibleDataError` |
| Two rows for the same asset and day | `DuplicateObservationError` |
| Price missing, non-finite, zero or negative | `InvalidPriceError` |
| Day without an observation | NaN in the panel. **Never interpolated or forward-filled.** |

Because the index has no missing days, "the previous row" always means "the previous calendar day", and a window of *w* rows always spans *w* calendar days.

**Price used.** Binance (`ohlcv`) datasets use the daily **close**: the last trade before 00:00 UTC of the next day, in the pair's quote currency (USDT). CoinGecko (`price_series`) datasets use the aggregated price sampled at 00:00 UTC. The context records which price column was used.

## 2. Returns

For asset *i* on day *t* with price *P*:

$$R_{i,t} = \frac{P_{i,t}}{P_{i,t-1}} - 1 \qquad r_{i,t} = \ln\frac{P_{i,t}}{P_{i,t-1}} = \ln(1 + R_{i,t})$$

*t − 1* is the previous **calendar day**. A return is labelled with the day it ends on. With Binance closes, $R_{i,t}$ is the close-to-close return over UTC day *t*.

**Status of each cell.** Each return cell has an explicit status:

| Status | Meaning | Return |
|---|---|---|
| `valid` | Prices on *t* and *t − 1* | defined |
| `first_observation` | First price of the asset in the panel | NaN |
| `missing_price` | No price on *t* | NaN |
| `after_gap` | Price on *t* but none on *t − 1* | NaN. The gap is **not bridged** into a multi-day return. |

A return of exactly 0 (an unchanged price) is a valid observation, not missing data. Returns are computed column by column, so they never cross assets.

**Worked example** (from the tests). Prices 100, 110, 99, 99:

- Simple returns: —, 0.10, −0.10, 0.00.
- Log returns: —, ln 1.1 = 0.0953102, ln 0.9 = −0.1053605, 0.
- Log returns add up over contiguous days: their sum equals ln(99/100).

**Simple or log?**

- Log returns add across time and are the default for volatility and correlation.
- Simple returns add across assets in a portfolio and are easier to read.
- Volatility differs between the two (for example, Cardano's annualized volatility is 97.5% with log returns and 100.6% with simple returns over 2021–2025). The return type is always recorded in the result metadata.

## 3. Volatility

**Daily volatility** is the sample standard deviation (ddof = 1) of the *n* defined returns:

$$\hat\sigma_d = \sqrt{\frac{1}{n-1}\sum_{t}(x_t - \bar x)^2}$$

**Annualized volatility**: $\hat\sigma_a = \hat\sigma_d\sqrt{N}$, with **N = 365** by default (configurable).

**Why 365.** Crypto assets trade every calendar day, so a year contains about 365 daily returns. The equity convention of 252 counts exchange trading days. Applied here, it would understate annual volatility by a factor of $\sqrt{252/365} \approx 0.83$.

**Assumptions and limits.** The √N scaling assumes independent, identically distributed returns. Crypto returns show volatility clustering and fat tails, so annualized figures are a convention for comparison. They are not a forecast and say nothing about future risk.

**Sample requirements.**

- ddof = 1 needs at least 2 values; fewer raises `InsufficientDataError`.
- Summary tables require **30 returns** by default; below that the value is NaN with status `insufficient`.
- A constant return series has volatility exactly 0.

**Worked example.** Returns 0.1, −0.1, 0:

- the mean is 0;
- the sum of squared deviations is 0.02;
- dividing by *n* − 1 = 2 gives 0.01;
- so σ_d = 0.1 and σ_a = 0.1 × √365 ≈ 1.9105.

## 4. Rolling volatility

$$\hat\sigma_{d}(t; w) = \text{sample std of the returns on days } t-w+1, \dots, t$$

- The window is **trailing** and labelled by its last day. It includes day *t* and never uses later data; a test checks that changing the last price only changes the last value.
- The window is *w* calendar days, because the index is calendar-complete. Default windows are 7, 30 and 90 days.
- **Minimum observations.** By default `min_periods = w`, so a window containing any missing return is undefined: rolling statistics never span gaps. A smaller `min_periods` (at least 2) can be set explicitly, in which case windows may contain gaps and the number of returns used is reported per window.
- The first *w* − 1 days are undefined. The first defined window ends on day *w* + 1 of the panel, because the first day has no return.
- Results are annualized with the same factor unless `annualize_result=False`.

## 5. Drawdown

Using observed prices only:

$$\text{Peak}_t = \max(P_0,\dots,P_t), \qquad DD_t = \frac{P_t}{\text{Peak}_t} - 1, \qquad \text{MDD} = \min_t DD_t$$

The result reports:

- MDD as a fraction ≤ 0, and its magnitude;
- the peak date and price, and the trough date and price;
- the recovery date;
- the duration in **calendar days** and in **observed steps** (these differ when there are gaps);
- the number of calendar days from peak to recovery.

**Tie-breaking.**

| Point | Rule |
|---|---|
| Trough | The earliest day on which MDD is reached |
| Peak | The latest day, on or before the trough, whose price equals the running peak at the trough (the decline starts the last time the price stood at that high) |
| Recovery | The first observed day after the trough with price ≥ the peak price. If none exists, `recovered = False` and no recovery date is given. |

**Edge cases.**

- A series that never declines (including a constant one) has MDD = 0, no peak or trough, and `recovered = None`.
- Fewer than 2 prices raises `InsufficientDataError`.
- Invalid prices raise `InvalidPriceError`.
- Days without a price have no drawdown value. Peaks are taken over observed prices only.

**Worked example.** Prices 100, 120, 90, 120, 60, 130:

- drawdowns are 0, 0, −25%, 0, −50%, 0;
- MDD = −50%, with the peak on day 4 (the later of the two 120s) and the trough on day 5;
- recovery is on day 6.

## 6. Correlation

**Pearson.** For the *n* days on which both assets have a defined return:

$$\rho = \frac{\sum (x_t-\bar x)(y_t-\bar y)}{\sqrt{\sum (x_t-\bar x)^2\,\sum (y_t-\bar y)^2}}$$

**Spearman** is the Pearson correlation of the ranks, with ties given their average rank. It is less sensitive to outliers and to non-linear but monotonic relationships.

**Pairwise deletion.**

- Each pair uses its own common days.
- An asset with a short history therefore reduces only its own pairs, not the whole matrix.
- The price is that different coefficients may rest on different days, so every result includes a **count matrix**, and the UI shows *n* on hover.
- Listwise deletion (one common sample for all assets) is not used.

**Undefined values** are NaN, with the reason recorded:

- `insufficient_overlap`: fewer than `min_overlap` common returns (default 30). This includes non-overlapping periods, where *n* = 0.
- `constant_series`: zero variance on the common days.

Coefficients are computed from returns, not prices; correlating trending price levels produces spurious values.

**Worked examples.**

- *x* = (1, 2, 3), *y* = (2, 4, 7) gives ρ = 15/√228 ≈ 0.99340.
- Spearman with ties: *x* = (1, 2, 2, 3), *y* = (1, 3, 2, 4) gives ranks (1, 2.5, 2.5, 4) and (1, 3, 2, 4), so ρ_s = 4.5/√22.5 ≈ 0.94868. This matches `scipy.stats.spearmanr`.

**Interpretation.** Correlation measures linear (Pearson) or monotonic (Spearman) co-movement over the sample. It does not imply causation. Correlations estimated within high-volatility periods are biased upward (Forbes & Rigobon, 2002), which matters for the Phase 5 research question.

## 7. Rolling correlation

Rolling correlation is computed for one pair over trailing windows of *w* calendar days (default 30, 90 or 180), using the days in the window where both returns exist.

- **Minimum observations:** `min_periods = w` by default, so windows containing a gap are undefined.
- **Undefined windows:** windows with a constant series are undefined.
- **Methods:** Pearson by default; Spearman is supported.
- **No look-ahead:** a test checks that future values never change past results.

## 8. Descriptive summary

`describe_assets` reports per asset:

- first and last observation;
- price observations;
- `missing_days`: calendar days without a price between the asset's first and last observation;
- defined returns;
- `undefined_returns`: returns undefined because of a preceding gap;
- mean, median, minimum and maximum daily return;
- daily and annualized volatility;
- maximum drawdown, with its peak and trough dates and whether it was recovered.

Return statistics need at least 30 returns, otherwise they are NaN. Sharpe ratios, VaR, beta and other risk-adjusted or predictive measures are intentionally not included.

## 9. Result metadata

Results carry a `ResultMetadata` record (`to_dict()` for JSON). It contains:

- **dataset:** id, version, content SHA-256, provider, quote currency, frequency, price column, synthetic flag and the asset-to-pair mapping;
- **selection:** assets and period;
- **calculation:** the calculation name, return type, correlation method, window, minimum observations and annualization factor;
- **samples:** sample counts per asset;
- **policy and version:** the missing-data policy and the CryptoVision version.

No data is duplicated into results. The dataset's `content_sha256`, together with these parameters, identifies the calculation.

## 10. Numerical notes

- **Precision:** calculations use float64 with no intermediate rounding. Formatting happens only in the UI.
- **Log returns:** computed as ln(P_t / P_{t−1}). This differs from ln P_t − ln P_{t−1} only by rounding, under 1e-14.
- **Constant inputs:** exactly constant samples are detected explicitly. They give volatility 0 and undefined correlation, rather than floating-point residue such as 1e-17.
- **Clipping:** correlations are clipped to [−1, 1] to remove rounding overshoot.

## 11. Verification

| Check | Method |
|---|---|
| Formulas | Hand-calculated examples (above) as exact or tolerance-based tests |
| Volatility | Compared with Python's `statistics.stdev` |
| Correlation | Compared with `scipy.stats.pearsonr` and `spearmanr` (SciPy is a test-only dependency) |
| Drawdown | Compared with a brute-force loop on a random walk |
| Real dataset (`test_analytics_real_dataset.py`, skipped when the git-ignored dataset is absent) | The Parquet file is read directly with pyarrow, bypassing the CryptoVision loader. Log returns, volatility, drawdown, BTC/ETH Pearson and Spearman, and sample rolling windows are recomputed with NumPy, `statistics` and SciPy, and compared. |

## 12. Source and currency limits

The research dataset contains Binance spot closes in **USDT**:

- These are one exchange's prices in a stablecoin, not aggregated USD prices.
- Statistics describe these 9 surviving large-cap pairs over 2021–2025. They do not describe the cryptocurrency market as a whole.
- Market capitalization is not available in this data.

See [limitations.md](limitations.md) and [data-sources.md](data-sources.md).
