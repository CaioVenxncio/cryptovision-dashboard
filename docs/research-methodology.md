# Research Methodology

This document explains the design of the Research Lab study and why each choice was made. The authoritative specification is the frozen protocol, `research/protocols/volatility-correlation-v1.md`. Results are in the generated report inside each result bundle.

## Question and estimand

**Question.** Do correlations among major cryptocurrency returns differ between periods of relatively high and low market volatility?

**Estimand.** Δ = ρ̄_H − ρ̄_L.

- ρ̄_R is the equal-weighted mean of the N(N−1)/2 unique pairwise Pearson correlations of daily log returns, computed on the days of regime R.
- **Pairs:** for the 9-asset universe there are 36 unique pairs. Each unordered pair is counted once and the diagonal is excluded.
- **Days:** all pairs in a regime use the same days (listwise complete). The effective sample of a regime is its number of days.

**Hypotheses.**

- H0: Δ = 0. H1: Δ ≠ 0, two-sided.
- The directional claim "correlations are higher when volatility is high" (Δ > 0) is exploratory only.

**Fisher z.** Individual correlations are not z-transformed before averaging, and the average is not z-transformed either. With dependent, heteroskedastic data the usual Fisher-z standard error, 1/√(n−3), does not apply, so inference comes from the bootstrap instead.

## Why regime definition is the central problem

Correlation estimates depend on how the sample was selected:

- **Selection on volatility.** Splitting days by realized volatility changes measured correlation even when the true dependence is constant. Boyer, Gibson and Loretan (1997, rev. 1999) show this for conditional correlations. Longin and Solnik (2001) specify the null distribution of conditional correlations before testing.
- **Interdependence.** Under a common-factor model with constant loadings, the correlation coefficient rises with factor variance. Forbes and Rigobon (2002) call this interdependence and propose a heteroskedasticity adjustment for contagion tests.

The design responds in three ways:

1. **A strictly past proxy.** v_t is the mean over assets of each asset's sample volatility on days t−30…t−1. A day's own return never affects its label, which removes the direct selection effect (§5 of the protocol).
2. **The mean of individual volatilities.** An equal-weight portfolio's volatility is not used, because it rises mechanically with cross-asset correlation and would sort days partly by past correlation, which is persistent.
3. **Simulation before interpretation.** Synthetic processes with constant conditional correlation but time-varying volatility are run through the same pipeline. They check whether the method "finds" a difference that is not there.

**What lagging does not solve.**

- Volatility clusters, so a high lagged proxy predicts high current volatility.
- When volatility varies differently across assets, pooling days with heterogeneous variances changes the unconditional Pearson correlation even if the conditional correlation is constant (a composition effect).
- Time-varying confounders and structural breaks remain.

The simulation scenario with asset-specific volatility (N4) exists to measure the composition effect.

**Alternative estimand.** Δ_z applies the same definition to devolatilized returns, r_{i,t} / s_{i,t}, where s_{i,t} is the strictly past 30-day volatility. It targets dependence net of each asset's recent volatility level. The protocol pre-specifies it as the fallback if Δ fails the gate.

The Forbes–Rigobon adjustment is not applied. It is derived for a source-market setting with a defined crisis window, which does not map onto a symmetric median split of a 9-asset average. A positive Δ is therefore interpreted as consistent with interdependence, not as evidence of contagion.

## Observational unit and dependence

- **Unit:** one day, meaning the 9-asset return vector with its regime label.
- **No rolling windows as observations:** overlapping rolling-window correlations are not used as observations. They share most of their days, and treating them as independent would be pseudoreplication.
- **Regimes are not runs:** a regime is a set of days that interleave with the other regime's days over time.

## Inference: stationary bootstrap

The stationary bootstrap (Politis and Romano, 1994) resamples blocks of consecutive days, with geometric block lengths and circular wrap-around.

- **Joint resampling.** Each day's full return vector moves with its label and its devolatilized values, which preserves cross-asset dependence.
- **Blocks.** Blocks preserve short-range serial dependence, such as volatility clustering and regime persistence. The mean block length is 20 days; 10 and 40 are robustness checks. Automatic selection (Politis and White, 2004) was not used, because it targets the mean of a single series.
- **Interval.** The 95% percentile interval of 2,000 replicates.
- **Fixed labels.** Labels are not recomputed inside replicates. A 30-day lagged proxy recomputed on block-resampled data would mix unrelated blocks.
  - The interval is therefore conditional on the realized regime assignment and ignores uncertainty in the threshold and proxy, so it is probably somewhat too narrow.
  - This is reported with every result.
- **No p-value.** The decision rule "the 95% interval excludes 0" is an approximate two-sided 5% test by inversion. Its validity rests on the simulation gate.

