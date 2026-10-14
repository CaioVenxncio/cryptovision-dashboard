"""CryptoVision Streamlit entry point.

Run with `streamlit run app.py`, or `cryptovision-demo` for the offline demo.
Pages live in `views/`; their logic lives in `cryptovision`. The visual
system is defined in `cryptovision.ui.theme` and `.streamlit/config.toml`.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from cryptovision import config
from cryptovision.config import ConfigurationError, load_settings
from cryptovision.demo import prepare_demo, uses_default_demo_data
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


@st.cache_resource(
    show_spinner="Preparing the synthetic demo data (first start only, under a minute)..."
)
def _prepare_demo_data(root: str) -> None:
    """Build the demo dataset and research bundle once per server process (idempotent)."""
    prepare_demo(Path(root), progress=lambda _: None)


try:
    settings = load_settings()
except ConfigurationError:
    settings = None  # each page reports the configuration error itself
demo_mode = settings is not None and settings.demo_mode

# Demo mode set only through the environment (e.g. CRYPTOVISION_DEMO in Streamlit
# secrets on a hosted app) has no `cryptovision-demo` launcher to build its data.
if settings is not None and uses_default_demo_data(settings):
    try:
        _prepare_demo_data(str(config.DEMO_ROOT))
    except Exception as exc:  # noqa: BLE001 - shown to the user; pages report missing data
        st.error(
            f"The synthetic demo data could not be prepared: {exc}. The Market Explorer "
            "demo still works; Historical Analytics and the Research Lab need this data.",
            icon=":material/error:",
        )

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
