"""HTML report for Inst Entry strategy."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

INST_ENTRY_JS_COLS = [
    {"id": "rank", "label": "#", "fmt": "int"},
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "first_time_entry", "label": "1st?", "fmt": "text"},
    {"id": "institutional_pct_delta", "label": "Inst Δ pp", "fmt": "num2"},
    {"id": "institutional_pct_now", "label": "Inst %", "fmt": "num2"},
    {"id": "quarter_end", "label": "Quarter", "fmt": "date"},
    {"id": "price_to_sales", "label": "Mcap/Sales", "fmt": "num2"},
    {"id": "market_cap_cr", "label": "Mcap Cr", "fmt": "num1"},
    {"id": "debt_to_equity", "label": "D/E", "fmt": "num2"},
    {"id": "sales_cagr", "label": "Sales CAGR", "fmt": "num1"},
    {"id": "avg_volume", "label": "Avg vol", "fmt": "int"},
    {"id": "ie_gates", "label": "Gates", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
]


def _with_rank(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    if "first_time_entry" in out.columns:
        out["first_time_entry"] = out["first_time_entry"].map(
            lambda v: "FIRST" if bool(v) else "ADD"
        )
    if "rank" not in out.columns or out["rank"].isna().all():
        out = out.reset_index(drop=True)
        out["rank"] = range(1, len(out) + 1)
    return out


def build_inst_entry_html(
    df: pd.DataFrame,
    *,
    title: str = "Inst Entry",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    del title, subtitle
    work = _with_rank(df)
    section = build_interactive_section(
        "instentry",
        "Inst Entry — micro value gates + DII/FII entry trigger",
        work,
        INST_ENTRY_JS_COLS,
        kind="inst_entry",
        open_section=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def inst_entry_iframe_height(row_count: int) -> int:
    return min(2200, max(560, 400 + min(row_count, 50) * 22))
