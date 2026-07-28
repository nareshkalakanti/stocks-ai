"""HTML report for momentum factor scan (spreadsheet-style columns)."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

# Match: Symbol | Company | Sector | Subsector | Price | Price 1Y | Price 1M | Momentum
FACTOR_JS_COLS = [
    {"id": "ticker", "label": "Symbol", "fmt": "text"},
    {"id": "company", "label": "Company Name", "fmt": "company"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "sub_sector", "label": "Subsector", "fmt": "text"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "price_1y", "label": "Price 1Y", "fmt": "num2"},
    {"id": "price_1m", "label": "Price 1M", "fmt": "num2"},
    {"id": "momentum_pct", "label": "Momentum", "fmt": "pct2"},
]


def build_factor_html(
    df: pd.DataFrame,
    *,
    standalone: bool = True,
) -> str:
    section = build_interactive_section(
        "factor",
        "Momentum — top 20% by 12–1 return (sorted by Momentum)",
        df,
        FACTOR_JS_COLS,
        kind="factor",
        open_section=True,
        expand_hint="Click row — website · quarterly · TV",
        fetch_news=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def factor_iframe_height(row_count: int) -> int:
    return min(2400, max(620, 420 + min(row_count, 50) * 24))
