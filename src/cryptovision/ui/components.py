"""Market Explorer components."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler

from cryptovision.config import Settings
from cryptovision.formatting import format_age, format_percent, format_usd, format_utc
from cryptovision.market import export_filename, summarize_selection, to_csv_bytes
from cryptovision.models import MarketSnapshot
from cryptovision.providers.coingecko import ATTRIBUTION_TEXT, ATTRIBUTION_URL
from cryptovision.ui import charts, design
from cryptovision.ui.market_data import (
    MIN_MANUAL_REFRESH_SECONDS,
    MarketLoadResult,
    clear_market_cache,
    refresh_allowed,
)
from cryptovision.ui.theme import change_color_css

ASSET_COUNTS = (10, 25, 50)
DEFAULT_ASSETS = 10

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


def format_change(value: float) -> str:
    """'▲ +1.23%' / '▼ -0.50%' / '■ 0.00%': direction readable without color."""
    if value is None or value != value:  # NaN
        return format_percent(value)
    return f"{charts.direction_symbol(value)} {format_percent(value)}"


def render_toolbar(snapshot_age_seconds: float | None, *, demo: bool) -> int:
    """Asset count selector and refresh action. Returns the number of assets."""
    left, right = st.columns([3, 1], vertical_alignment="bottom")
    with left:
        count = st.radio(
            "Assets shown",
            ASSET_COUNTS,
            index=ASSET_COUNTS.index(DEFAULT_ASSETS),
            horizontal=True,
            help="Largest assets by market capitalization. Changing this does not call the API.",
        )
    with right:
        if not demo and st.button(
            "Refresh data",
            icon=":material/refresh:",
            disabled=not refresh_allowed(snapshot_age_seconds),
            help=(
                f"Fetch new data now. Available once cached data is older than "
                f"{MIN_MANUAL_REFRESH_SECONDS} seconds. Each refresh uses one API credit."
            ),
            width="stretch",
        ):
            clear_market_cache()
            st.rerun()
    return int(count)


def render_load_problem(result: MarketLoadResult) -> None:
    """Explain why no market data is available, and how to continue."""
    if result.missing_api_key:
        st.warning(
            "**No CoinGecko API key is configured.** Live market data needs a free Demo key.",
            icon=":material/key:",
        )
        st.markdown(
            "1. Create a free Demo API key at "
            "[coingecko.com/en/api](https://www.coingecko.com/en/api).\n"
            "2. Copy `.env.example` to `.env` in the project root.\n"
            "3. Set `COINGECKO_API_KEY=<your key>` in `.env` and restart the app.\n\n"
            "To explore without a key, start the offline demo with `cryptovision-demo`."
        )
        return
    if result.error_message:
        st.error(result.error_message, icon=":material/cloud_off:")
    if result.retry_in_seconds is not None:
        st.info(
            f"The app will try again in about {int(result.retry_in_seconds) + 1} seconds. "
            "Historical Analytics and the Research Lab work offline in the meantime.",
            icon=":material/schedule:",
        )


def freshness_meta(
    snapshot: MarketSnapshot, newly_fetched: bool, age_seconds: float, *, demo: bool
) -> list[tuple[str, str]]:
    if demo:
        return [
            ("Source", "synthetic demo snapshot"),
            ("Generated", format_utc(snapshot.fetched_at)),
            ("Assets", str(len(snapshot.coins))),
        ]
    return [
        ("Source", "CoinGecko Demo API"),
        ("Provider update", format_utc(snapshot.data_last_updated)),
        ("Fetched", format_utc(snapshot.fetched_at)),
        (
            "Cache",
            "retrieved just now" if newly_fetched else f"cached copy, {format_age(age_seconds)}",
        ),
    ]


def render_summary(frame: pd.DataFrame) -> None:
    summary = summarize_selection(frame)
    scope = f"Computed over the {summary.asset_count} assets shown, not the whole market."
    change = summary.market_cap_change_24h_pct
    cols = st.columns(4)
    cols[0].metric(
        "Market cap · selected",
        format_usd(summary.market_cap_total, compact=True),
        help=f"Sum of market capitalizations in USD. {scope}",
    )
    cols[1].metric(
        "24h volume · selected",
        format_usd(summary.volume_24h_total, compact=True),
        help=f"Sum of reported 24h trading volumes in USD. {scope}",
    )
    cols[2].metric(
        "Market cap change · 24h",
        format_change(change) if change is not None else "—",
        help=(
            "Percentage change of the combined market cap of the assets shown over the last "
            "24 hours; reflects price and supply changes. " + scope
        ),
    )
    cols[3].metric(
        "Assets shown",
        str(summary.asset_count),
        help="Assets without a reported market cap are excluded from the totals.",
    )
    if summary.assets_missing_market_cap:
        st.caption(
            f"{summary.assets_missing_market_cap} asset(s) report no market cap and are "
            "excluded from the totals."
        )


def build_market_table(frame: pd.DataFrame, columns: list[str] | None = None) -> Styler:
    """Display formatting only; the underlying values stay numeric and sortable."""
    return (
        frame[columns or TABLE_COLUMNS]
        .style.format(
            {
                "price": format_usd,
                "change_24h_pct": format_change,
                "volume_24h": lambda v: format_usd(v, compact=True),
                "market_cap": lambda v: format_usd(v, compact=True),
            }
        )
        .map(change_color_css, subset=["change_24h_pct"])
    )


def market_table_column_config() -> dict[str, object]:
    return {
        "image": st.column_config.ImageColumn("", width="small"),
        "rank": st.column_config.NumberColumn("#", width="small"),
        "name": st.column_config.TextColumn("Asset"),
        "symbol": st.column_config.TextColumn("Symbol", width="small"),
        "price": st.column_config.NumberColumn("Price (USD)"),
        "change_24h_pct": st.column_config.NumberColumn("24h change"),
        "volume_24h": st.column_config.NumberColumn("24h volume (USD)"),
        "market_cap": st.column_config.NumberColumn("Market cap (USD)"),
    }


ROW_HEIGHT = 34


def render_table(frame: pd.DataFrame) -> None:
    columns = list(TABLE_COLUMNS)
    if frame["image"].isna().all():
        columns.remove("image")  # e.g. the synthetic demo has no logos
    st.dataframe(
        build_market_table(frame, columns),
        hide_index=True,
        width="stretch",
        placeholder="—",
        row_height=ROW_HEIGHT,
        height=min(ROW_HEIGHT * (len(frame) + 1) + 2, 620),
        column_config={k: v for k, v in market_table_column_config().items() if k in columns},
        alt=f"Table of the top {len(frame)} assets by market capitalization with price, "
        "24-hour change, 24-hour volume and market capitalization in USD.",
    )


def render_charts(frame: pd.DataFrame) -> None:
    cap_tab, change_tab = st.tabs(["Market capitalization", "24h price change"])
    with cap_tab:
        log_scale = st.toggle(
            "Logarithmic scale", help="Makes smaller assets visible next to the largest ones."
        )
        largest = frame.nlargest(1, "market_cap")
        design.chart(
            charts.market_cap_chart(frame, log_scale=log_scale),
            summary=(
                f"Horizontal bars, one per asset, sorted by market capitalization. "
                f"Largest: {largest['name'].iloc[0]} "
                f"({format_usd(largest['market_cap'].iloc[0], compact=True)})."
                if len(largest)
                else "No market capitalization reported."
            ),
            key="market-cap-chart",
        )
    with change_tab:
        missing = frame["change_24h_pct"].isna().sum()
        up = int((frame["change_24h_pct"].round(2) > 0).sum())
        down = int((frame["change_24h_pct"].round(2) < 0).sum())
        design.chart(
            charts.price_change_chart(frame),
            summary=(
                f"{up} assets up ▲, {down} down ▼ over 24 hours."
                + (f" {missing} without a reported change are omitted." if missing else "")
            ),
            key="price-change-chart",
        )


def render_export(frame: pd.DataFrame, snapshot: MarketSnapshot) -> None:
    st.download_button(
        "Download CSV",
        data=to_csv_bytes(frame, snapshot),
        file_name=export_filename(snapshot),
        mime="text/csv",
        icon=":material/download:",
        on_click="ignore",
        help="Raw numeric values for the assets shown, with source and fetch time (UTC).",
    )


def render_footer(settings: Settings, *, demo: bool) -> None:
    st.divider()
    if demo:
        st.caption(
            "Demo mode: every value on this page is synthetic. CryptoVision is an educational "
            "research project, not investment advice."
        )
        return
    st.caption(
        f"[{ATTRIBUTION_TEXT}]({ATTRIBUTION_URL}). "
        "CryptoVision is an educational research project, not investment advice. "
        "Prices are not real-time: the provider updates roughly every 60 seconds and this "
        f"app reuses fetched data for up to {settings.cache_ttl_seconds // 60} minutes."
    )
