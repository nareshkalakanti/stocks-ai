"""HTML report for Alpha Hide (SARVADA-style) scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

ALPHA_HIDE_JS_COLS = [
    {"id": "rank", "label": "#", "fmt": "int"},
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "phase", "label": "Phase", "fmt": "text"},
    {"id": "ah_ingredients", "label": "Ingredients", "fmt": "text"},
    {"id": "pe_ratio", "label": "PE", "fmt": "num1"},
    {"id": "ev_ebitda", "label": "EV/EBITDA", "fmt": "num2"},
    {"id": "price_to_sales", "label": "Mcap/Sales", "fmt": "num2"},
    {"id": "sales_cagr", "label": "Sales CAGR", "fmt": "num1"},
    {"id": "drawdown_pct", "label": "DD %", "fmt": "num1"},
    {"id": "promoter_pct_delta", "label": "Prom Δ", "fmt": "num2"},
    {"id": "institutional_pct_delta", "label": "Inst Δ", "fmt": "num2"},
    {"id": "market_cap_cr", "label": "Mcap Cr", "fmt": "num1"},
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


def build_alpha_hide_html(
    df: pd.DataFrame,
    *,
    title: str = "Alpha Hide",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    del title, subtitle
    work = _with_rank(df)
    section = build_interactive_section(
        "alphahide",
        "Alpha Hide — Phase I/II · Valuation · Growth · Contrarian · Inflection · Promoter",
        work,
        ALPHA_HIDE_JS_COLS,
        kind="alpha_hide",
        open_section=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def alpha_hide_iframe_height(row_count: int) -> int:
    return min(2200, max(560, 400 + min(row_count, 50) * 22))
