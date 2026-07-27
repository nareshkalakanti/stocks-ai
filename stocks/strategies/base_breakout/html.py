"""HTML report for weekly base breakout scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

BASE_BREAKOUT_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "signal", "label": "Signal", "fmt": "text"},
    {"id": "score", "label": "Score", "fmt": "score"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "detail", "label": "Setup", "fmt": "text"},
    {"id": "date", "label": "As of", "fmt": "date"},
]


def build_base_breakout_html(
    df: pd.DataFrame,
    *,
    standalone: bool = True,
) -> str:
    section = build_interactive_section(
        "basebreakout",
        "Weekly Base Breakout — long consolidation near breakout (expand row for chart · TV to verify)",
        df,
        BASE_BREAKOUT_JS_COLS,
        kind="base_breakout",
        open_section=True,
        expand_hint="Click row — weekly base chart + TradingView link",
        fetch_news=False,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def base_breakout_iframe_height(row_count: int) -> int:
    return min(2600, max(700, 480 + min(row_count, 50) * 24))
