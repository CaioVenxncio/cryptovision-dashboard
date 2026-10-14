"""CryptoVision Streamlit entry point.

Run with `streamlit run app.py`, or `cryptovision-demo` for the offline demo.
Pages live in `views/`; their logic lives in `cryptovision`. The visual
system is defined in `cryptovision.ui.theme` and `.streamlit/config.toml`.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from cryptovision.config import ConfigurationError, load_settings
from cryptovision.ui import design
from cryptovision.ui.theme import APP_NAME, PAGE_ICON

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(
    page_title=APP_NAME,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="auto",  # open on desktop, collapsed on small screens
)
design.apply_styles()
st.logo(str(ASSETS / "cryptovision-logo.svg"), icon_image=str(ASSETS / "cryptovision-mark.svg"))

try:
    demo_mode = load_settings().demo_mode
except ConfigurationError:
    demo_mode = False  # each page reports the configuration error itself

navigation = st.navigation(
    [
        st.Page(
            "views/market_explorer.py",
            title="Market Explorer",
            icon=":material/monitoring:",
            default=True,
        ),
        st.Page(
            "views/historical_analytics.py",
            title="Historical Analytics",
            icon=":material/insights:",
        ),
        st.Page("views/research_lab.py", title="Research Lab", icon=":material/science:"),
    ]
)
design.sidebar_identity("demo" if demo_mode else "live")
navigation.run()
