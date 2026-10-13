# Research Protocol: Cross-Asset Return Correlation in High- and Low-Volatility Regimes

- **Protocol ID:** `volatility-correlation`
- **Version:** 1.0
- **Status:** locally pre-specified. The protocol was written, and its hash frozen in `volatility-correlation-v1.lock.json`, before any regime-conditional statistic was computed on the empirical dataset. It is **not** registered with an external registry.
- **Machine-readable parameters:** `configs/experiments/volatility-correlation-v1.toml`. Where this text and the configuration differ, the configuration governs the computation and the difference is a protocol error to be reported.

## 0. Disclosure of prior data exposure

Before this protocol was written, the author computed descriptive statistics on the empirical dataset during development of the analytics engine (Phase 4). These included:

- full-period pairwise correlations (e.g., BTC/ETH Pearson about 0.81);
- per-asset volatility and drawdown;
- the range of the BTC 30-day rolling volatility (16.8% to 121.2% annualized);
- the range of the BTC/ETH 90-day rolling correlation (0.67 to 0.96, with the dates of the extremes).

No correlation was computed conditional on a volatility regime, and no relationship between rolling volatility and rolling correlation was examined. The analysis is therefore **not blind**. The design choices below are justified on methodological grounds and were not tuned to the data, but readers should weigh this exposure.

## 1. Research question

Do correlations among the daily returns of a fixed set of major cryptocurrencies differ between periods of relatively high and relatively low market volatility?

## 2. Hypotheses and estimand

**Primary estimand.** Δ = ρ̄_H − ρ̄_L.

- ρ̄_R is the equal-weighted arithmetic mean, over all N(N−1)/2 unique asset pairs, of the Pearson correlation of daily log returns computed on the days classified into regime R.
- H denotes the high-volatility regime and L the low-volatility regime.
- Diagonal elements are excluded and each pair is counted once.

**Hypotheses.**

- **H0 (primary, two-sided):** Δ = 0.
- **H1:** Δ ≠ 0.
- **Secondary, exploratory and directional:** Δ > 0, i.e. average correlation is higher in high-volatility regimes. This is reported as exploratory only and never replaces the two-sided primary hypothesis.

**What Δ measures.**

- Δ compares the *unconditional* (pooled) Pearson correlation of returns between two sets of days.
- It is not a measure of contagion or of a change in a structural dependence parameter.
- A non-zero Δ can arise from a genuine change in conditional correlation. It can also arise from the volatility composition of the regime samples (§6). The simulation gate (§10) checks the second mechanism.

**Alternative estimand (pre-specified fallback, §10).** Δ_z has the same definition but uses devolatilized returns, z_{i,t} = r_{i,t} / s_{i,t}. Here s_{i,t} is the sample standard deviation (ddof = 1) of asset *i*'s log returns over the 30 days t−30…t−1, using strictly past data only.

## 3. Data

| Item | Value |
|---|---|
| Dataset | `binance-spot-1d-top10-20210103` v1.0.0 (Binance Vision spot daily klines) |
| Content SHA-256 | `d2da4d6e7087d49b72f9b3e18a67aa72870714f3ef8a7723d4fcab62ab9d8d4e` (verified before every run) |
| Quote currency | USDT; exchange-specific Binance prices, not aggregated USD prices |
| Price | Daily close (last trade before 00:00 UTC) |
| Universe | BTC, ETH, LTC, XRP, DOT, BCH, ADA, BNB, LINK: 9 assets, 36 unique pairs |
| Universe rule | Fixed in Phase 3 from the 2021-01-03 snapshot (see `docs/data-methodology.md`); not revisited here |
| Observation period | Returns from 2021-01-02 to 2025-12-31 (1,825 daily log returns per asset) |
| Evaluation period | 2021-02-01 to 2025-12-31: the days on which the 30-day lagged proxy is defined (1,795 days) |

## 4. Returns and missing data

- **Returns:** daily log returns r_{i,t} = ln(P_{i,t} / P_{i,t−1}) between consecutive calendar days (Phase 4 policy). Returns are never bridged across gaps.
- **Missing data:** a day enters a regime sample only if all assets in the universe have a defined return (listwise deletion within the fixed universe). Every pair in a regime therefore uses the same days. The dataset currently has no missing days; the rule is stated for completeness.

