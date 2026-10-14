"""CryptoVision Design System v1.0: design tokens, chart template and the one CSS layer.

Tokens are the single source of truth for colors. `.streamlit/config.toml`
repeats the same values for Streamlit's native theme (Streamlit cannot read
Python), and `tests/test_design_system.py` checks that both stay in sync and
that text colors meet WCAG 2.2 AA contrast on the canvas and surface.
See docs/design-system.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import plotly.graph_objects as go
import plotly.io as pio

APP_NAME = "CryptoVision"
PAGE_ICON = ":material/query_stats:"


@dataclass(frozen=True)
class Tokens:
    canvas: str = "#09090B"
    surface: str = "#111113"
    surface_raised: str = "#18181B"
    border: str = "#27272A"
    text: str = "#FAFAFA"
    text_muted: str = "#A1A1AA"
    accent: str = "#60A5FA"
    positive: str = "#34D399"
    warning: str = "#FBBF24"
    negative: str = "#F87171"


TOKENS = Tokens()

# Okabe-Ito based categorical palette, lightened where needed for a dark canvas.
# Distinguishable under the common forms of color-vision deficiency; series are
# also identified by legend labels and hover text, never by color alone.
SERIES_COLORS = (
    "#56B4E9",  # sky blue
    "#E69F00",  # orange
    "#2CB58E",  # bluish green
    "#F0E442",  # yellow
    "#CC79A7",  # reddish purple
    "#E8743B",  # vermillion
    "#7FA7E0",  # light blue
    "#B8B8C0",  # grey
    "#FAFAFA",  # white
)
# Diverging scale for correlations (-1 orange, 0 neutral, +1 blue): avoids red/green.
# Endpoints are dark enough for white cell labels (contrast >= 4.5:1).
DIVERGING_SCALE = ((0.0, "#9A5B00"), (0.5, "#27272A"), (1.0, "#1F6AA5"))

FONT_STACK = (
    "Geist, Inter, 'Segoe UI', system-ui, -apple-system, Roboto, 'Helvetica Neue', "
    "Arial, sans-serif"
)
MONO_STACK = "'Geist Mono', 'JetBrains Mono', 'Cascadia Mono', Consolas, ui-monospace, monospace"

CHART_HEIGHT = 420
UP_SYMBOL, DOWN_SYMBOL, FLAT_SYMBOL = "▲", "▼", "■"

# Back-compatible names used by earlier modules.
POSITIVE_COLOR = TOKENS.positive
NEGATIVE_COLOR = TOKENS.negative
ACCENT_COLOR = TOKENS.accent
NEUTRAL_LINE_COLOR = TOKENS.text_muted
CHANGE_DISPLAY_DECIMALS = 2


def change_color_css(value: float) -> str:
    """CSS for a percent change shown with two decimals; 0.00% is uncolored."""
    rounded = round(value, CHANGE_DISPLAY_DECIMALS)
    if rounded > 0:
        return f"color: {POSITIVE_COLOR}"
    if rounded < 0:
        return f"color: {NEGATIVE_COLOR}"
    return ""


# --- Contrast (WCAG 2.2) ------------------------------------------------------------


def _linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (relative_luminance(foreground), relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


# --- Plotly template ----------------------------------------------------------------


def _build_template() -> go.layout.Template:
    t = TOKENS
    axis = {
        "gridcolor": t.border,
        "linecolor": t.border,
        "zerolinecolor": t.border,
        "tickfont": {"color": t.text_muted, "size": 12},
        "title": {"font": {"color": t.text_muted, "size": 12}},
        "automargin": True,
    }
    return go.layout.Template(
        layout={
            "font": {"family": FONT_STACK, "color": t.text, "size": 13},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "colorway": list(SERIES_COLORS),
            "xaxis": axis,
            "yaxis": axis,
            "legend": {
                "font": {"color": t.text_muted, "size": 12},
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "x": 0,
                "bgcolor": "rgba(0,0,0,0)",
            },
            "hoverlabel": {
                "bgcolor": t.surface_raised,
                "bordercolor": t.border,
                "font": {"family": FONT_STACK, "color": t.text, "size": 12},
            },
            "margin": {"t": 40, "r": 16, "b": 16, "l": 16},
            "colorscale": {"diverging": [list(stop) for stop in DIVERGING_SCALE]},
        }
    )


TEMPLATE_NAME = "cryptovision"
pio.templates[TEMPLATE_NAME] = _build_template()
pio.templates.default = TEMPLATE_NAME

PLOTLY_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


# --- CSS layer ----------------------------------------------------------------------

# The only CSS in the app. It styles CryptoVision's own classes (cv-*) and a few
# documented Streamlit test ids. Streamlit's theme (config.toml) does the rest.
CSS = f"""
<style>
:root {{ font-variant-numeric: tabular-nums; }}
[data-testid="stMainBlockContainer"] {{ max-width: 1360px; padding-top: 2.25rem;
  padding-bottom: 4rem; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMetricLabel"] p {{ font-size: 0.75rem; color: {TOKENS.text_muted};
  text-transform: uppercase; letter-spacing: 0.04em; }}
