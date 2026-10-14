"""Historical Analytics page: descriptive analytics on validated local datasets.

Reads only local datasets through the validated loader; never makes network
requests. Expired or not research-ready datasets are not offered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from cryptovision.analytics.alignment import PricePanel
from cryptovision.analytics.correlation import (
    DEFAULT_MIN_OVERLAP,
    correlation_matrix,
    rolling_correlation,
)
from cryptovision.analytics.correlation import (
    DEFAULT_ROLLING_WINDOWS as CORRELATION_WINDOWS,
)
from cryptovision.analytics.data import load_price_panel
from cryptovision.analytics.descriptive import describe_assets
from cryptovision.analytics.exceptions import AnalyticsError
from cryptovision.analytics.models import CorrelationMethod, ReturnType
from cryptovision.analytics.returns import compute_returns
from cryptovision.analytics.volatility import (
    DEFAULT_ROLLING_WINDOWS as VOLATILITY_WINDOWS,
)
from cryptovision.analytics.volatility import rolling_volatility
from cryptovision.data.errors import DataPipelineError
from cryptovision.data.pipeline import list_datasets
from cryptovision.data.provenance import DatasetManifest
from cryptovision.ui import analytics_charts, design

DEFAULT_ASSETS = ("bitcoin", "ethereum", "cardano")
MAX_DEFAULT_ASSETS = 3


@dataclass(frozen=True)
class DatasetOption:
    path: Path
    manifest: DatasetManifest

    @property
    def label(self) -> str:
        tag = " [SYNTHETIC]" if self.manifest.synthetic else ""
        return f"{self.manifest.dataset_id} v{self.manifest.dataset_version}{tag}"


def available_datasets(data_dir: Path, now: datetime | None = None) -> list[DatasetOption]:
    """Research-ready, unexpired datasets; real datasets are listed before synthetic ones."""
    now = now or datetime.now(UTC)
    options = [
        DatasetOption(path, manifest)
        for path, manifest in list_datasets(data_dir)
        if manifest.status == "research_ready" and not manifest.is_expired(now)
    ]
    return sorted(options, key=lambda option: (option.manifest.synthetic, option.label))


@st.cache_data(max_entries=4, show_spinner=False)
def _load_panel(path: str, content_sha256: str) -> PricePanel:
    # content_sha256 is part of the cache key, so a rebuilt dataset is reloaded.
    return load_price_panel(Path(path))


def default_assets(assets: tuple[str, ...]) -> list[str]:
    preferred = [asset for asset in DEFAULT_ASSETS if asset in assets]
    return preferred or list(assets[:MAX_DEFAULT_ASSETS])


SUMMARY_COLUMNS = {
    "first_observation": "First day",
    "last_observation": "Last day",
    "return_observations": "Returns (n)",
    "missing_days": "Missing days",
    "mean_return": "Mean daily return",
    "median_return": "Median daily return",
    "min_return": "Min daily return",
    "max_return": "Max daily return",
    "daily_volatility": "Daily volatility",
    "annualized_volatility": "Annualized volatility",
    "max_drawdown": "Max drawdown",
    "drawdown_peak": "Drawdown peak",
    "drawdown_trough": "Drawdown trough",
    "drawdown_recovered": "Recovered",
}


def summary_display(table: pd.DataFrame) -> pd.DataFrame:
    return table.loc[:, list(SUMMARY_COLUMNS)].rename(columns=SUMMARY_COLUMNS)


def _meta(option: DatasetOption, panel: PricePanel) -> list[tuple[str, str]]:
    manifest, context = option.manifest, panel.context
    pairs = sorted(set(context.pairs.values()))
    pairs_text = ", ".join(pairs[:3]) + (f" +{len(pairs) - 3}" if len(pairs) > 3 else "")
    return [
        ("Dataset", f"{manifest.dataset_id} v{manifest.dataset_version}"),
        ("Provider", context.provider),
        ("Pairs", pairs_text or "—"),
        ("Quote", context.quote_currency),
        ("Frequency", "1 day, UTC close"),
        ("Available", f"{manifest.actual_period.start} → {manifest.actual_period.end}"),
        ("SHA-256", f"{(context.content_sha256 or '')[:12]}…"),
    ]


def _context_notice(panel: PricePanel) -> None:
    context = panel.context
    if context.synthetic:
        design.demo_notice("This dataset is a deterministic synthetic random walk.")
    elif context.provider == "binance_vision":
        st.info(
            f"**Binance spot prices in {context.quote_currency}.** Daily closes on one exchange, "
            "quoted in a stablecoin; not aggregated USD market prices. Data: Binance Vision "
            "(CC BY-NC-SA 4.0).",
            icon=":material/info:",
        )


def render(data_dir: Path) -> None:
    options = available_datasets(data_dir)
    if not options:
        design.page_header(
            "Historical data",
            "Historical Analytics",
            "Descriptive statistics of past daily returns from validated local datasets.",
        )
        st.info(
            "**No research-ready local dataset was found.** Build the research dataset with "
            "`cryptovision-data collect configs/datasets/binance-spot-1d-top10-20210103.toml "
            "--yes`, create synthetic data with `cryptovision-data synthetic`, or start the "
            "offline demo with `cryptovision-demo`.",
            icon=":material/database:",
        )
        return

    header = st.container()
    controls = st.container()
    index = controls.selectbox(
        "Dataset", range(len(options)), format_func=lambda i: options[i].label
    )
    option = options[index]
    try:
        panel = _load_panel(str(option.path), option.manifest.content_sha256)
    except (AnalyticsError, DataPipelineError) as exc:
        with header:
            design.page_header("Historical data", "Historical Analytics", "Dataset unavailable.")
        st.error(f"The dataset could not be loaded safely: {exc}", icon=":material/gpp_bad:")
        return

    with header:
        design.page_header(
            "Historical data",
            "Historical Analytics",
            "Descriptive statistics of past daily returns. They describe history only; they are "
            "not forecasts, research findings or investment advice.",
            meta=_meta(option, panel),
            tags=[("Synthetic", "warn")] if panel.context.synthetic else [("Local · verified", "")],
        )
        _context_notice(panel)

    with controls:
        selection_cols = st.columns([5, 4])
        assets = selection_cols[0].multiselect(
            "Assets", panel.assets, default=default_assets(panel.assets)
        )
        period = selection_cols[1].slider(
            "Period (UTC days)",
            min_value=panel.start,
            max_value=panel.end,
            value=(panel.start, panel.end),
            format="YYYY-MM-DD",
        )
        settings_cols = st.columns(4)
        return_type = settings_cols[0].radio(
            "Return type",
            [ReturnType.LOG, ReturnType.SIMPLE],
            format_func=lambda value: "Log" if value is ReturnType.LOG else "Simple",
            horizontal=True,
            help="Log: ln(P_t / P_t-1). Simple: P_t / P_t-1 − 1. Consecutive calendar days only.",
        )
        vol_window = settings_cols[1].radio(
            "Volatility window (days)", VOLATILITY_WINDOWS, index=1, horizontal=True
        )
        corr_window = settings_cols[2].radio(
            "Correlation window (days)", CORRELATION_WINDOWS, index=1, horizontal=True
        )
        method = settings_cols[3].radio(
            "Correlation method",
            [CorrelationMethod.PEARSON, CorrelationMethod.SPEARMAN],
            format_func=lambda value: value.value.capitalize(),
            horizontal=True,
        )

    if not assets:
        st.info("Select at least one asset.", icon=":material/touch_app:")
        return
    try:
        _render_results(
            panel, assets, period, ReturnType(return_type), vol_window, corr_window, method
        )
    except AnalyticsError as exc:
        st.error(f"The selection cannot be analyzed: {exc}", icon=":material/error:")


def _render_results(
    panel: PricePanel,
    assets: list[str],
    period: tuple[date, date],
    return_type: ReturnType,
    vol_window: int,
    corr_window: int,
    method: CorrelationMethod,
) -> None:
    selection = panel.select(assets=assets, start=period[0], end=period[1])
    returns = compute_returns(selection, return_type)
    summary = describe_assets(returns)
    quote = selection.context.quote_currency

    design.section(
        "Summary",
        f"{selection.start} to {selection.end} · {return_type.value} returns · annualized "
        f"with {summary.metadata.annualization_factor} calendar days · statistics need at least "
        f"{summary.metadata.min_observations} returns (otherwise shown as —).",
    )
    st.dataframe(
        summary_display(summary.table).style.format(
            {
                "Mean daily return": "{:+.3%}",
                "Median daily return": "{:+.3%}",
                "Min daily return": "{:+.2%}",
                "Max daily return": "{:+.2%}",
                "Daily volatility": "{:.2%}",
                "Annualized volatility": "{:.1%}",
                "Max drawdown": "{:.1%}",
            },
            na_rep="—",
        ),
        width="stretch",
        placeholder="—",
        alt="Per-asset summary: observations, missing days, return statistics, volatility "
        "and maximum drawdown.",
    )

    design.section("Charts", "Hover for exact values; each chart has a text summary.")
    price_tab, vol_tab, dd_tab, corr_tab = st.tabs(
        ["Price", "Volatility", "Drawdown", "Correlation"]
    )
    with price_tab:
        design.chart(
            analytics_charts.price_chart(selection.prices, quote_currency=quote),
            summary=f"Daily closing prices in {quote} on a log scale, {len(assets)} asset(s). "
            "Gaps are shown as breaks, never filled.",
            data=selection.prices,
            key="price",
        )
    with vol_tab:
        volatility = rolling_volatility(returns, window=vol_window)
        latest = volatility.values.ffill().iloc[-1].dropna()
        design.chart(
            analytics_charts.rolling_volatility_chart(volatility),
            summary=f"Annualized {vol_window}-day rolling volatility, labelled by the last day "
            "of each window."
            + (
                " Latest: " + ", ".join(f"{a} {v:.0%}" for a, v in latest.items()) + "."
                if len(latest)
                else ""
            ),
            data=volatility.values,
            key="volatility",
        )
    with dd_tab:
        deepest = summary.table["max_drawdown"].dropna()
        design.chart(
            analytics_charts.drawdown_chart(selection.prices),
            summary="Decline from the running peak of the close price."
            + (
                " Deepest: " + ", ".join(f"{a} {v:.0%}" for a, v in deepest.items()) + "."
                if len(deepest)
                else ""
            ),
            key="drawdown",
        )
    with corr_tab:
        if len(assets) < 2:
            st.info("Select at least two assets to compare correlations.", icon=":material/info:")
            return
        correlation = correlation_matrix(returns, method=method)
        st.caption(
            f"{method.value.capitalize()} correlation of daily returns; pairwise deletion; at "
            f"least {DEFAULT_MIN_OVERLAP} common returns per pair (otherwise n/a). Correlation "
            "describes co-movement, not causation."
        )
        design.chart(
            analytics_charts.correlation_heatmap(correlation),
            summary="Correlation matrix; cells show r, hover shows the number of common days.",
            data=correlation.matrix,
            key="correlation",
        )
        pair_cols = st.columns(2)
        pair_a = pair_cols[0].selectbox("Rolling correlation: first asset", assets, index=0)
        others = [asset for asset in assets if asset != pair_a]
        pair_b = pair_cols[1].selectbox("Second asset", others, index=0)
        rolling = rolling_correlation(returns, pair_a, pair_b, window=corr_window, method=method)
        design.chart(
            analytics_charts.rolling_correlation_chart(rolling),
            summary=f"{corr_window}-day rolling {method.value} correlation of {pair_a} and "
            f"{pair_b}; windows with gaps are undefined.",
            key="rolling-correlation",
        )
        with st.expander("Reproducibility metadata"):
            st.json(correlation.metadata.to_dict())
