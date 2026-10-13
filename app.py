"""CryptoVision Streamlit entry point: Market Explorer.

Run with `streamlit run app.py`. Configuration is read from `.env`; see
`.env.example`.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import plotly.express as px
import streamlit as st

from cryptovision.config import ConfigurationError, load_settings
from cryptovision.formatting import format_age, format_percent, format_usd, format_utc
from cryptovision.market import (
    export_filename,
    select_top,
    snapshot_to_frame,
    summarize_selection,
    to_csv_bytes,
)
from cryptovision.models import MarketSnapshot
from cryptovision.providers.coingecko import (
    ATTRIBUTION_TEXT,
    ATTRIBUTION_URL,
    CoinGeckoClient,
)
from cryptovision.providers.errors import MissingApiKeyError, ProviderError, RateLimitError

VS_CURRENCY = "usd"
# One request returns enough assets for every slider position, so moving the
# slider never triggers a new API call.
MARKET_FETCH_SIZE = 100
MIN_ASSETS, MAX_ASSETS, DEFAULT_ASSETS = 5, 50, 10
# CoinGecko Demo data updates about every 60 s; refreshing faster wastes credits.
MIN_MANUAL_REFRESH_SECONDS = 60
# After a failed request, wait before contacting the provider again.
FAILURE_COOLDOWN_SECONDS = 60

POSITIVE_COLOR = "#1a7f37"
NEGATIVE_COLOR = "#cf222e"
ACCENT_COLOR = "#6200EE"

st.set_page_config(
    page_title="CryptoVision · Market Explorer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    settings = load_settings()
except ConfigurationError as exc:
    st.error(str(exc))
    st.stop()


@st.cache_data(ttl=settings.cache_ttl_seconds, max_entries=4, show_spinner=False)
def fetch_market_snapshot(vs_currency: str, per_page: int) -> MarketSnapshot:
    """Fetch market data once per cache TTL. Failures are not cached."""
    client = CoinGeckoClient.from_settings(settings)
    return client.get_markets(vs_currency, per_page=per_page)


def load_snapshot() -> tuple[MarketSnapshot | None, bool]:
    """Return the snapshot and whether it was newly retrieved during this run."""
    last_failure = st.session_state.get("last_failure")
    if last_failure is not None:
        failed_at, message, cooldown = last_failure
        remaining = cooldown - (time.monotonic() - failed_at)
        if remaining > 0:
            st.error(message)
            st.info(f"The app will try again in about {int(remaining) + 1} seconds.")
            return None, False
        del st.session_state["last_failure"]

    started_at = datetime.now(UTC)
    try:
        with st.spinner("Loading market data from CoinGecko..."):
            snapshot = fetch_market_snapshot(VS_CURRENCY, MARKET_FETCH_SIZE)
    except MissingApiKeyError:
        st.warning("No CoinGecko API key is configured.")
        st.markdown(
            "1. Create a free Demo API key at "
            "[coingecko.com/en/api](https://www.coingecko.com/en/api).\n"
            "2. Copy `.env.example` to `.env` in the project root.\n"
            "3. Set `COINGECKO_API_KEY=<your key>` in `.env` and restart the app."
        )
        return None, False
    except ProviderError as exc:
        cooldown = FAILURE_COOLDOWN_SECONDS
        if isinstance(exc, RateLimitError) and exc.retry_after_seconds:
            cooldown = max(cooldown, exc.retry_after_seconds)
        message = f"Market data is unavailable: {exc}"
        st.session_state["last_failure"] = (time.monotonic(), message, cooldown)
        st.error(message)
        return None, False
    return snapshot, snapshot.fetched_at >= started_at


def render_sidebar(snapshot_age_seconds: float | None) -> int:
    st.sidebar.header("Settings")
    asset_count = st.sidebar.slider(
        "Number of assets",
        min_value=MIN_ASSETS,
        max_value=MAX_ASSETS,
        value=DEFAULT_ASSETS,
        help="Top assets by market capitalization. Changing this does not call the API.",
    )
    can_refresh = snapshot_age_seconds is None or snapshot_age_seconds >= MIN_MANUAL_REFRESH_SECONDS
    if st.sidebar.button(
        "Refresh data",
        disabled=not can_refresh,
        help=(
            f"Fetch new data now. Available once cached data is older than "
            f"{MIN_MANUAL_REFRESH_SECONDS} seconds. Each refresh uses one API credit."
        ),
    ):
        fetch_market_snapshot.clear()
        st.rerun()
    st.sidebar.caption(
        f"Data is cached for {settings.cache_ttl_seconds // 60} minutes to respect "
        "the CoinGecko Demo plan's monthly request budget."
    )
    return asset_count


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


def render_summary(frame) -> None:
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


def render_table(frame) -> None:
    columns = [
        "image",
        "rank",
        "name",
        "symbol",
        "price",
        "change_24h_pct",
        "volume_24h",
        "market_cap",
    ]
    styled = (
        frame[columns]
        .style.format(
            {
                "price": format_usd,
                "change_24h_pct": format_percent,
                "volume_24h": lambda v: format_usd(v, compact=True),
                "market_cap": lambda v: format_usd(v, compact=True),
            }
        )
        .map(
            lambda v: (
                f"color: {POSITIVE_COLOR}" if v > 0 else f"color: {NEGATIVE_COLOR}" if v < 0 else ""
            ),
            subset=["change_24h_pct"],
        )
    )
    st.dataframe(
        styled,
        hide_index=True,
        width="stretch",
        column_config={
            "image": st.column_config.ImageColumn("", width="small"),
            "rank": st.column_config.NumberColumn("Rank"),
            "name": "Name",
            "symbol": "Symbol",
            "price": st.column_config.NumberColumn("Price (USD)"),
            "change_24h_pct": st.column_config.NumberColumn("24h Change"),
            "volume_24h": st.column_config.NumberColumn("24h Volume (USD)"),
            "market_cap": st.column_config.NumberColumn("Market Cap (USD)"),
        },
    )


def render_charts(frame) -> None:
    st.subheader("Market Capitalization")
    log_scale = st.checkbox(
        "Logarithmic scale", help="Makes smaller assets visible next to the largest ones."
    )
    chart_data = frame.assign(
        market_cap_label=frame["market_cap"].map(lambda v: format_usd(v, compact=True)),
        change_label=frame["change_24h_pct"].map(format_percent),
    )
    fig_cap = px.bar(
        chart_data,
        x="name",
        y="market_cap",
        custom_data=["market_cap_label"],
        log_y=log_scale,
        color_discrete_sequence=[ACCENT_COLOR],
    )
    fig_cap.update_traces(hovertemplate="%{x}<br>Market cap: %{customdata[0]}<extra></extra>")
    fig_cap.update_layout(
        xaxis_title=None,
        yaxis_title="Market cap (USD)",
        yaxis_tickprefix="$",
        yaxis_exponentformat="B",
        height=450,
    )
    st.plotly_chart(fig_cap, width="stretch")

    st.subheader("Price Change (24h)")
    chart_data = chart_data.sort_values("change_24h_pct").assign(
        direction=lambda df: df["change_24h_pct"].map(lambda v: "Up" if v >= 0 else "Down")
    )
    fig_change = px.bar(
        chart_data,
        x="name",
        y="change_24h_pct",
        color="direction",
        custom_data=["change_label"],
        color_discrete_map={"Up": POSITIVE_COLOR, "Down": NEGATIVE_COLOR},
    )
    fig_change.update_traces(hovertemplate="%{x}<br>24h change: %{customdata[0]}<extra></extra>")
    fig_change.update_layout(
        xaxis_title=None,
        yaxis_title="24h price change (%)",
        yaxis_ticksuffix="%",
        showlegend=False,
        height=450,
    )
    fig_change.add_hline(y=0, line_width=1, line_color="#888888")
    st.plotly_chart(fig_change, width="stretch")


def render_export(frame, snapshot: MarketSnapshot) -> None:
    st.subheader("Export")
    st.download_button(
        "Download CSV",
        data=to_csv_bytes(frame, snapshot),
        file_name=export_filename(snapshot),
        mime="text/csv",
        on_click="ignore",
        help="Raw numeric values for the selected assets, with source and fetch time (UTC).",
    )


def render_footer() -> None:
    st.divider()
    st.caption(
        f"[{ATTRIBUTION_TEXT}]({ATTRIBUTION_URL}). "
        "CryptoVision is an educational research project, not investment advice. "
        "Prices are not real-time: the provider updates roughly every 60 seconds and this "
        f"app reuses fetched data for up to {settings.cache_ttl_seconds // 60} minutes."
    )


st.title("CryptoVision")
st.markdown("#### Market Explorer")

snapshot, newly_fetched = load_snapshot()
age_seconds = (
    (datetime.now(UTC) - snapshot.fetched_at).total_seconds() if snapshot is not None else None
)
asset_count = render_sidebar(age_seconds)

if snapshot is not None:
    full_frame = snapshot_to_frame(snapshot)
    if full_frame.empty:
        st.info("The provider returned no market data.")
    else:
        frame = select_top(full_frame, asset_count)
        render_freshness(snapshot, newly_fetched, age_seconds or 0.0)
        render_summary(frame)
        st.subheader(f"Top {len(frame)} Assets by Market Cap")
        render_table(frame)
        render_charts(frame)
        render_export(frame, snapshot)

render_footer()
