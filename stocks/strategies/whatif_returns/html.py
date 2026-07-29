"""HTML report for Market·Cap price-change scan (Quant-style interactive table)."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.dashboards.interactive_table import (
    build_interactive_section,
    wrap_interactive_page,
)
from stocks.strategies.whatif_returns.service import YTD_COL, YTD_LABEL, top_performers

PRICE_CHANGE_JS_COLS = [
    {"id": "rank", "label": "#", "fmt": "int"},
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "ret_ytd", "label": "YTD %", "fmt": "pct_signed"},
    {"id": "ret_1m", "label": "1M", "fmt": "pct_signed"},
    {"id": "ret_2m", "label": "2M", "fmt": "pct_signed"},
    {"id": "ret_3m", "label": "3M", "fmt": "pct_signed"},
    {"id": "ret_6m", "label": "6M", "fmt": "pct_signed"},
    {"id": "ret_9m", "label": "9M", "fmt": "pct_signed"},
]

# Only shown when the scan has at least one non-null value.
_OPTIONAL_RET_COLS = (
    {"id": "ret_12m", "label": "12M", "fmt": "pct_signed"},
    {"id": "ret_24m", "label": "24M", "fmt": "pct_signed"},
)


def _col_has_data(df: pd.DataFrame, col: str) -> bool:
    if df is None or df.empty or col not in df.columns:
        return False
    return pd.to_numeric(df[col], errors="coerce").notna().any()


def _worth_today_col(invest_amount: float) -> dict:
    """Single column: ₹ invested at year-start → value today."""
    amt = float(invest_amount)
    label = f"₹{amt:,.0f}" if amt == int(amt) else f"₹{amt:,.2f}"
    return {"id": f"val_{YTD_COL}", "label": f"{label} today", "fmt": "num0"}


def _normalize_price_change_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "price" not in out.columns and "price_now" in out.columns:
        out["price"] = out["price_now"]
    return out


def build_price_change_html(
    df: pd.DataFrame,
    *,
    invest_amount: float = 5000.0,
    summary: pd.DataFrame | None = None,
    standalone: bool = True,
) -> str:
    """
    Quant-style table: YTD % + rolling % · one ₹ column = value today
    if that amount was invested at year-start.
    """
    work = _normalize_price_change_df(df)
    cols = list(PRICE_CHANGE_JS_COLS)
    for opt in _OPTIONAL_RET_COLS:
        if _col_has_data(work, opt["id"]):
            cols.append(opt)
    cols.append(_worth_today_col(invest_amount))

    bits: list[str] = []
    if summary is not None and not summary.empty:
        row = summary[summary["horizon"] == YTD_LABEL]
        if not row.empty:
            ret = row.iloc[0].get("avg_return_pct")
            top = safe_str(row.iloc[0].get("top_ticker"))
            top_r = row.iloc[0].get("top_return_pct")
            if ret is not None:
                bit = f"YTD avg {float(ret):+.1f}%"
                if top and top_r is not None:
                    bit += f" · top {top} {float(top_r):+.1f}%"
                bits.append(bit)

    top_n = top_performers(work, horizon_col=YTD_COL, n=10)
    if top_n.empty:
        top_n = top_performers(work, horizon_col="ret_3m", n=10)
    top_note = ""
    if not top_n.empty:
        leaders = ", ".join(
            f"{safe_str(r.get('ticker'))}"
            for _, r in top_n.head(5).iterrows()
            if safe_str(r.get("ticker"))
        )
        if leaders:
            top_note = f" · Top YTD: {leaders}"

    amt = float(invest_amount)
    amt_s = f"₹{amt:,.0f}" if amt == int(amt) else f"₹{amt:,.2f}"
    headline = (
        f"Price Change — {amt_s} at year-start → worth today · Market · Cap"
        + ((" · " + " · ".join(bits[:2])) if bits else "")
        + top_note
    )

    section = build_interactive_section(
        "pxchg",
        headline,
        work,
        cols,
        kind="price_change",
        open_section=True,
        expand_hint="Click row — website · quarterly · SC · TV · news",
        fetch_news=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def price_change_iframe_height(row_count: int) -> int:
    return min(5200, max(720, 480 + min(row_count, 140) * 24))


__all__ = [
    "PRICE_CHANGE_JS_COLS",
    "build_price_change_html",
    "price_change_iframe_height",
]
