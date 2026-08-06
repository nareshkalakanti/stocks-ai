"""HTML report for SuperStars — same interactive table shell as Governance Map / Cash Quality."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

SUPERSTARS_JS_COLS = [
    {"id": "company", "label": "Company", "fmt": "company"},
    {"id": "investor", "label": "Investor", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "market_cap_cr", "label": "Mcap Cr", "fmt": "num1"},
    {"id": "cap_code", "label": "Cap", "fmt": "cap_code"},
    {"id": "change_display", "label": "Change", "fmt": "ss_change"},
]

SUPERSTARS_CONSENSUS_JS_COLS = [
    {"id": "rank", "label": "#", "fmt": "int"},
    {"id": "company", "label": "Company", "fmt": "company"},
    {"id": "investor_count", "label": "N", "fmt": "int"},
    {"id": "investor", "label": "Investors", "fmt": "text"},
    {"id": "activity", "label": "Activity", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "market_cap_cr", "label": "Mcap Cr", "fmt": "num1"},
    {"id": "cap_code", "label": "Cap", "fmt": "cap_code"},
    {"id": "combined_value_cr", "label": "Value Cr", "fmt": "num1"},
]

SUPERSTARS_JS_COLS_NO_INVESTOR = [
    c for c in SUPERSTARS_JS_COLS if c["id"] != "investor"
]

_EXTRA_COLS = (
    "investor",
    "cap_code",
    "market_cap_cr",
    "change_display",
    "change_type",
    "holding_entity",
    "company_name",
)

_CONSENSUS_EXTRA_COLS = (
    "rank",
    "investor",
    "investor_count",
    "activity",
    "cap_code",
    "market_cap_cr",
    "combined_value_cr",
    "company_name",
)


def _prepare_report_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    if "ticker" not in work.columns and "symbol" in work.columns:
        work["ticker"] = work["symbol"]
    if "market" not in work.columns and "exchange" in work.columns:
        work["market"] = work["exchange"].map(
            lambda x: "BSE" if safe_str(x).upper() == "BSE" else "NSE"
        )
    if "name" not in work.columns:
        work["name"] = work.get("company_name", work.get("ticker", ""))
    work["name"] = work.apply(
        lambda r: safe_str(r.get("name"))
        or safe_str(r.get("company_name"))
        or safe_str(r.get("ticker"))
        or "—",
        axis=1,
    )
    if "sector" in work.columns:
        work["sector"] = work["sector"].map(lambda s: safe_str(s) or "—")
    else:
        work["sector"] = "—"
    if "cap_code" not in work.columns:
        work["cap_code"] = "—"
    else:
        work["cap_code"] = work["cap_code"].map(lambda s: safe_str(s) or "—")
    if "market_cap_cr" not in work.columns:
        work["market_cap_cr"] = pd.NA
    if "change_display" not in work.columns:
        work["change_display"] = "—"
    else:
        work["change_display"] = work["change_display"].map(lambda s: safe_str(s) or "—")
    if "investor" in work.columns:
        work["investor"] = work["investor"].map(lambda s: safe_str(s) or "—")
    return work.reset_index(drop=True)


def build_superstars_html(
    df: pd.DataFrame,
    *,
    title: str = "SuperStars",
    show_investor: bool = False,
    standalone: bool = False,
) -> str:
    work = _prepare_report_df(df)
    cols = SUPERSTARS_JS_COLS if show_investor else SUPERSTARS_JS_COLS_NO_INVESTOR
    section = build_interactive_section(
        "superstars",
        title,
        work,
        cols,
        kind="superstars",
        open_section=True,
        expand_hint="Click row for price, quarterly data & news",
        fetch_news=False,
        extra_cols=_EXTRA_COLS,
        include_superstars=False,
        meta_label="holdings",
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def build_superstars_consensus_html(
    df: pd.DataFrame,
    *,
    title: str = "On 2+ investors",
    standalone: bool = False,
) -> str:
    work = _prepare_report_df(df)
    if not work.empty and "rank" not in work.columns:
        work = work.reset_index(drop=True)
        work.insert(0, "rank", range(1, len(work) + 1))
    section = build_interactive_section(
        "ssconsensus",
        title,
        work,
        SUPERSTARS_CONSENSUS_JS_COLS,
        kind="superstars_consensus",
        open_section=True,
        expand_hint="Click row for price, quarterly data & news",
        fetch_news=False,
        extra_cols=_CONSENSUS_EXTRA_COLS,
        include_superstars=False,
        meta_label="stocks",
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def superstars_iframe_height(row_count: int) -> int:
    return min(2200, max(480, 360 + min(row_count, 60) * 28))


def superstars_consensus_iframe_height(row_count: int) -> int:
    return min(2400, max(420, 320 + min(row_count, 80) * 26))
