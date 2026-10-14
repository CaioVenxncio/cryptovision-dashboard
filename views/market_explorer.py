"""Market Explorer page: current market overview (CoinGecko, or a synthetic demo snapshot).

Rendered through the navigation in `app.py`. Logic lives in `cryptovision`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from cryptovision.config import ConfigurationError, load_settings
from cryptovision.demo import demo_market_snapshot
from cryptovision.market import select_top, snapshot_to_frame
from cryptovision.ui import components, design
from cryptovision.ui.market_data import (
    MarketLoadResult,
    load_market_snapshot,
    snapshot_age_seconds,
)

try:
    settings = load_settings()
except ConfigurationError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

demo = settings.demo_mode
if demo:
    # Offline demo: generated data, no network request.
    result = MarketLoadResult(snapshot=demo_market_snapshot(), newly_fetched=False)
else:
    with st.spinner("Loading market data from CoinGecko..."):
        result = load_market_snapshot(settings, st.session_state)

snapshot = result.snapshot
age_seconds = snapshot_age_seconds(snapshot, datetime.now(UTC)) if snapshot else None

design.page_header(
    "Markets",
    "Market Explorer",
    "The largest crypto assets by market capitalization. Snapshots refreshed at most every "
    "15 minutes; not real-time quotes.",
    meta=(
        components.freshness_meta(snapshot, result.newly_fetched, age_seconds or 0.0, demo=demo)
        if snapshot
        else [("Source", "CoinGecko Demo API"), ("Status", "unavailable")]
    ),
    tags=[("Demo · synthetic", "warn")] if demo else [("Live", "live")],
)
if demo:
    design.demo_notice("This snapshot of 40 assets is generated, not fetched from CoinGecko.")

asset_count = components.render_toolbar(age_seconds, demo=demo)

if snapshot is None:
    components.render_load_problem(result)
else:
    full_frame = snapshot_to_frame(snapshot)
    if full_frame.empty:
        st.info("The provider returned no market data.", icon=":material/info:")
    else:
        if snapshot.dropped_records:
            st.warning(
                f"{snapshot.dropped_records} record(s) from the provider were invalid and skipped.",
                icon=":material/warning:",
            )
        frame = select_top(full_frame, asset_count)
        components.render_summary(frame)
        design.section(
            f"Top {len(frame)} assets",
            "Sortable by any column. Values stay numeric; formatting is display-only.",
        )
        components.render_table(frame)
        components.render_export(frame, snapshot)
        design.section("Market structure", "Capitalization and 24-hour price change per asset.")
        components.render_charts(frame)

components.render_footer(settings, demo=demo)
