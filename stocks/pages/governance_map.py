"""Governance Map — PEAD-style director report (shared boards + Dir Score)."""

from __future__ import annotations

import streamlit as st

from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.governance.html import build_governance_map_html, governance_map_iframe_height
from stocks.governance.map_data import (
    build_governance_map_rows,
    hydrate_missing_profiles,
    map_company_ticker_markets,
    missing_profile_tickers,
)
from stocks.governance.service import governance_stats, init_governance_db


def render_governance_map(*, show_title: bool = True) -> None:
    init_governance_db()
    if show_title:
        st.markdown("### Governance Map")
    st.caption(
        "**DIN-backed** directors on **2+** boards · tap **SME** for scanned Emerge "
        "names (incl. single-board) · **By company** = shared board · "
        "**By role** = same title across cos."
    )

    stats = governance_stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Companies", stats["companies"])
    with c2:
        st.metric("On 2+ boards", stats["multi_board_directors"])
    with c3:
        st.metric("With DIN", stats.get("directors_with_din", 0))
    with c4:
        st.metric("Seats", stats["seats"])

    # Fixed defaults (filters UI removed): DIN-only, min 2 boards.
    min_boards = 2

    ticker_markets = map_company_ticker_markets(min_boards=int(min_boards))
    missing = missing_profile_tickers(ticker_markets)
    fill_cols = st.columns([1, 2])
    with fill_cols[0]:
        if st.button(
            f"Fill missing about/web ({len(missing)})",
            width="stretch",
            disabled=not missing,
            help="Pull website + about from screener.in for companies still blank (batched).",
        ):
            with st.spinner(f"Fetching profiles for up to {min(120, len(missing))} companies…"):
                n = hydrate_missing_profiles(ticker_markets, max_fetch=min(120, len(missing) or 0))
            st.success(f"Filled {n} profile(s).") if n else st.info("No new profiles fetched.")
            st.rerun()
    with fill_cols[1]:
        if missing:
            st.caption(
                f"**{len(missing):,}** map companies still missing website or about "
                f"(e.g. auto-fills ~60 on load; use the button for more)."
            )

    with st.spinner("Building governance map…"):
        rows = build_governance_map_rows(
            min_boards=int(min_boards),
            hydrate_profiles=True,
            hydrate_max=60,
            hydrate_mcaps=True,
            hydrate_mcap_max=40,
        )

    if rows.empty:
        st.info(
            "No shared directors yet. Run **Governance** scan on overlapping "
            "sectors, then reopen this map."
        )
        return

    if "din_backed" in rows.columns:
        rows = rows[rows["din_backed"].astype(bool)].copy()
        if rows.empty:
            st.warning("No DIN-backed multi-board directors yet.")
            return
        rows = rows.reset_index(drop=True)
        rows["rank"] = range(1, len(rows) + 1)

    bridge_n = int(rows["bridge"].fillna(False).astype(bool).sum()) if "bridge" in rows.columns else 0
    cross_n = int(rows["sme_cross"].fillna(False).astype(bool).sum()) if "sme_cross" in rows.columns else 0
    st.caption(
        f"**{len(rows):,}** directors · **{bridge_n:,}** big↔small bridge · "
        f"**{cross_n:,}** SME↔Main crossover · DIN only · "
        "toolbar tags: Cap · Holdings · SME · Cross"
    )

    embed_html = build_governance_map_html(
        rows,
        title="Governance Map",
        standalone=False,
        min_boards=int(min_boards),
    )
    embed_html_iframe(
        embed_html,
        height=governance_map_iframe_height(len(rows)),
        key="gov_map_iframe",
    )
