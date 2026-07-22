"""HTML report for Micro Value strategy scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

MICRO_VALUE_JS_COLS = [
    {"id": "rank", "label": "#", "fmt": "int"},
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "mv_score", "label": "Score", "fmt": "num1"},
    {"id": "price_to_sales", "label": "Mcap/Sales", "fmt": "num2"},
    {"id": "market_cap_cr", "label": "Mcap Cr", "fmt": "num1"},
    {"id": "pe_ratio", "label": "PE", "fmt": "num1"},
    {"id": "sales_growth", "label": "Sales YoY", "fmt": "num1"},
    {"id": "debt_to_equity", "label": "D/E", "fmt": "num2"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
]


def _with_rank(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    if "rank" not in out.columns or out["rank"].isna().all():
        out = out.reset_index(drop=True)
        out["rank"] = range(1, len(out) + 1)
    return out


def build_micro_value_html(
    df: pd.DataFrame,
    *,
    title: str = "Micro Value",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    del title, subtitle
    work = _with_rank(df)
    section = build_interactive_section(
        "microv",
        "Micro Value — 20–200 Cr · Mcap/Sales < 1",
        work,
        MICRO_VALUE_JS_COLS,
        kind="micro_value",
        open_section=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def micro_value_iframe_height(row_count: int) -> int:
    return min(2200, max(560, 400 + min(row_count, 50) * 22))
