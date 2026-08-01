"""Fund Watchlists — Negen / Niveshaay (separate from personal Holdings)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.text_utils import safe_str
from stocks.shared.fund_watchlists import (
    FUND_WATCHLIST_DEFS,
    fund_watchlist_label,
    load_fund_watchlist_df,
    sync_all_fund_watchlists,
    sync_fund_watchlist_from_superstars,
)
from stocks.shared.links import screener_url, tradingview_url


def _ensure_synced_if_empty() -> None:
    """First open: pull from SuperStars DB if watchlists are empty."""
    for key in FUND_WATCHLIST_DEFS:
        if load_fund_watchlist_df(key).empty:
            sync_fund_watchlist_from_superstars(key)


def _render_list_table(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        st.caption("No tickers yet — sync from SuperStars after a SuperStars refresh.")
        return
    rows = []
    for _, row in df.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        market = safe_str(row.get("market")).upper() or "NSE"
        name = safe_str(row.get("name")) or ticker
        entity = safe_str(row.get("holding_entity")) or "—"
        val = row.get("holding_value_cr")
        try:
            val_txt = f"₹{float(val):.1f} Cr" if val is not None and not pd.isna(val) else "—"
        except (TypeError, ValueError):
            val_txt = "—"
        sc = screener_url(ticker, market)
        tv = tradingview_url(ticker, market)
        rows.append(
            {
                "Ticker": ticker,
                "Company": name,
                "Held via": entity,
                "Value": val_txt,
                "SC": sc,
                "TV": tv,
            }
        )
    show = pd.DataFrame(rows)
    st.dataframe(
        show,
        width="stretch",
        hide_index=True,
        column_config={
            "SC": st.column_config.LinkColumn("SC", display_text="SC"),
            "TV": st.column_config.LinkColumn("TV", display_text="TV"),
        },
    )


def render_fund_watchlist_panel(list_key: str, *, show_title: bool = True) -> None:
    """Single fund watchlist (Negen / Niveshaay)."""
    _ensure_synced_if_empty()
    label = fund_watchlist_label(list_key)
    if show_title:
        st.markdown(f"#### {label}")
    meta = FUND_WATCHLIST_DEFS.get(list_key) or {}
    inv = ", ".join(meta.get("investor_names") or [])
    df = load_fund_watchlist_df(list_key)
    st.caption(
        f"{len(df):,} stocks · synced from SuperStars ({inv or 'refresh SuperStars first'})"
    )
    _render_list_table(df)


def render_fund_watchlists(*, show_title: bool = True) -> None:
    if show_title:
        st.markdown("### Fund Watchlists")
    st.caption(
        "**Separate from Holdings** · Negen & Niveshaay synced from SuperStars. "
        "Open **Watching → List** to switch between fund lists."
    )

    _ensure_synced_if_empty()

    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    with c2:
        sync = st.button(
            "Sync from SuperStars",
            type="primary",
            width="stretch",
            help="Replace watchlists from latest SuperStars Negen / Niveshaay holdings in DB.",
            key="fund_watchlists_sync_all",
        )
    if sync:
        counts = sync_all_fund_watchlists()
        bits = [f"**{fund_watchlist_label(k)}** {n}" for k, n in counts.items()]
        if sum(counts.values()) == 0:
            st.warning(
                "No SuperStars rows for Negen/Niveshaay yet — open SuperStars → Refresh all first."
            )
        else:
            st.success("Synced · " + " · ".join(bits))

    tabs = st.tabs([fund_watchlist_label(k) for k in FUND_WATCHLIST_DEFS])
    for tab, key in zip(tabs, FUND_WATCHLIST_DEFS, strict=False):
        with tab:
            render_fund_watchlist_panel(key, show_title=False)
