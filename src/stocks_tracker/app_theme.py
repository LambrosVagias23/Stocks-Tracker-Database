"""Shared design tokens and Plotly template.

Import from any page via ``from stocks_tracker.app_theme import COLORS, plotly_template``.
Keep this file in sync with ``.streamlit/config.toml`` so the Streamlit
chrome and the Plotly charts share one palette.
"""

from __future__ import annotations

import plotly.graph_objects as go

COLORS = {
    "bg": "#0B0E14",
    "surface": "#131822",
    "surface_alt": "#1A2130",
    "primary": "#5EB3FF",
    "accent": "#FFC857",
    "positive": "#38D39F",
    "negative": "#FF5F6D",
    "text": "#D7DBE6",
    "muted": "#8A94A6",
    "grid": "rgba(215, 219, 230, 0.08)",
    "candle_up": "#38D39F",
    "candle_down": "#FF5F6D",
}

# Ordered series palette (used for multi-line charts, Bollinger bands, etc.)
SERIES_PALETTE = [
    "#5EB3FF",  # primary blue
    "#FFC857",  # amber
    "#B088F9",  # soft violet
    "#4CE0B3",  # mint
    "#FF9F6B",  # coral
    "#73D3FF",  # light cyan
]


def plotly_template() -> go.layout.Template:
    """Return a plotly ``Template`` that matches our dark theme."""
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=COLORS["bg"],
            plot_bgcolor=COLORS["bg"],
            font=dict(
                family="Inter, system-ui, -apple-system, Segoe UI, sans-serif",
                color=COLORS["text"],
                size=13,
            ),
            colorway=SERIES_PALETTE,
            xaxis=dict(
                gridcolor=COLORS["grid"],
                zerolinecolor=COLORS["grid"],
                linecolor=COLORS["grid"],
                tickcolor=COLORS["grid"],
                showspikes=False,
            ),
            yaxis=dict(
                gridcolor=COLORS["grid"],
                zerolinecolor=COLORS["grid"],
                linecolor=COLORS["grid"],
                tickcolor=COLORS["grid"],
            ),
            legend=dict(
                bgcolor="rgba(0,0,0,0)",
                bordercolor=COLORS["grid"],
                borderwidth=0,
                font=dict(color=COLORS["muted"], size=12),
            ),
            hoverlabel=dict(
                bgcolor=COLORS["surface"],
                bordercolor=COLORS["grid"],
                font=dict(color=COLORS["text"], size=12),
            ),
            margin=dict(l=12, r=12, t=28, b=12),
        )
    )


def positive_negative(value: float) -> str:
    """Return ``normal | inverse | off`` for st.metric delta_color based on a signed value."""
    if value is None or value == 0:
        return "off"
    return "normal" if value > 0 else "inverse"