## Simulation gate

The protocol (§10) defines 9 null scenarios and 3 alternatives. For each scenario:

- 200 datasets of 5 assets × 1,800 days are generated (365 days in the short-sample scenario).
- Each dataset goes through the regime rule and a 499-replicate bootstrap.
- The pseudo-true value of each estimand is approximated by one 200,000-day path.

**Criteria.** In null scenarios:

- **G1:** the rejection rate is at most 0.10.
- **G2:** the pseudo-true value is within ±0.02 of 0.

In all scenarios:

- **G3:** coverage of the pseudo-true value is at least 0.85.

**Decision.** If Δ fails and Δ_z passes, Δ_z becomes primary. If neither passes, results are descriptive only.

**Short-sample scenario.** The empirical 180-day-per-regime minimum cannot be met in the 365-day scenario (N6), where regimes have about 167 days each. N6 uses a 60-day minimum, as recorded in the simulation output.

## Robustness and multiplicity

Eleven pre-specified checks each change one element of the specification: R1 simple returns, R2 Spearman, R3 60-day lookback, R4 trailing threshold, R5 upper-quartile split, R6 and R7 block lengths, R8 excluding 2021, R9 BTC proxy, R10 excluding BNB, R11 the other estimand.

- They are reported with 95% intervals and Bonferroni-adjusted intervals (1 − 0.05/11).
- They are sensitivity analyses, not additional confirmatory tests.
- The primary conclusion is called robust only if all robustness estimates share its sign.

## What can and cannot be concluded

- **What can be concluded:** whether, in this dataset and under this regime definition, average pairwise return correlation differs between high- and low-proxy days, and by how much.
- **What cannot be concluded:**
  - why correlations differ (contagion, interdependence or phase effects);
  - whether the pattern holds for other assets, exchanges, quote currencies, frequencies or periods;
  - anything causal.
- **A null result is not proof of equal correlations.**

## References

See the reference list in the protocol. All citations were checked against publisher or repository records: Forbes and Rigobon (2002); Boyer, Gibson and Loretan (1997, rev. 1999); Longin and Solnik (2001); Politis and Romano (1994); Politis and White (2004).

## Outcome of the v1 simulation gate (2026-10-13)

The frozen gate was run before any empirical regime statistic was computed: 200 datasets × 499 bootstrap replicates per scenario, 1,228 s. **Neither estimand passed.**

| Criterion | Δ (raw) | Δ_z (devolatilized) |
|---|---|---|
| G1: null rejection rate ≤ 0.10 | Fails in N4 (0.115, asset-specific volatility) and N5 (0.105, ρ = −0.2) | Passes in every evaluable null scenario (0.035–0.095) |
| G2: \|pseudo-true\| ≤ 0.02 in nulls | Passes (largest \|value\| 0.012, in N4) | Passes |
| G3: coverage ≥ 0.85 | Fails in A1 (0.585) and A2 (0.665) | Fails in A1 (0.810) and A2 (0.730) |
| N7 (5% missing returns) | Not evaluable: the proxy requires 30 complete past days, which almost never occurs | Same |

**Interpretation.**

- **Constant correlation, changing volatility.** The critical null test is passed by Δ_z. Raw Δ shows a small composition effect: a pseudo-true value of −0.012 and rejection rate 0.115 under asset-specific volatility.
- **When a true effect exists (A1, A2),** both estimands detect it in 86–100% of datasets, but their 95% intervals cover the pseudo-true value too rarely.
- **Exploratory follow-up (synthetic only, not part of the frozen protocol):** rerunning A1, A2 and N4 with mean block lengths 20, 60 and 120 left coverage essentially unchanged (A1 Δ_z 0.71–0.74; A2 Δ_z 0.76–0.80).
  - So the undercoverage is not a block-length problem.
  - It follows from holding regime labels fixed: the interval reflects variability given the realized regime assignment, while across samples the estimate also varies with how the labels line up with the latent volatility and correlation states.
- **Missing data.** N7 shows that the proxy definition cannot handle missing returns; a missing-tolerant proxy would be needed. The empirical dataset has no missing days, so this did not affect the empirical run.

**Decision.** As pre-specified (protocol §10), the empirical study was run as frozen and is reported **descriptively only**. All intervals are labelled "not validated" and no inferential statement is made. The protocol was not revised; this choice was confirmed by the project owner before the empirical run.

**What a future protocol version would need.**

- An inference procedure that accounts for regime-assignment uncertainty, for example re-estimating regimes inside a resampling scheme that keeps the proxy's look-back intact.
- A missing-tolerant proxy.
- A new freeze before any further empirical run.
