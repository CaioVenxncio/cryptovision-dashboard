"""Markdown research report generated from a result bundle's JSON files."""

from __future__ import annotations

from typing import Any

from cryptovision.research.reporting import (
    _analysis_row,
    _round,
    block_sensitivity_table,
    gate_summary,
    validation_table,
)

REFERENCES = """\
- Boyer, B. H., Gibson, M. S., & Loretan, M. (1997, revised 1999). *Pitfalls in Tests for \
Changes in Correlations*. International Finance Discussion Papers No. 597, Board of Governors \
of the Federal Reserve System.
- Forbes, K. J., & Rigobon, R. (2002). No Contagion, Only Interdependence: Measuring Stock \
Market Comovements. *The Journal of Finance*, 57(5), 2223-2261. \
https://doi.org/10.1111/0022-1082.00494
- Longin, F., & Solnik, B. (2001). Extreme Correlation of International Equity Markets. \
*The Journal of Finance*, 56(2), 649-676.
- Politis, D. N., & Romano, J. P. (1994). The Stationary Bootstrap. *Journal of the American \
Statistical Association*, 89(428), 1303-1313.
- Politis, D. N., & White, H. (2004). Automatic Block-Length Selection for the Dependent \
Bootstrap. *Econometric Reviews*, 23(1), 53-70. https://doi.org/10.1081/ETC-120028836"""


def _estimand_text(estimand: str) -> str:
    if estimand == "raw":
        return "average pairwise Pearson correlation of daily log returns"
    return (
        "average pairwise Pearson correlation of devolatilized daily log returns (each return "
        "divided by the asset's strictly-past 30-day volatility)"
    )


def _illustration_text(illustration: dict[str, Any] | None, primary_delta: float) -> str:
    if not illustration:
        return ""
    return (
        "**Methodological illustration (not a robustness check).** Classifying days by a "
        "contemporaneous 30-day window that includes the day itself gives "
        f"Δ = {_round(illustration['delta'])} (interval [{illustration['ci_low']:+.4f}, "
        f"{illustration['ci_high']:+.4f}]), compared with {_round(primary_delta)} for the "
        "strictly-past primary rule. The difference shows how much the regime definition "
        "itself shapes the estimate."
    )


def _discussion(results: dict[str, Any]) -> str:
    primary = results["primary"]
    interpretation = results["interpretation"]
    paragraphs = [
        "**What the evidence supports.** " + interpretation["inference"],
        "**What it does not support.** The design compares unconditional correlations of two "
        "sets of days. A non-zero difference is consistent with several mechanisms: a common "
        "factor whose variance rises in turbulent periods (interdependence in the sense of "
        "Forbes and Rigobon), genuine changes in dependence, differences between market phases "
        "that coincide with volatility, or residual composition effects. The study cannot "
        "separate these and makes no causal claim.",
        "**Robustness.** " + interpretation["robustness"],
        f"**Scope.** The average correlation in the low-volatility regime is "
        f"{primary['rho_low']:.3f}, so these assets co-move strongly even in calm periods; any "
        "difference concerns the degree of an existing co-movement among nine large, surviving "
        "assets on one exchange.",
    ]
    if not results["validated"]:
        paragraphs.insert(
            0,
            "**Method not validated.** No estimand passed the pre-specified simulation gate, so "
            "the numbers in this report are descriptive and carry no inferential weight.",
        )
    return "\n\n".join(paragraphs)


