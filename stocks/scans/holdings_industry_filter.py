"""Holdings industries-only filter — shared across scan pages."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.scans.holdings_playlist import (
    filter_stocks_by_holdings_industries,
    holdings_industry_labels,
    holdings_industry_match_spec,
)

_HOLDINGS_INDUSTRIES_HELP = (
    "Limit the scan to display sectors and industries represented in your Holdings "
    "(all peers in those groups, not just your Holdings tickers)."
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

    fine_labels, display_sectors = holdings_industry_match_spec()
    if not fine_labels and not display_sectors:
        st.warning("No industries in Holdings — uncheck the box or update your portfolio.")
        return None

    out = filter_stocks_by_holdings_industries(filtered)
    sector_part = (
        f"{len(display_sectors)} sectors"
        if display_sectors
        else f"{len(fine_labels)} groups"
    )
    note = f" · **My industries** ({sector_part} · {len(out)} listings)"
    if out.empty:
        st.warning(
            "No listings match your Holdings industries with the current market filters."
        )
        return None
    return out, note
