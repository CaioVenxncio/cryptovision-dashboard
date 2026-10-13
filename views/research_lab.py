"""Research Lab page: verified results of the pre-specified study (read-only, offline)."""

from __future__ import annotations

import streamlit as st

from cryptovision.config import ConfigurationError, load_settings
from cryptovision.ui.research_view import render

try:
    settings = load_settings()
except ConfigurationError as exc:
    st.error(str(exc))
    st.stop()

render(settings.results_dir)