def render_report(
    results: dict[str, Any], validation: dict[str, Any], manifest: dict[str, Any]
) -> str:
    primary = results["primary"]
    lock = results["protocol_lock"]
    dataset = results["dataset"]
    interpretation = results["interpretation"]
    validated = results["validated"]
    estimand = results["primary_estimand"]
    estimand_text = _estimand_text(estimand)
    status = (
        "validated by the pre-specified simulation gate"
        if validated
        else "NOT validated (results are descriptive only)"
    )
    environment = manifest.get("environment", {})
    git = environment.get("git", {})
    settings = validation["settings"]
    robustness_rows = "\n".join(_analysis_row(item) for item in results["robustness"])
    warnings = [w for item in [primary, *results["robustness"]] for w in item["warnings"]]
    warnings_section = (
        "## Warnings\n\n" + "\n".join(f"- {w}" for w in warnings) + "\n\n" if warnings else ""
    )
    lock_files = ", ".join(f"`{name}` {digest[:12]}…" for name, digest in lock["files"].items())
    ci = f"[{primary['ci_low']:+.4f}, {primary['ci_high']:+.4f}]"

    synthetic_banner = (
        "> **SYNTHETIC DATA.** This run used a synthetic dataset. The numbers are not market "
        "observations and are not empirical findings.\n\n"
        if results.get("synthetic_data")
        else ""
    )
    return f"""{synthetic_banner}# Cross-Asset Return Correlation in High- and Low-Volatility Regimes

*A locally pre-specified study of nine cryptocurrencies traded on Binance against USDT, \
{primary["first_day"]} to {primary["last_day"]}. Generated by the CryptoVision Research Lab. \
Not peer reviewed; the protocol was not externally registered.*

## Abstract

We ask whether the average pairwise correlation of daily returns among nine large \
cryptocurrencies differs between days of relatively high and relatively low market volatility. \
Days are classified by a strictly-past volatility proxy (the cross-sectional mean of 30-day \
lagged asset volatilities) split at its sample median. The primary estimand is the difference Δ \
in the {estimand_text} between the high- and low-volatility regimes. Inference uses a stationary \
block bootstrap that resamples whole days jointly across assets. The procedure was evaluated on \
synthetic processes before the empirical run and is **{status}**. The estimate is \
Δ = {_round(primary["delta"])} (95% interval {ci}; {primary["n_high"]} high- and \
{primary["n_low"]} low-volatility days; {primary["n_assets"]} assets, {primary["n_pairs"]} \
pairs). {interpretation["inference"]} The results describe exchange-specific USDT prices of nine \
surviving assets in one period and do not identify causal mechanisms.

## 1. Introduction

Correlations between crypto assets matter for diversification and for understanding market \
structure. A common claim is that correlations rise in turbulent markets. Testing it is \
delicate: correlation coefficients depend on the volatility of the sample in which they are \
measured (Forbes and Rigobon, 2002), and splitting a sample by volatility can change measured \
correlations even when the underlying dependence is constant (Boyer, Gibson and Loretan, \
1997/1999; Longin and Solnik, 2001). This study is designed around that difficulty.

## 2. Research question and hypotheses

- **Question:** do correlations among major cryptocurrency returns differ between periods of \
relatively high and low market volatility?
- **Primary estimand:** Δ = ρ̄_H − ρ̄_L, the difference between regimes in the equal-weighted \
mean of the {primary["n_pairs"]} unique pairwise correlations ({estimand_text}).
- **H0:** Δ = 0. **H1 (two-sided):** Δ ≠ 0. The directional hypothesis Δ > 0 is exploratory.

## 3. Methodological considerations

- **Endogenous regimes.** If regimes are defined from the same returns whose correlations are \
compared, high-volatility samples can show different correlations by construction. The proxy \
uses only returns from days t−30…t−1, so a day's own return never determines its regime. \
Lagging does not remove composition effects of volatility clustering, persistent confounding \
or structural change.
- **Proxy choice.** The mean of individual volatilities is used instead of the volatility of an \
equal-weighted portfolio, whose variance rises with correlation and would partly sort days by \
past correlation.
- **Dependence.** Returns are dependent over time in their second moments and across assets. \
Overlapping rolling-window correlations are not used as observations; the unit is the daily \
cross-section of returns, resampled in blocks.
- **Interdependence.** Under a common-factor model, correlation rises with factor variance \
(Forbes and Rigobon, 2002). A non-zero Δ can reflect such interdependence.

## 4. Data

| Item | Value |
|---|---|
| Dataset | `{dataset["id"]}` v{dataset["version"]} |
| Content SHA-256 | `{dataset["content_sha256"]}` |
| Source | Binance Vision spot daily klines (CC BY-NC-SA 4.0); daily closes in **USDT** on one \
exchange, not aggregated USD prices |
| Assets | {", ".join(primary["assets"])} |
| Evaluation days | {primary["first_day"]} to {primary["last_day"]} ({primary["n_days"]} days; \
incomplete days excluded: {primary["excluded_incomplete_days"]}) |

**Asset selection.** The non-stablecoin, non-wrapped top-10 assets by market capitalization in \
the CoinMarketCap snapshot of 2021-01-03, restricted to assets with Binance USDT spot archives \
for the whole period. BSV (eligible, but delisted from Binance) is excluded, so the universe \
consists of survivors on one exchange.

## 5. Methods

- **Returns:** daily log returns ln(P_t / P_(t−1)) of closes on consecutive calendar days.
- **Volatility proxy:** v_t, the mean over assets of each asset's sample standard deviation \
(ddof = 1) of returns on days t−30…t−1.
- **Regimes:** High if v_t exceeds its median over the evaluation period, Low otherwise. This \
is an in-sample, descriptive split; a strictly-past threshold is a robustness check (R4).
- **Estimator:** Pearson correlations on all days of a regime (listwise complete), averaged \
over unique pairs with equal weights; Δ is the High minus Low average.
- **Inference:** stationary bootstrap (Politis and Romano, 1994), mean block length \
{primary["mean_block_length"]} days, {primary["replications"]} replications. Whole days are \
resampled jointly with their fixed regime labels; 95% percentile interval; no p-value. Because \
labels are not re-estimated in replicates, intervals are conditional on the realized regime \
assignment and probably somewhat too narrow.

## 6. Experimental protocol

The protocol (version {results["protocol_version"]}) and configuration were frozen at \
**{lock["frozen_at"]}** ({lock_files}). Regime-conditional statistics on the empirical data were \
computed only after freezing. Descriptive analytics on the same dataset had been seen before the \
protocol was written (disclosed in protocol §0).

## 7. Simulation validation

The procedure was applied to synthetic processes with known dependence \
({settings["n_assets"]} assets, {settings["n_days"]} days, {settings["replications"]} datasets \
per scenario, {settings["bootstrap_replications"]} bootstrap replicates). "Rejection" means the \
95% interval excludes zero; in null scenarios its nominal rate is 0.05.

{validation_table(validation)}

**Block-length sensitivity**

{block_sensitivity_table(validation)}

**Gate decision**

{gate_summary(validation)}

## 8. Results

| Quantity | Value |
|---|---|
| Primary estimand | `{estimand}` ({"validated" if validated else "not validated"}) |
| ρ̄ high-volatility regime | {primary["rho_high"]:.4f} ({primary["n_high"]} days) |
| ρ̄ low-volatility regime | {primary["rho_low"]:.4f} ({primary["n_low"]} days) |
| **Δ = ρ̄_H − ρ̄_L** | **{_round(primary["delta"])}** |
| 95% bootstrap interval | {ci} |
| Bootstrap standard error | {primary["standard_error"]:.4f} |
| Assets / unique pairs | {primary["n_assets"]} / {primary["n_pairs"]} |
| Rejected replicates | {primary["rejected_replicates"]} of {primary["replications"]} |

- {interpretation["inference"]}
- {interpretation["relevance"]}
- {interpretation["direction"]}

## 9. Robustness checks (pre-specified)

Bonferroni-adjusted intervals use confidence level \
{results["bonferroni_confidence_level"]:.4f}. These are sensitivity analyses, not separate \
confirmatory tests; none replaces the primary result.

| ID | Check | Estimand | Δ | 95% interval | Bonferroni interval | ρ̄ High | ρ̄ Low | Days H/L | Assets |
|---|---|---|---|---|---|---|---|---|---|
{_analysis_row(primary)}
{robustness_rows}

{interpretation["robustness"]}

{_illustration_text(results.get("illustration"), primary["delta"])}

## 10. Discussion

{_discussion(results)}

## 11. Threats to validity

- **Regime endogeneity and composition.** The lagged proxy removes selection on a day's own \
return but not composition effects of volatility clustering. The simulations (Section 7) show \
their size under the processes studied, which may not match real data.
- **In-sample threshold and fixed labels.** Both make the interval conditional and possibly too \
narrow.
- **Time confounding.** High- and low-volatility days cluster in time, so regime differences can \
partly reflect different market phases. R8 excludes 2021.
- **Selection.** Nine assets surviving on Binance, chosen by a 2021 ranking; stablecoins, \
wrapped tokens and delisted assets are excluded.
- **Measurement.** Exchange-specific USDT closes at the 00:00 UTC cut-off; possible USDT/USD \
deviations; BNB is Binance's own token (R10).
- **Multiple testing.** One primary analysis; robustness intervals are also Bonferroni-adjusted.
- **Prior exposure.** Descriptive statistics of the dataset were seen before the protocol was \
written.

## 12. Limitations

The study describes one exchange, one quote currency, nine assets and five years of daily data. \
Correlations are linear (Pearson); tail dependence, intraday dynamics and market capitalization \
are not examined. The interval ignores uncertainty in the regime threshold. No causal claim is \
made.

## 13. Reproducibility

- Code: CryptoVision {environment.get("cryptovision")} (git `{git.get("commit")}`, working tree \
dirty: {git.get("working_tree_dirty")}).
- Environment: Python {environment.get("python")}, NumPy {environment.get("numpy")}, pandas \
{environment.get("pandas")}, {environment.get("platform")}.
- Seeds: bootstrap {results["seed"]}, simulation {settings["seed"]} (streams derived with \
`numpy.random.SeedSequence`).
- Procedure: see `docs/research-reproducibility.md`. Result files other than `manifest.json` \
are expected to be byte-identical for identical inputs, platform and library versions; \
cross-platform bitwise identity has not been tested.

## 14. Conclusion

{interpretation["inference"]} {interpretation["relevance"]} The findings concern average linear \
co-movement of nine Binance USDT pairs in {primary["first_day"][:4]}–{primary["last_day"][:4]} \
under a lagged-volatility regime split. They are not evidence about causal contagion or about \
the cryptocurrency market as a whole.

{warnings_section}## References

{REFERENCES}

---
Data attribution: Binance Vision (https://data.binance.vision), CC BY-NC-SA 4.0. This report \
contains derived statistics only, not market data.
"""