## 5. Volatility proxy and regime classification (primary)

**Proxy.** The volatility proxy is the cross-sectional mean of the assets' lagged volatilities:

v_t = (1/N) Σ_i s_{i,t}

with s_{i,t} as defined in §2: 30-day lookback, all 30 past returns required, strictly past data.

**Why this proxy.**

1. **Strictly past information.** The day-*t* return never enters its own regime label, which removes the direct selection effect of classifying days by their own realized returns.
2. **Average of individual volatilities, not the volatility of an equal-weighted portfolio.** Portfolio volatility rises mechanically with cross-asset correlation, so a portfolio-volatility proxy would partly sort days by *past correlation*. Because correlation is persistent, that would label high-correlation periods as "high volatility" by construction.
3. **Not BTC alone.** Using BTC alone is tested as a robustness check.

**Regime rule.**

- Day *t* is **High** if v_t > m and **Low** otherwise.
- m is the median of v_t over the evaluation period. This is an in-sample threshold: it uses the distribution of the proxy over the whole period, so the classification is a descriptive split, not a real-time rule. A strictly past (trailing) threshold is tested as a robustness check.
- The median split gives balanced regimes of about 897 days each.

**What lagging does not solve.**

- Volatility clusters, so v_t predicts current volatility. High-regime days therefore still have higher *current* volatility than low-regime days.
- Lagging removes the mechanical selection on day *t*'s own returns. It does **not** remove:
  - composition effects, where pooled Pearson correlation depends on the mixture of volatility levels within each regime;
  - confounding by persistent market conditions;
  - structural change over time.
- These are evaluated by simulation (§10) and discussed as threats to validity (§12).

**Relation to the literature.**

- Forbes and Rigobon (2002) show that correlation coefficients are conditional on market volatility. Under a common-factor model with constant parameters, correlation measured in high-volatility periods is higher, and they propose a heteroskedasticity adjustment for tests of contagion.
- Boyer, Gibson and Loretan (1997, rev. 1999) show that conditioning a sample on high or low values can change measured correlation even when the true correlation is constant.
- Longin and Solnik (2001) specify the null distribution of conditional correlations before testing.

This protocol does not apply the Forbes–Rigobon adjustment to Δ. That adjustment is derived for a source-market framework with one crisis window, which does not map directly onto a 9-asset average with a symmetric median split. The interpretation of a non-zero Δ (§11) states explicitly that it may reflect common-factor volatility (interdependence) rather than a change in the dependence structure.

## 6. Observational unit and dependence

- **Observational unit:** the daily 9-asset return vector, labelled with its regime.
- **No rolling windows:** rolling-window correlations are **not** used as observations, because overlapping windows are not independent and would inflate the effective sample size.
- **Regimes are not runs:** a regime is a set of days, not a contiguous block, so Δ compares two day-sets that interleave over time.
- **Dependence:** returns show volatility clustering, cross-asset dependence and regime persistence. Inference therefore uses a block bootstrap (§7) that resamples whole days, preserving cross-asset dependence, in blocks that preserve short-range temporal dependence.

## 7. Inference

**Method.** The stationary bootstrap (Politis and Romano, 1994) over the evaluation days, in calendar order and wrapped circularly.

- Each day's full 9-asset return vector moves **jointly** with its regime label and, for Δ_z, its devolatilized values. Assets are never resampled independently.
- **Mean block length:** 20 days, so block lengths are geometric with p = 1/20. This is fixed in advance, not selected from the data. The choice balances preserving volatility and regime persistence (regimes from a 30-day lagged median split last weeks) against keeping enough distinct blocks (about 90 per replicate). Lengths 10 and 40 are robustness checks. Automatic block-length selection (Politis and White, 2004) was considered and not used, because it targets the variance of a univariate mean rather than a difference of pooled correlations between regimes.
- **Replications:** B = 2,000. Random seed 20261013, using NumPy `default_rng`.
- **Labels are fixed in resampling.** Regime labels and lagged volatilities are computed once, from the original series, and travel with their day. They are **not** recomputed inside replicates, because recomputing a 30-day lagged proxy on block-resampled data would mix blocks.
  - **Consequence:** the interval quantifies the sampling variability of the returns given the realized regime assignment. It does **not** include uncertainty from estimating the threshold or the proxy. Intervals are therefore conditional and probably somewhat too narrow, and this is reported.
