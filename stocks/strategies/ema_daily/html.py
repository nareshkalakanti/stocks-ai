"""HTML report for daily above-all-EMAs scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

EMA_DAILY_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "date", "label": "Day", "fmt": "date"},
]


def build_ema_daily_html(
    df: pd.DataFrame,
    *,
    title: str = "Above All EMAs",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    del title, subtitle
    section = build_interactive_section(
        "emad",
        "Daily — price above EMA 20 · 50 · 100 · 200",
        df,
        EMA_DAILY_JS_COLS,
        kind="ema_daily",
        open_section=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def ema_daily_iframe_height(row_count: int) -> int:
    return min(2200, max(560, 400 + min(row_count, 50) * 22))
