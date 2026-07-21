"""HTML report for Cash Quality strategy scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

CASH_QUALITY_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "cq_score", "label": "Score", "fmt": "num1"},
    {"id": "cq_checks", "label": "Checks", "fmt": "text"},
    {"id": "cash_to_tax", "label": "Cash/Tax", "fmt": "num2"},
    {"id": "croic", "label": "CROIC", "fmt": "num2"},
    {"id": "ccc_years", "label": "CCC Y", "fmt": "num2"},
    {"id": "ccc_days", "label": "CCC d", "fmt": "num1"},
    {"id": "ocf_ebitda_growth", "label": "OCF/EBITDA g", "fmt": "num2"},
    {"id": "ocf_to_ebitda", "label": "OCF/EBITDA", "fmt": "num2"},
    {"id": "ocf_cagr", "label": "OCF CAGR", "fmt": "num1"},
    {"id": "ebitda_cagr", "label": "EBITDA CAGR", "fmt": "num1"},
    {"id": "market_cap_cr", "label": "Mcap Cr", "fmt": "num1"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
]


def build_cash_quality_html(
    df: pd.DataFrame,
    *,
    title: str = "Cash Quality",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    del title, subtitle
    section = build_interactive_section(
        "cashq",
        "Cash Quality — CROIC, CCC, Cash/Tax, OCF vs EBITDA growth",
        df,
        CASH_QUALITY_JS_COLS,
        kind="cash_quality",
        open_section=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def cash_quality_iframe_height(row_count: int) -> int:
    return min(2200, max(560, 400 + min(row_count, 50) * 22))
