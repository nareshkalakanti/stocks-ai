"""HTML report for low-volatility factor scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

LOW_VOL_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "vol_rank", "label": "Rank", "fmt": "int"},
    {"id": "short_vol", "label": "ST Vol%", "fmt": "num1"},
    {"id": "long_vol", "label": "LT Vol%", "fmt": "num1"},
    {"id": "composite_vol", "label": "Avg Vol%", "fmt": "num1"},
    {"id": "score", "label": "Score", "fmt": "score"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "date", "label": "As of", "fmt": "date"},
]


def build_low_vol_html(
    df: pd.DataFrame,
    *,
    standalone: bool = True,
) -> str:
    section = build_interactive_section(
        "lowvol",
        "Low Volatility — bottom 20% by short (21d) + long (252d) annualized vol",
        df,
        LOW_VOL_JS_COLS,
        kind="low_vol",
        open_section=True,
        expand_hint="Click row — website · quarterly · TV",
        fetch_news=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def low_vol_iframe_height(row_count: int) -> int:
    return min(2400, max(620, 420 + min(row_count, 50) * 24))
