"""HTML report for Growth strategy scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

GROWTH_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "growth_score", "label": "Score", "fmt": "num1"},
    {"id": "growth_checks", "label": "Checks", "fmt": "text"},
    {"id": "sales_cagr", "label": "Sales CAGR", "fmt": "num1"},
    {"id": "profit_cagr", "label": "Profit CAGR", "fmt": "num1"},
    {"id": "sales_growth", "label": "Sales YoY", "fmt": "num1"},
    {"id": "operating_margin", "label": "Op. mgn", "fmt": "num1"},
    {"id": "gross_margin", "label": "Gross mgn", "fmt": "num1"},
    {"id": "net_margin", "label": "Net mgn", "fmt": "num1"},
    {"id": "roe", "label": "ROE", "fmt": "num1"},
    {"id": "roa", "label": "ROA", "fmt": "num1"},
    {"id": "debt_to_equity", "label": "D/E", "fmt": "num2"},
    {"id": "pe_ratio", "label": "PE", "fmt": "num1"},
    {"id": "market_cap_cr", "label": "Mcap Cr", "fmt": "num1"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
]


def build_growth_html(
    df: pd.DataFrame,
    *,
    title: str = "Growth",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    del title, subtitle
    section = build_interactive_section(
        "growth",
        "Growth — quantitative screen (CAGR, margins, ROE, D/E)",
        df,
        GROWTH_JS_COLS,
        kind="growth",
        open_section=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def growth_iframe_height(row_count: int) -> int:
    return min(2200, max(560, 400 + min(row_count, 50) * 22))
