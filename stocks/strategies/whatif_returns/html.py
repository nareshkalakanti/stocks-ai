"""HTML report for Market·Cap price-change scan (Quant-style interactive table)."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.dashboards.interactive_table import (
    build_interactive_section,
    wrap_interactive_page,
)
from stocks.strategies.whatif_returns.service import (
    RETURN_HORIZONS,
    YTD_COL,
    YTD_LABEL,
    top_performers,
)

PRICE_CHANGE_JS_COLS = [
    {"id": "rank", "label": "#", "fmt": "int"},
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "ret_ytd", "label": "YTD", "fmt": "pct_signed"},
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


def _value_cols(invest_amount: float, *, include: set[str]) -> list[dict]:
    amt = float(invest_amount)
    label = f"₹{amt:,.0f}" if amt == int(amt) else f"₹{amt:,.2f}"
    out: list[dict] = []
    if YTD_COL in include:
        out.append({"id": f"val_{YTD_COL}", "label": f"{label}→{YTD_LABEL}", "fmt": "num0"})
    for col, _m, lab in RETURN_HORIZONS:
        if col in include and col in {"ret_3m", "ret_6m", "ret_12m", "ret_24m"}:
            out.append({"id": f"val_{col}", "label": f"{label}→{lab}", "fmt": "num0"})
    return out


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
    One Quant-style section (like Momentum) so expand payload
    (website · quarterly · SC/TV) is embedded once and stays complete.
    Primary: invest at year-start → value now (YTD).
    """
    work = _normalize_price_change_df(df)
    cols = list(PRICE_CHANGE_JS_COLS)
    for opt in _OPTIONAL_RET_COLS:
        if _col_has_data(work, opt["id"]):
            cols.append(opt)

    value_include = {YTD_COL, "ret_3m", "ret_6m"}
    if _col_has_data(work, "ret_12m"):
        value_include.add("ret_12m")
    if _col_has_data(work, "ret_24m"):
        value_include.add("ret_24m")
    cols = cols + _value_cols(invest_amount, include=value_include)

    bits: list[str] = []
    if summary is not None and not summary.empty:
        for hz, col in (
            (YTD_LABEL, YTD_COL),
            ("1M", "ret_1m"),
            ("3M", "ret_3m"),
            ("6M", "ret_6m"),
            ("12M", "ret_12m"),
            ("24M", "ret_24m"),
        ):
            if col in ("ret_12m", "ret_24m") and not _col_has_data(work, col):
                continue
            row = summary[summary["horizon"] == hz]
            if row.empty:
                continue
            ret = row.iloc[0].get("avg_return_pct")
            top = safe_str(row.iloc[0].get("top_ticker"))
            top_r = row.iloc[0].get("top_return_pct")
            if ret is None:
                continue
            bit = f"{hz} avg {float(ret):+.1f}%"
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
        f"Price Change — {amt_s} at year-start → now (YTD) · Market · Cap"
        + ((" · " + " · ".join(bits[:4])) if bits else "")
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
