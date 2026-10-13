# Research Limitations

These limitations apply to every result produced by the Research Lab. They complement the data limitations in [limitations.md](limitations.md).

## Design

- **Regime endogeneity and composition.**
  - The lagged proxy prevents a day's own return from determining its regime.
  - It does not prevent composition effects: pooling days whose volatilities differ across assets changes unconditional correlations.
  - The simulations quantify this effect for a few stylized processes, which need not resemble real crypto returns.
- **In-sample threshold.** The primary median threshold uses the whole period's distribution of the proxy, so the regime split is descriptive, not a real-time rule. R4 uses a strictly past threshold.
- **Conditional intervals.** Bootstrap replicates keep the original regime labels, so the intervals ignore uncertainty in the proxy and threshold and are probably too narrow.
- **Percentile intervals.** Percentile bootstrap intervals can undercover when the estimator is biased or skewed, which is checked as coverage in the simulations.
- **Fixed block length.** A mean block length of 20 days is a judgement. R6 and R7 show the sensitivity.
- **One estimand.** An equal-weighted mean of 36 pairwise Pearson correlations hides heterogeneity across pairs. Pair-level values are reported descriptively but not tested individually.

## Data

- **Single venue and quote.** Binance spot closes in USDT; not aggregated USD prices, and not other exchanges.
- **Survivorship and selection.** Nine assets that survived on Binance from 2021 to 2025, chosen from a 2021 market-cap ranking. Stablecoins, wrapped tokens and the delisted BSV are excluded.
- **BNB.** BNB is Binance's own token and may react to venue-specific events (R10).
- **Period dependence.** 2021–2025 contains distinct market phases, and high- and low-volatility days cluster in them, so regime contrasts partly coincide with time periods (R8).
- **Daily frequency and UTC cut-off.** Intraday dynamics and timing differences between assets inside a day are not captured.

## Inference

- **One primary test.** The robustness checks are not independent confirmations; they reuse the same data.
- **Not blind.** Descriptive statistics of the dataset were seen before the protocol was written (protocol §0).
- **Not preregistered.** The protocol was frozen locally, before regime-conditional results were computed. It was not registered with an external registry.
- **Not peer reviewed.** No external review has taken place.

## Interpretation

- **No causal claims.** A difference in correlation can reflect interdependence through a common factor, genuine dependence changes, market-phase differences or residual composition effects.
- **Absence of evidence.** An interval that includes zero is not evidence that correlations are equal.
- **Not investment advice.** Results describe historical co-movement and are not trading or portfolio guidance.
