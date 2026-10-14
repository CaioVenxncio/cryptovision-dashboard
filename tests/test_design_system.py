"""Design tokens: WCAG contrast, sync with the Streamlit theme, safe HTML components."""

from __future__ import annotations

import tomllib
from pathlib import Path

import plotly.io as pio
import pytest

from cryptovision.ui import design
from cryptovision.ui.theme import (
    DIVERGING_SCALE,
    SERIES_COLORS,
    TEMPLATE_NAME,
    TOKENS,
    contrast_ratio,
    relative_luminance,
)

CONFIG = tomllib.loads(
    (Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text("utf-8")
)
TEXT_TOKENS = ("text", "text_muted", "accent", "positive", "warning", "negative")
BACKGROUNDS = ("canvas", "surface", "surface_raised")


def test_contrast_formula_reference_values():
    # WCAG reference points: black on white is 21:1, identical colors 1:1.
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)
    assert relative_luminance("#FFFFFF") == pytest.approx(1.0)


@pytest.mark.parametrize("foreground", TEXT_TOKENS)
@pytest.mark.parametrize("background", BACKGROUNDS)
def test_text_tokens_meet_wcag_aa(foreground, background):
    ratio = contrast_ratio(getattr(TOKENS, foreground), getattr(TOKENS, background))
    assert ratio >= 4.5, f"{foreground} on {background}: {ratio:.2f}"


@pytest.mark.parametrize("color", SERIES_COLORS)
def test_chart_series_colors_are_visible_on_canvas(color):
    # WCAG 1.4.11 non-text contrast: graphical objects >= 3:1 against adjacent colors.
    assert contrast_ratio(color, TOKENS.canvas) >= 3.0


def test_series_palette_has_distinct_colors():
    assert len(set(SERIES_COLORS)) == len(SERIES_COLORS)


@pytest.mark.parametrize("stop", [DIVERGING_SCALE[0][1], DIVERGING_SCALE[-1][1]])
def test_heatmap_endpoints_keep_white_labels_readable(stop):
    assert contrast_ratio(TOKENS.text, stop) >= 4.5


def test_streamlit_theme_matches_tokens():
    theme = CONFIG["theme"]
    assert theme["base"] == "dark"
    assert theme["backgroundColor"] == TOKENS.canvas
    assert theme["secondaryBackgroundColor"] == TOKENS.surface
    assert theme["textColor"] == TOKENS.text
    assert theme["primaryColor"] == TOKENS.accent
    assert theme["borderColor"] == TOKENS.border
    assert theme["greenColor"] == TOKENS.positive
    assert theme["redColor"] == TOKENS.negative
    assert theme["yellowColor"] == TOKENS.warning
    assert theme["chartCategoricalColors"] == list(SERIES_COLORS)
    assert CONFIG["client"]["toolbarMode"] == "minimal"
    assert CONFIG["browser"]["gatherUsageStats"] is False


def test_plotly_template_is_registered_and_default():
    assert pio.templates.default == TEMPLATE_NAME
    layout = pio.templates[TEMPLATE_NAME].layout
    assert list(layout.colorway) == list(SERIES_COLORS)
    assert layout.paper_bgcolor == "rgba(0,0,0,0)"


def test_components_escape_dynamic_text(monkeypatch):
    rendered: list[str] = []
    monkeypatch.setattr(design.st, "markdown", lambda body, **_: rendered.append(body))

    design.page_header(
        "<eyebrow>", "<script>alert(1)</script>", "lead & more",
        meta=[("Key", "<b>value</b>")], tags=[("tag<x>", "warn")],
    )  # fmt: skip
    design.section("<h1>title</h1>", "desc <i>")

    html = "".join(rendered)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "&lt;b&gt;value&lt;/b&gt;" in html
    assert "tag&lt;x&gt;" in html
    assert "&lt;h1&gt;title&lt;/h1&gt;" in html
    assert 'class="cv-tag cv-warn"' in html
