"""Historical Analytics page: descriptive statistics on validated local datasets.

Rendered through the navigation in `app.py`. Works offline.
"""

from __future__ import annotations

import streamlit as st

from cryptovision.config import ConfigurationError, load_settings
from cryptovision.ui.analytics_view import render

try:
    settings = load_settings()
except ConfigurationError as exc:
    st.error(str(exc))
    st.stop()

render(settings.data_dir)
