"""Quantitative analytics for validated historical datasets.

Pure calculations: no Streamlit, no network access, no file writes. Real data
enters only through `cryptovision.analytics.data.load_price_panel`, which uses
the Phase 3 loader and therefore its integrity, readiness and expiry checks.
See docs/analytics-methodology.md for definitions and policies.
"""
