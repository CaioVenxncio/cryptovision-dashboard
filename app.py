"""CryptoVision Streamlit entry point.

Run with `streamlit run app.py`. Configuration is read from `.env`; see
`.env.example`. Pages live in `views/`; their logic lives in `cryptovision`.
"""

from __future__ import annotations

import streamlit as st

from cryptovision.ui.theme import APP_NAME, PAGE_ICON

st.set_page_config(
    page_title=APP_NAME,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

navigation = st.navigation(
    [
        st.Page("views/market_explorer.py", title="Market Explorer", icon="📊", default=True),
        st.Page("views/historical_analytics.py", title="Historical Analytics", icon="📈"),
    ]
)
navigation.run()
