"""HTML report for DCF strategy scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

DCF_JS_COLS = [
    {"id": "rank", "label": "#", "fmt": "int"},
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "verdict", "label": "Verdict", "fmt": "text"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "fair_price", "label": "Fair", "fmt": "num2"},
    {"id": "upside_pct", "label": "Upside %", "fmt": "num1"},
    {"id": "implied_growth", "label": "Implied g%", "fmt": "num1"},
    {"id": "growth", "label": "Assumed g%", "fmt": "num1"},
    {"id": "discount_rate", "label": "r%", "fmt": "num1"},
    {"id": "terminal_growth", "label": "Term g%", "fmt": "num1"},
    {"id": "base_fcf", "label": "Base FCF", "fmt": "num0"},
    {"id": "equity_value", "label": "Equity val", "fmt": "num0"},
    {"id": "market_cap_cr", "label": "Mcap Cr", "fmt": "num1"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
]


def _with_rank(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    need = "rank" not in out.columns or out["rank"].isna().all()
    if need:
        out = out.reset_index(drop=True)
        out["rank"] = range(1, len(out) + 1)
    else:
        out["rank"] = pd.to_numeric(out["rank"], errors="coerce").astype("Int64")
    return out


def build_dcf_html(
    df: pd.DataFrame,
    *,
    title: str = "DCF",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    del title, subtitle
    work = _with_rank(df)
    section = build_interactive_section(
        "dcf",
        "DCF — forecast FCF + terminal value vs market price",
        work,
        DCF_JS_COLS,
        kind="dcf",
        open_section=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def dcf_iframe_height(row_count: int) -> int:
    return min(2200, max(560, 400 + min(row_count, 50) * 22))
