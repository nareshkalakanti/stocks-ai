"""Single-row bordered scan toolbars (filters + page controls)."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from typing import TYPE_CHECKING

import streamlit as st

from stocks.core.config import (
    CAP_TIERS,
    DEFAULT_CAP_TIER,
    SCAN_MCAP_MAX_CR,
    SCAN_MCAP_MIN_CR,
    cap_tier_labels,
)
from stocks.scans.scan_playlists import cap_tier_select_disabled

if TYPE_CHECKING:
    import pandas as pd

    from stocks.scans.stock_filters import StockFilters

# Market, sector, sub-sector filter columns.
FILTER_COL_WIDTHS = [0.78, 1.05, 1.05]

CAP_TIER_COL_WIDTH = 0.82
SCAN_BTN_COL_WIDTH = 0.44
COMPACT_SCAN_BTN_COL_WIDTH = 0.32
STOP_BTN_COL_WIDTH = 0.4
WORKERS_COL_WIDTH = 0.52
STRATEGY_CHOICE_COL_WIDTH = 0.68
BB_TIMEFRAME_COL_WIDTH = 0.68

# Indices after FILTER_COL_WIDTHS in every scan toolbar row.
IDX_MARKET = 0
IDX_SECTOR = 1
IDX_INDUSTRY = 2  # Sub sector (fine industry / sub_sector tags)
IDX_CAP_TIER = 3
# First column index for page-specific controls (Scan, Strategy, etc.).
IDX_PAGE_START = 4

_CAP_HELP = (
    "Optional cap filter · default **All caps** (no minimum) · "
    f"or **{SCAN_MCAP_MIN_CR:.0f}–{SCAN_MCAP_MAX_CR:.0f} Cr** and Micro / Small / Mid / Large tiers"
)

_SCAN_TOOLBAR_CSS = """
<style>
/* Scan toolbar — one row, bottom-aligned controls */
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"] {
  align-items: flex-end !important;
  flex-wrap: nowrap !important;
  gap: 0.5rem !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="column"] {
  min-width: 0;
}
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stWidgetLabel"] p {
  white-space: nowrap;
  font-size: 0.8125rem;
  line-height: 1.15;
  margin-bottom: 0.15rem;
}
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stNumberInput"] input {
  min-height: 2.25rem;
}
div[data-testid="stVerticalBlockBorderWrapper"] .stButton button {
  min-height: 2.25rem;
}
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] > div {
  gap: 0.25rem;
}
</style>
"""


def inject_scan_toolbar_css() -> None:
    if st.session_state.get("_scan_toolbar_css"):
        return
    st.markdown(_SCAN_TOOLBAR_CSS, unsafe_allow_html=True)
    st.session_state["_scan_toolbar_css"] = True


def default_cap_tier_label() -> str:
    tier_labels = cap_tier_labels()
    default = next(
        (str(t["label"]) for t in CAP_TIERS if t["id"] == DEFAULT_CAP_TIER),
        tier_labels[0],
    )
    return default if default in tier_labels else tier_labels[0]


def render_cap_tier_select(market: str, *, key: str) -> str:
    tier_labels = cap_tier_labels()
    default = default_cap_tier_label()
    return st.selectbox(
        "Market cap",
        tier_labels,
        index=tier_labels.index(default),
        key=key,
        disabled=cap_tier_select_disabled(market),
        help=_CAP_HELP,
    )


@contextmanager
def scan_toolbar_panel() -> Iterator[None]:
    """Bordered scan toolbar shell (prefer ``scan_toolbar_row`` for single-row layouts)."""
    inject_scan_toolbar_css()
    with st.container(border=True):
        yield


def toolbar_columns(*widths: float, gap: str = "small"):
    return st.columns(list(widths), vertical_alignment="bottom", gap=gap)


def base_scan_extra_widths(*page_widths: float) -> tuple[float, ...]:
    """Standard cap tier column, then page-specific controls."""
    return (CAP_TIER_COL_WIDTH, *page_widths)


@contextmanager
def scan_toolbar_row(*extra_widths: float) -> Iterator[list]:
    """Bordered single row: Market · Sector · Sub sector · … page controls."""
    inject_scan_toolbar_css()
    widths = FILTER_COL_WIDTHS + list(extra_widths)
    with st.container(border=True):
        yield st.columns(widths, vertical_alignment="bottom", gap="small")


def render_base_scan_filters(
    stocks: "pd.DataFrame",
    row: list,
    *,
    key_prefix: str,
    cap_tier_key: str,
) -> tuple["StockFilters", str]:
    """Render Market / Sector / Sub sector / Market cap in one toolbar row."""
    from stocks.scans.stock_filters import render_stock_filters

    filters = render_stock_filters(
        stocks,
        cols=(row[IDX_MARKET], row[IDX_SECTOR], row[IDX_INDUSTRY]),
        key_prefix=key_prefix,
    )
    with row[IDX_CAP_TIER]:
        cap_tier_label_ui = render_cap_tier_select(filters.market, key=cap_tier_key)
    return filters, cap_tier_label_ui
