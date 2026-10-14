# CryptoVision Design System v1.0

The design system is deliberately small. It has one set of tokens, one Plotly template, one CSS block and a few page-level components. Everything else is native Streamlit.

| File | Role |
|---|---|
| `src/cryptovision/ui/theme.py` | Tokens, chart palettes, contrast helper, Plotly template, the global CSS block |
| `src/cryptovision/ui/design.py` | Page-level components (header, section, chart wrapper, sidebar identity, demo notice) |
| `.streamlit/config.toml` | Streamlit's native theme. It repeats the token values because Streamlit cannot read Python. |
| `assets/cryptovision-mark.svg`, `assets/cryptovision-logo.svg` | Original line-chart mark and logo, used by `st.logo` |
| `tests/test_design_system.py` | Keeps the TOML theme in sync with the tokens and checks contrast |

## Principles

1. **Data first.** Numbers, tables and charts carry the page. Decoration is limited to type, spacing and thin borders.
2. **Honest labelling.** Synthetic data, failed validation gates and unvalidated intervals are stated in words next to the values they affect, not only through color.
3. **One source of truth.** Colors are defined once in `Tokens`. Charts get them from the Plotly template; Streamlit widgets get them from the TOML theme.
4. **Accessible by default.** Text meets WCAG 2.2 AA contrast. Every chart has a text summary and a data table.

## Color tokens

Dark theme only. Contrast ratios are computed with the WCAG 2.2 formula (`contrast_ratio` in `theme.py`).

| Token | Value | Use | Contrast on canvas / surface / raised |
|---|---|---|---|
| `canvas` | `#09090B` | Page background | — |
| `surface` | `#111113` | Sidebar, inputs, table header | — |
| `surface_raised` | `#18181B` | Raised panels | — |
| `border` | `#27272A` | Borders, grid lines | — |
| `text` | `#FAFAFA` | Body text | 19.1 / 18.1 / 17.0 |
| `text_muted` | `#A1A1AA` | Captions, metadata | 7.8 / 7.4 / 6.9 |
| `accent` | `#60A5FA` | Primary actions, focus ring, links | 7.8 / 7.4 / 7.0 |
| `positive` | `#34D399` | Increases | 10.3 / 9.8 / 9.2 |
| `warning` | `#FBBF24` | Synthetic-data and caution tags | 11.9 / 11.3 / 10.6 |
| `negative` | `#F87171` | Decreases, errors | 7.2 / 6.8 / 6.4 |

Tests require at least 4.5:1 for every text token on every background.

### Chart palettes

- **Categorical (`SERIES_COLORS`):** based on the Okabe-Ito palette, lightened where needed for the dark canvas. Every color has at least 6.5:1 contrast against the canvas (tests require 3:1, WCAG 1.4.11). Series are also named in the legend and hover text, so color is never the only cue.
- **Diverging (`DIVERGING_SCALE`):** `#9A5B00` (−1), `#27272A` (0), `#1F6AA5` (+1) for correlation heatmaps. It avoids red/green. White cell labels have 5.2:1 and 5.5:1 contrast at the endpoints.
- **Direction:** price changes use ▲ / ▼ / ■ symbols in addition to green and red.

## Typography

- **Sans:** Geist, then Inter, then the system UI font. **Mono:** Geist Mono, JetBrains Mono, Cascadia Mono, Consolas. No font files are shipped; the browser uses the first installed font.
- **Scale:** page title 1.875rem, section heading 1.125rem, body 14px, captions 0.75–0.8125rem.
- **Numbers:** tabular numerals in metrics and tables, so columns of figures line up.
- **Metadata** (eyebrows, provenance rows, tags) uses the mono stack.

## Layout

- Main content is capped at 1360px and centered.
- Each page starts with `page_header`: eyebrow, title, a one-paragraph lead, a provenance row (`meta`) and tags such as `DEMO · SYNTHETIC` or `DESCRIPTIVE ONLY`.
- Content is split by `section(title, description)` headings rendered as `<h2>`.
- Page controls live in the page body, not the sidebar. The sidebar holds navigation and the data-mode identity only.
- The sidebar collapses automatically on narrow screens (`initial_sidebar_state="auto"`), and Streamlit's columns stack vertically.

## Components (`ui/design.py`)

| Component | Purpose |
|---|---|
| `apply_styles()` | Injects the single CSS block once per page run |
| `page_header(eyebrow, title, lead, meta=, tags=)` | Page heading with provenance row and tags |
| `section(title, description)` | `<h2>` section heading with an optional muted description |
| `chart(figure, summary=, data=)` | Renders a Plotly figure, a text summary and an expander "Data table for this chart" |
| `sidebar_identity(mode)` | Sidebar tag and note describing the data mode (`demo`, or live and local data) |
| `demo_notice(what)` | Warning that the values shown are synthetic |

All dynamic text passed to these components is HTML-escaped. `test_components_escape_dynamic_text` checks this.

## CSS

The CSS block in `theme.py` is the only custom CSS in the app. It:

- styles CryptoVision's own `cv-*` classes and a few documented Streamlit test ids (`cv-eyebrow`, `cv-title`, `cv-lead`, `cv-meta`, `cv-section`, `cv-tag`, `cv-sidenote`, `cv-brand`);
- sets tabular numerals and the content width;
- adds a visible 2px accent focus ring (`:focus-visible`) for keyboard users.

Streamlit's theme (`config.toml`) does the rest. Keeping custom selectors few makes Streamlit upgrades less likely to break the styling.

## Charts

- The `cryptovision` Plotly template is registered and set as the default when `theme.py` is imported. It uses a transparent background, the token text colors, `border` grid lines, the categorical palette, and a horizontal legend above the plot.
- `PLOTLY_CONFIG` hides the Plotly logo and removes the lasso and box-select tools.
- Charts with many categories use horizontal bars. Log scales are labelled in the axis title.
- Missing days are shown as gaps, never interpolated.

## Accessibility

Checked:

- Text contrast and chart color contrast (automated tests).
- Charts have text summaries and data tables; tables passed to `st.dataframe` carry `alt` text where Streamlit supports it.
- Direction is shown with symbols as well as color.
- Keyboard focus is visible (checked manually in Chrome on the radio buttons).
- Layout at 390px width stacks into one column (checked manually in Chrome).

Not checked: screen-reader output, Windows high-contrast mode, browser zoom above 200%, and browsers other than Chrome. No formal accessibility audit has been carried out, so CryptoVision makes no WCAG conformance claim.

## Changing the design

1. Change the value in `Tokens` (or `SERIES_COLORS` / `DIVERGING_SCALE`).
2. Make the same change in `.streamlit/config.toml`.
3. Run `pytest tests/test_design_system.py`. It fails if the two files disagree or if contrast drops below the thresholds.