[data-testid="stMetricValue"], [data-testid="stDataFrame"] {{ font-variant-numeric: tabular-nums; }}
:focus-visible {{ outline: 2px solid {TOKENS.accent} !important; outline-offset: 2px; }}
h1, h2, h3 {{ letter-spacing: -0.015em; }}
.cv-eyebrow {{ font-family: {MONO_STACK}; font-size: 0.75rem; letter-spacing: 0.08em;
  text-transform: uppercase; color: {TOKENS.text_muted}; margin: 0 0 0.35rem 0; }}
.cv-title {{ font-size: 1.875rem; font-weight: 600; letter-spacing: -0.02em; margin: 0;
  color: {TOKENS.text}; line-height: 1.2; }}
.cv-lead {{ color: {TOKENS.text_muted}; font-size: 0.9375rem; margin: 0.4rem 0 0.9rem 0;
  max-width: 72ch; line-height: 1.5; }}
.cv-meta {{ display: flex; flex-wrap: wrap; gap: 0.35rem 1.25rem; font-family: {MONO_STACK};
  font-size: 0.75rem; color: {TOKENS.text_muted}; padding: 0.6rem 0;
  border-top: 1px solid {TOKENS.border}; border-bottom: 1px solid {TOKENS.border}; }}
.cv-meta b {{ color: {TOKENS.text}; font-weight: 500; }}
.cv-section {{ margin: 2rem 0 0.25rem 0; }}
.cv-section h2 {{ font-size: 1.125rem; font-weight: 600; margin: 0; color: {TOKENS.text}; }}
.cv-section p {{ color: {TOKENS.text_muted}; font-size: 0.8125rem; margin: 0.25rem 0 0 0;
  max-width: 80ch; }}
.cv-tag {{ display: inline-block; font-family: {MONO_STACK}; font-size: 0.6875rem;
  letter-spacing: 0.06em; text-transform: uppercase; padding: 0.1rem 0.45rem;
  border: 1px solid {TOKENS.border}; border-radius: 4px; color: {TOKENS.text_muted}; }}
.cv-tag.cv-warn {{ color: {TOKENS.warning}; border-color: {TOKENS.warning}; }}
.cv-tag.cv-live {{ color: {TOKENS.positive}; border-color: {TOKENS.positive}; }}
.cv-sidenote {{ color: {TOKENS.text_muted}; font-size: 0.75rem; line-height: 1.45;
  margin: 0.5rem 0 0 0; }}
.cv-brand {{ font-weight: 600; font-size: 1rem; letter-spacing: -0.01em; color: {TOKENS.text}; }}
.cv-brand span {{ color: {TOKENS.text_muted}; font-weight: 400; }}
</style>
"""
