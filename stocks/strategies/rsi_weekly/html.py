"""HTML report for weekly RSI entry scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

RSI_WEEKLY_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "rsi", "label": "RSI", "fmt": "num2"},
    {"id": "prev_rsi", "label": "Prev RSI", "fmt": "num2"},
    {"id": "signal", "label": "Signal", "fmt": "text"},
    {"id": "date", "label": "Week", "fmt": "date"},
]


def build_rsi_weekly_html(
    df: pd.DataFrame,
    *,
    title: str = "RSI Weekly",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    del title, subtitle
    section = build_interactive_section(
        "rsiw",
        "RSI Weekly — entry cross ≥60 (new cross replaces prior)",
        df,
        RSI_WEEKLY_JS_COLS,
        kind="rsi_weekly",
        open_section=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def rsi_weekly_iframe_height(row_count: int) -> int:
    return min(2200, max(560, 400 + min(row_count, 50) * 22))
