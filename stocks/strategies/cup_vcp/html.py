"""HTML reports for Cup & Handle and VCP scans (annotated charts on expand)."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

PATTERN_SCAN_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "signal", "label": "Signal", "fmt": "text"},
    {"id": "score", "label": "Score", "fmt": "score"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "detail", "label": "Setup", "fmt": "text"},
    {"id": "date", "label": "As of", "fmt": "date"},
]

_CUP_HANDLE_META = {
    "section_id": "cuphandle",
    "kind": "cup_handle",
    "subtitle": "Cup & Handle — weekly/daily setups near rim (expand row for drawn shape · TV to verify)",
    "expand_hint": "Click row — cup/handle chart · website · quarterly · TV",
}

_VCP_META = {
    "section_id": "vcp",
    "kind": "vcp",
    "subtitle": "VCP — volatility contractions into pivot (expand row for chart · TV to verify)",
    "expand_hint": "Click row — VCP chart · website · quarterly · TV",
}


def _build_pattern_html(
    df: pd.DataFrame,
    *,
    meta: dict[str, str],
    standalone: bool,
) -> str:
    section = build_interactive_section(
        meta["section_id"],
        meta["subtitle"],
        df,
        PATTERN_SCAN_JS_COLS,
        kind=meta["kind"],
        open_section=True,
        expand_hint=meta["expand_hint"],
        fetch_news=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def build_cup_handle_html(
    df: pd.DataFrame,
    *,
    standalone: bool = True,
) -> str:
    return _build_pattern_html(df, meta=_CUP_HANDLE_META, standalone=standalone)


def build_vcp_html(
    df: pd.DataFrame,
    *,
    standalone: bool = True,
) -> str:
    return _build_pattern_html(df, meta=_VCP_META, standalone=standalone)


def build_cup_vcp_html(
    df: pd.DataFrame,
    *,
    standalone: bool = True,
) -> str:
    """Legacy combined report — prefer build_cup_handle_html / build_vcp_html."""
    return build_cup_handle_html(df, standalone=standalone)


def pattern_scan_iframe_height(row_count: int) -> int:
    return min(2600, max(700, 480 + min(row_count, 50) * 24))


def cup_vcp_iframe_height(row_count: int) -> int:
    return pattern_scan_iframe_height(row_count)
