"""Holdings industries-only filter — shared across scan pages."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.scans.holdings_playlist import (
    filter_stocks_by_holdings_industries,
    holdings_industry_labels,
)

_HOLDINGS_INDUSTRIES_HELP = (
    "When checked, scan only stocks in industries held in your portfolio."
)
_CHECKBOX_LABEL = "My industries"


def render_holdings_industries_checkbox(*, key: str) -> bool:
    return st.checkbox(
        _CHECKBOX_LABEL,
        value=False,
        key=key,
        help=_HOLDINGS_INDUSTRIES_HELP,
    )


def apply_holdings_industries_if_checked(
    filtered: pd.DataFrame,
    *,
    enabled: bool,
) -> tuple[pd.DataFrame, str] | None:
    """Narrow *filtered* to Holdings portfolio industries. Returns None if UI should stop."""
    if not enabled:
        return filtered, ""

    industry_labels = holdings_industry_labels()
    if not industry_labels:
        st.warning("No industries in Holdings — uncheck the box or update your portfolio.")
        return None

    out = filter_stocks_by_holdings_industries(filtered)
    note = (
        f" · **My industries** ({len(industry_labels)}): "
        f"{', '.join(industry_labels[:8])}"
        f"{'…' if len(industry_labels) > 8 else ''}"
    )
    if out.empty:
        st.warning(
            "No listings match your Holdings industries with the current market filters."
        )
        return None
    return out, note
