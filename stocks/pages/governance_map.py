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
        "Directors on **2+** boards · **By company** = shared board · "
        "**By role** = same title across cos (Compliance / CFO / CS) · "
        "Red **suspect** = likely name collision."
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

    f1, f2, f3 = st.columns([1, 1, 1])
    with f1:
        min_boards = st.selectbox(
            "Min boards",
            options=[2, 3, 4],
            index=0,
            key="gov_map_min_boards",
        )
    with f2:
        din_only = st.checkbox(
            "DIN-backed only",
            value=False,
            key="gov_map_din_only",
            help="Hide name-only matches (noisier Yahoo overlaps).",
        )
    with f3:
        hide_collisions = st.checkbox(
            "Hide name collisions",
            value=True,
            key="gov_map_hide_collisions",
            help="Hide name-only directors on 5+ boards (common-name false merges).",
            disabled=din_only,
        )

    search_q = st.text_input(
        "Search stock / director",
        key="gov_map_search",
        placeholder="e.g. INA, Insolation, or director name",
        help="Filters the map by ticker, company name, or director.",
    )

    ticker_markets = map_company_ticker_markets(min_boards=int(min_boards))
    missing = missing_profile_tickers(ticker_markets)
    fill_cols = st.columns([1, 2])
    with fill_cols[0]:
        if st.button(
            f"Fill missing about/web ({len(missing)})",
            use_container_width=True,
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

    collision_n = 0
    if "name_collision" in rows.columns:
        collision_n = int(rows["name_collision"].fillna(False).astype(bool).sum())

    if din_only and "din_backed" in rows.columns:
        rows = rows[rows["din_backed"].astype(bool)].copy()
        if rows.empty:
            st.warning("No DIN-backed multi-board directors yet.")
            return
        rows = rows.reset_index(drop=True)
        rows["rank"] = range(1, len(rows) + 1)
    elif hide_collisions and "name_collision" in rows.columns:
        rows = rows[~rows["name_collision"].fillna(False).astype(bool)].copy()
        if rows.empty:
            st.warning("All remaining rows look like name collisions. Turn the filter off or use DIN sources.")
            return
        rows = rows.reset_index(drop=True)
        rows["rank"] = range(1, len(rows) + 1)

    bridge_n = int(rows["bridge"].fillna(False).astype(bool).sum()) if "bridge" in rows.columns else 0
    filter_note = ""
    if din_only:
        filter_note = " · DIN only"
    elif hide_collisions and collision_n:
        filter_note = f" · hid {collision_n:,} name collisions"
    st.caption(
        f"**{len(rows):,}** directors · **{bridge_n:,}** with big↔small bridge"
        f"{filter_note} · click headers to sort"
    )

    embed_html = build_governance_map_html(
        rows,
        title="Governance Map",
        standalone=False,
        initial_query=str(search_q or ""),
    )
    embed_html_iframe(
        embed_html,
        height=governance_map_iframe_height(len(rows)),
        key="gov_map_iframe",
    )