- **Interval:** two-sided 95% percentile interval of the replicates of Δ. The bootstrap standard error (standard deviation of replicates) is also reported.
- **No p-value is reported.** The percentile interval is not converted into a p-value.
- **Replicate validity:** a replicate counts only if each regime contains at least 180 days. The number of rejected replicates is reported. If more than 1% are rejected, the result is flagged.

## 8. Decision and reporting rules

- **Inferential statement.** The primary result is "evidence of a regime difference at the 5% level" only if the 95% interval for Δ excludes 0. Otherwise the result is "no evidence of a difference with this design"; it is **never** "no difference".
  - Excluding 0 from a 95% percentile interval is used as an approximate two-sided 5% test by test inversion. Its validity depends on the bootstrap assumptions above and on passing the simulation gate (§10).
- **Effect size.** Δ is reported with its interval, along with ρ̄_H and ρ̄_L, the number of days per regime, the number of pairs (36) and the number of assets (9).
  - The smallest effect of interest is set at |Δ| = 0.05 in average correlation. This guides the description of practical relevance only and is not a test.
- **Fisher z:** not used for inference. Individual correlations are not z-transformed before averaging; the estimand is the plain average.
- **No causal interpretation.**

## 9. Robustness analyses (pre-specified)

Each check changes exactly one element of the primary specification. All are reported with point estimate, 95% interval and Bonferroni-adjusted interval (confidence 1 − 0.05/11 ≈ 99.55%). None replaces the primary result.

