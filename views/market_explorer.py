"""Market Explorer page: current market data from CoinGecko.

Rendered through the navigation in `app.py`. Logic lives in `cryptovision`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from cryptovision.config import ConfigurationError, load_settings
from cryptovision.market import select_top, snapshot_to_frame
from cryptovision.ui import components
from cryptovision.ui.market_data import load_market_snapshot, snapshot_age_seconds
from cryptovision.ui.theme import APP_NAME

try:
    settings = load_settings()
except ConfigurationError as exc:
    st.error(str(exc))
    st.stop()

st.title(APP_NAME)
st.markdown("#### Market Explorer")

with st.spinner("Loading market data from CoinGecko..."):
    result = load_market_snapshot(settings, st.session_state)

snapshot = result.snapshot
age_seconds = snapshot_age_seconds(snapshot, datetime.now(UTC)) if snapshot else None
asset_count = components.render_sidebar(settings, age_seconds)

if snapshot is None:
    components.render_load_problem(result)
else:
    full_frame = snapshot_to_frame(snapshot)
    if full_frame.empty:
        st.info("The provider returned no market data.")
    else:
        frame = select_top(full_frame, asset_count)
        components.render_freshness(snapshot, result.newly_fetched, age_seconds or 0.0)
        components.render_summary(frame)
        st.subheader(f"Top {len(frame)} Assets by Market Cap")
        components.render_table(frame)
        components.render_charts(frame)
        components.render_export(frame, snapshot)

components.render_footer(settings)
