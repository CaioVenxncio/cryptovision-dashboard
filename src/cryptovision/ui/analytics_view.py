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
from cryptovision.analytics.volatility import (
    rolling_volatility,
)
from cryptovision.data.errors import DataPipelineError
from cryptovision.data.pipeline import list_datasets
from cryptovision.data.provenance import DatasetManifest
from cryptovision.formatting import format_utc
from cryptovision.ui import analytics_charts

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


def summary_display(table: pd.DataFrame) -> pd.DataFrame:
    columns = {
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
    return table.loc[:, list(columns)].rename(columns=columns)


def render_context(option: DatasetOption, panel: PricePanel) -> None:
    manifest = option.manifest
    context = panel.context
    if context.synthetic:
        st.warning(
            "Synthetic data: generated for testing and demonstration, not market observations."
        )
    elif context.provider == "binance_vision":
        st.info(
            f"Binance spot exchange prices in **{context.quote_currency}** (daily close, UTC). "
            "These are prices on one exchange, quoted in a stablecoin. They are not aggregated "
            "USD market prices."
        )
    st.caption(
        f"**Dataset:** {manifest.dataset_id} v{manifest.dataset_version} · "
        f"**Provider:** {context.provider} · **Quote:** {context.quote_currency} · "
        f"**Available period:** {manifest.actual_period.start} to {manifest.actual_period.end} · "
        f"**Content SHA-256:** `{(context.content_sha256 or '')[:12]}…` · "
        f"**Created:** {format_utc(manifest.created_at)}"
    )


def render(data_dir: Path) -> None:
    st.title("CryptoVision")
    st.markdown("#### Historical Analytics")
    st.caption(
        "Descriptive statistics of past returns. They describe history only; they are not "
        "forecasts, research findings or investment advice."
    )

    options = available_datasets(data_dir)
    if not options:
        st.info(
            f"No research-ready local dataset was found in `{data_dir}`. Build one with "
            "`cryptovision-data collect configs\\datasets\\binance-spot-1d-top10-20210103.toml "
            "--yes`, or create synthetic data with `cryptovision-data synthetic`."
        )
        return

    st.sidebar.header("Analytics settings")
    index = st.sidebar.selectbox(
        "Dataset", range(len(options)), format_func=lambda i: options[i].label
    )
    option = options[index]
    try:
        panel = _load_panel(str(option.path), option.manifest.content_sha256)
    except (AnalyticsError, DataPipelineError) as exc:
        st.error(f"The dataset could not be loaded safely: {exc}")
        return

    render_context(option, panel)

    assets = st.sidebar.multiselect("Assets", panel.assets, default=default_assets(panel.assets))
    period = st.sidebar.slider(
        "Period (UTC days)",
        min_value=panel.start,
        max_value=panel.end,
        value=(panel.start, panel.end),
        format="YYYY-MM-DD",
    )
    return_type = st.sidebar.radio(
        "Return type",
        [ReturnType.LOG, ReturnType.SIMPLE],
        format_func=lambda value: "Logarithmic" if value is ReturnType.LOG else "Simple",
        help="Log returns: ln(P_t / P_t-1). Simple returns: P_t / P_t-1 - 1.",
    )
    vol_window = st.sidebar.selectbox("Volatility window (days)", VOLATILITY_WINDOWS, index=1)
    corr_window = st.sidebar.selectbox("Correlation window (days)", CORRELATION_WINDOWS, index=1)
    method = st.sidebar.radio(
        "Correlation method",
        [CorrelationMethod.PEARSON, CorrelationMethod.SPEARMAN],
        format_func=lambda value: value.value.capitalize(),
    )

    if not assets:
        st.info("Select at least one asset.")
        return
    try:
        _render_results(
            panel, assets, period, ReturnType(return_type), vol_window, corr_window, method
        )
    except AnalyticsError as exc:
        st.error(f"The selection cannot be analyzed: {exc}")


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

    st.subheader("Summary")
    st.caption(
        f"{selection.start} to {selection.end} · {return_type.value} returns · annualization "
        f"factor {summary.metadata.annualization_factor} (calendar days) · statistics need at "
        f"least {summary.metadata.min_observations} returns"
    )
    st.dataframe(
        summary_display(summary.table).style.format(
            {
                "Mean daily return": "{:.3%}",
                "Median daily return": "{:.3%}",
                "Min daily return": "{:.2%}",
                "Max daily return": "{:.2%}",
                "Daily volatility": "{:.2%}",
                "Annualized volatility": "{:.1%}",
                "Max drawdown": "{:.1%}",
            },
            na_rep="—",
        ),
        width="stretch",
    )

    st.subheader(f"Close price ({quote})")
    st.plotly_chart(
        analytics_charts.price_chart(selection.prices, quote_currency=quote), width="stretch"
    )

    st.subheader("Rolling volatility")
    volatility = rolling_volatility(returns, window=vol_window)
    st.plotly_chart(analytics_charts.rolling_volatility_chart(volatility), width="stretch")

    st.subheader("Drawdown")
    st.plotly_chart(analytics_charts.drawdown_chart(selection.prices), width="stretch")

    st.subheader("Correlation of daily returns")
    if len(assets) < 2:
        st.info("Select at least two assets to compare correlations.")
        return
    correlation = correlation_matrix(returns, method=method)
    st.caption(
        f"{method.value.capitalize()} correlation, pairwise deletion, at least "
        f"{DEFAULT_MIN_OVERLAP} common returns per pair. Hover a cell for its sample size. "
        "Correlation describes co-movement, not causation."
    )
    st.plotly_chart(analytics_charts.correlation_heatmap(correlation), width="stretch")

    pair_a = st.selectbox("Rolling correlation: first asset", assets, index=0)
    others = [asset for asset in assets if asset != pair_a]
    pair_b = st.selectbox("Rolling correlation: second asset", others, index=0)
    rolling = rolling_correlation(returns, pair_a, pair_b, window=corr_window, method=method)
    st.plotly_chart(analytics_charts.rolling_correlation_chart(rolling), width="stretch")

    with st.expander("Reproducibility metadata"):
        st.json(correlation.metadata.to_dict())