| ID | Change |
|---|---|
| R1 | Simple instead of log returns |
| R2 | Spearman instead of Pearson correlation |
| R3 | Volatility lookback of 60 days |
| R4 | Strictly past threshold: median of the proxy over the previous 365 days (evaluation starts once defined) |
| R5 | Upper-quartile split: High if the proxy exceeds its 75th percentile |
| R6 | Mean block length 10 |
| R7 | Mean block length 40 |
| R8 | Exclude 2021 (evaluation from 2022-01-01) |
| R9 | BTC's lagged 30-day volatility as the proxy |
| R10 | Exclude BNB (Binance's own exchange token): 8 assets, 28 pairs |
| R11 | The other estimand (Δ_z if the primary is Δ, Δ if the fallback made Δ_z primary) |

**Robustness statement.** The primary conclusion is described as *robust to the pre-specified checks* only if every robustness estimate has the same sign as the primary estimate. Otherwise the disagreeing checks are listed.

**Methodological illustration (not a robustness check).** Classification by a *contemporaneous* 30-day window (days t−29…t, including day *t*) shows the selection effect that §5 avoids.

## 10. Simulation gate (method validation before empirical inference)

The inference procedure must pass a synthetic validation before the empirical result may be interpreted inferentially.

**Settings.**

- 5 assets, 1,800 days (365 days in the short-sample scenario).
- M = 200 Monte Carlo datasets per scenario.
- B = 499 bootstrap replicates, mean block length 20.
- Seed 20261013.
- Each synthetic dataset goes through the same regime rule and bootstrap as the empirical data.
- **Pseudo-true value:** the population value of the estimand under each process is approximated by applying the estimator to one long simulated path of 200,000 days.

**Null scenarios** (constant conditional correlation ρ):

| ID | Process |
|---|---|
| N1 | i.i.d. Gaussian, ρ = 0.5, constant volatility |
| N2 | Common GARCH(1,1) volatility (α = 0.08, β = 0.90) shared by all assets, ρ = 0.5 |
| N3 | Common two-state Markov volatility (scale 1 or 2.5, stay probability 0.99), ρ = 0.5 |
| N4 | Asset-specific GARCH(1,1) volatility, one process per asset, ρ = 0.5 |
| N5 | As N2 with ρ = −0.2 (negative constant correlation) |
| N6 | As N2 with 365 days (short sample) |
| N7 | As N2 with 5% of daily returns missing at random per asset |
| N8 | As N3 with stay probability 0.998 (highly persistent regimes) |
| N9 | As N2 with ρ = 0 (independent assets) |

**Alternative scenarios** (dependence changes):

| ID | Process |
|---|---|
| A1 | Markov state drives both volatility (scale 1 or 2.5) and correlation (0.3 in the calm state, 0.6 in the volatile state) |
| A2 | One-factor model with constant loadings and factor variance switching (×4) by Markov state: conditional correlation rises with factor variance, as in Forbes and Rigobon's interdependence |
| A3 | Correlation switches 0.3/0.6 by a Markov state independent of constant volatility. The volatility regime is uninformative, so the pseudo-true Δ ≈ 0 |

**Metrics per scenario.**

- Rejection rate: the share of datasets whose 95% interval excludes 0.
- Coverage of the pseudo-true value.
- Mean bias against the pseudo-true value.
- Mean interval width.

Block-length sensitivity (10 and 40) is evaluated on N2 and N3.

**Gate criteria for the primary estimand.**

1. **G1.** In every null scenario where the pseudo-true value is within ±0.02 of 0, the rejection rate is ≤ 0.10. The nominal rate is 0.05; the 0.10 bound allows for Monte Carlo error with M = 200 and for mild undercoverage of percentile intervals.
2. **G2.** In every null scenario, |pseudo-true value| ≤ 0.02. In other words, the estimand itself is not materially non-zero when the conditional correlation is constant.
3. **G3.** Coverage of the pseudo-true value is ≥ 0.85 in every scenario.

**Pre-specified decision.**

- If Δ passes G1–G3, Δ is the primary estimand.
- If Δ fails G2 or G1 in any null scenario but Δ_z passes all three, **Δ_z becomes the primary estimand** and Δ moves to R11. Δ_z must be computed on the same simulations.
- If neither passes, the empirical study is reported **descriptively only**: estimates and intervals are labelled "not validated" and no inferential statement is made.

Power in A1 and A2 is reported descriptively, with no threshold.

## 11. Interpretation rules

- **A positive Δ** is consistent with higher average co-movement on high-volatility days. Possible mechanisms include a common factor whose variance rises (interdependence, as in Forbes and Rigobon), genuine dependence changes, or residual composition effects not captured by the simulations. The design cannot separate these.
- **The results are descriptive** of 9 surviving large-cap assets on one exchange in USDT, 2021–2025. They do not generalize to "the crypto market", other periods or other venues without further evidence.
- **Robustness and exploratory analyses** are labelled as such.

## 12. Threats to validity

- **Regime endogeneity and composition effects:** see §5. Mitigated by the lagged proxy, tested by simulation, not eliminated.
- **In-sample threshold:** the median uses the full-period distribution; R4 tests a trailing threshold.
- **Conditional intervals:** fixed labels in the bootstrap understate uncertainty (§7).
- **Structural change:** 2021–2025 includes several market phases; regimes partly coincide with calendar periods. R8 checks the effect of excluding 2021.
- **Selection and survivorship:** the universe excludes delisted BSV and stablecoins; all assets survived on Binance.
- **Data source:** Binance-only USDT prices, the UTC day cut-off, and possible USDT/USD deviations.
- **BNB:** Binance's own token may co-move with venue-specific events (R10).
- **Multiple testing:** one primary test. The 11 robustness checks carry Bonferroni-adjusted intervals and are not separate confirmatory claims.
- **Prior exposure:** see §0.

## 13. Changes to this protocol

Any change after freezing requires a new protocol version (v2, …) with the reason, the date and whether empirical results had been seen. Version 1 remains in the repository unchanged.

## References

- Boyer, B. H., Gibson, M. S., & Loretan, M. (1997, revised 1999). *Pitfalls in Tests for Changes in Correlations*. International Finance Discussion Papers No. 597, Board of Governors of the Federal Reserve System.
- Forbes, K. J., & Rigobon, R. (2002). No Contagion, Only Interdependence: Measuring Stock Market Comovements. *The Journal of Finance*, 57(5), 2223–2261. https://doi.org/10.1111/0022-1082.00494
- Longin, F., & Solnik, B. (2001). Extreme Correlation of International Equity Markets. *The Journal of Finance*, 56(2), 649–676.
- Politis, D. N., & Romano, J. P. (1994). The Stationary Bootstrap. *Journal of the American Statistical Association*, 89(428), 1303–1313.
- Politis, D. N., & White, H. (2004). Automatic Block-Length Selection for the Dependent Bootstrap. *Econometric Reviews*, 23(1), 53–70. https://doi.org/10.1081/ETC-120028836
