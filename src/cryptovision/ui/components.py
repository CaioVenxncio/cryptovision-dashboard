"""Reusable Streamlit components for the Market Explorer."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler

from cryptovision.config import Settings
from cryptovision.formatting import format_age, format_percent, format_usd, format_utc
from cryptovision.market import export_filename, summarize_selection, to_csv_bytes
from cryptovision.models import MarketSnapshot
from cryptovision.providers.coingecko import ATTRIBUTION_TEXT, ATTRIBUTION_URL
from cryptovision.ui import charts
from cryptovision.ui.market_data import (
    MIN_MANUAL_REFRESH_SECONDS,
    MarketLoadResult,
    clear_market_cache,
    refresh_allowed,
)
from cryptovision.ui.theme import change_color_css

MIN_ASSETS, MAX_ASSETS, DEFAULT_ASSETS = 5, 50, 10

TABLE_COLUMNS = [
    "image",
    "rank",
    "name",
    "symbol",
    "price",
    "change_24h_pct",
    "volume_24h",
    "market_cap",
]


def render_sidebar(settings: Settings, snapshot_age_seconds: float | None) -> int:
    """Render the settings sidebar and return the selected number of assets."""
    st.sidebar.header("Settings")
    asset_count = st.sidebar.slider(
        "Number of assets",
        min_value=MIN_ASSETS,
        max_value=MAX_ASSETS,
        value=DEFAULT_ASSETS,
        help="Top assets by market capitalization. Changing this does not call the API.",
    )
    if st.sidebar.button(
        "Refresh data",
        disabled=not refresh_allowed(snapshot_age_seconds),
        help=(
            f"Fetch new data now. Available once cached data is older than "
            f"{MIN_MANUAL_REFRESH_SECONDS} seconds. Each refresh uses one API credit."
        ),
    ):
        clear_market_cache()
        st.rerun()
    st.sidebar.caption(
        f"Data is cached for {settings.cache_ttl_seconds // 60} minutes to respect "
        "the CoinGecko Demo plan's monthly request budget."
    )
    return asset_count


def render_load_problem(result: MarketLoadResult) -> None:
    """Explain why no market data is available."""
    if result.missing_api_key:
        st.warning("No CoinGecko API key is configured.")
        st.markdown(
            "1. Create a free Demo API key at "
            "[coingecko.com/en/api](https://www.coingecko.com/en/api).\n"
            "2. Copy `.env.example` to `.env` in the project root.\n"
            "3. Set `COINGECKO_API_KEY=<your key>` in `.env` and restart the app."
        )
        return
    if result.error_message:
        st.error(result.error_message)
    if result.retry_in_seconds is not None:
        st.info(f"The app will try again in about {int(result.retry_in_seconds) + 1} seconds.")


def render_freshness(snapshot: MarketSnapshot, newly_fetched: bool, age_seconds: float) -> None:
    source = "Retrieved just now" if newly_fetched else f"Cached copy ({format_age(age_seconds)})"
    st.caption(
        f"**Provider data last updated:** {format_utc(snapshot.data_last_updated)} · "
        f"**Fetched at:** {format_utc(snapshot.fetched_at)} · {source}"
    )
    if snapshot.dropped_records:
        st.warning(
            f"{snapshot.dropped_records} record(s) from the provider were invalid and skipped."
        )


def render_summary(frame: pd.DataFrame) -> None:
    summary = summarize_selection(frame)
    scope = f"Computed over the {summary.asset_count} selected assets only, not the whole market."
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Selected Assets Market Cap",
        format_usd(summary.market_cap_total, compact=True),
        help=f"Sum of market capitalizations. {scope}",
    )
    col2.metric(
        "Selected Assets 24h Volume",
        format_usd(summary.volume_24h_total, compact=True),
        help=f"Sum of reported 24h trading volumes. {scope}",
    )
    col3.metric(
        "Selected Assets Market Cap Change (24h)",
        format_percent(summary.market_cap_change_24h_pct),
        help=(
            "Percentage change of the combined market cap of the selected assets over the "
            "last 24 hours. Reflects price and supply changes. " + scope
        ),
    )
    if summary.assets_missing_market_cap:
        st.caption(
            f"{summary.assets_missing_market_cap} selected asset(s) report no market cap "
            "and are excluded from the totals."
        )


def build_market_table(frame: pd.DataFrame) -> Styler:
    """Display formatting for the market table. Underlying values stay numeric."""
    return (
        frame[TABLE_COLUMNS]
        .style.format(
            {
                "price": format_usd,
                "change_24h_pct": format_percent,
                "volume_24h": lambda v: format_usd(v, compact=True),
                "market_cap": lambda v: format_usd(v, compact=True),
            }
        )
        .map(change_color_css, subset=["change_24h_pct"])
    )


def market_table_column_config() -> dict[str, object]:
    return {
        "image": st.column_config.ImageColumn("", width="small"),
        "rank": st.column_config.NumberColumn("Rank"),
        "name": "Name",
        "symbol": "Symbol",
        "price": st.column_config.NumberColumn("Price (USD)"),
        "change_24h_pct": st.column_config.NumberColumn("24h Change"),
        "volume_24h": st.column_config.NumberColumn("24h Volume (USD)"),
        "market_cap": st.column_config.NumberColumn("Market Cap (USD)"),
    }


def render_table(frame: pd.DataFrame) -> None:
    st.dataframe(
        build_market_table(frame),
        hide_index=True,
        width="stretch",
        column_config=market_table_column_config(),
    )


def render_charts(frame: pd.DataFrame) -> None:
    st.subheader("Market Capitalization")
    log_scale = st.checkbox(
        "Logarithmic scale", help="Makes smaller assets visible next to the largest ones."
    )
    st.plotly_chart(charts.market_cap_chart(frame, log_scale=log_scale), width="stretch")

    st.subheader("Price Change (24h)")
    st.plotly_chart(charts.price_change_chart(frame), width="stretch")


def render_export(frame: pd.DataFrame, snapshot: MarketSnapshot) -> None:
    st.subheader("Export")
    st.download_button(
        "Download CSV",
        data=to_csv_bytes(frame, snapshot),
        file_name=export_filename(snapshot),
        mime="text/csv",
        on_click="ignore",
        help="Raw numeric values for the selected assets, with source and fetch time (UTC).",
    )


def render_footer(settings: Settings) -> None:
    st.divider()
    st.caption(
        f"[{ATTRIBUTION_TEXT}]({ATTRIBUTION_URL}). "
        "CryptoVision is an educational research project, not investment advice. "
        "Prices are not real-time: the provider updates roughly every 60 seconds and this "
        f"app reuses fetched data for up to {settings.cache_ttl_seconds // 60} minutes."
    )
