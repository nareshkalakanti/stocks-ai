"""Governance Map — PEAD-style director report (shared boards + Dir Score)."""

from __future__ import annotations

import streamlit as st

from stocks.core.config import (
    GOVERNANCE_DB_PATH,
    GOVERNANCE_MAP_AUTO_HYDRATE_MCAP_MAX,
    GOVERNANCE_MAP_AUTO_HYDRATE_MCAPS,
    GOVERNANCE_MAP_AUTO_HYDRATE_PROFILE_MAX,
    GOVERNANCE_MAP_AUTO_HYDRATE_PROFILES,
    GOVERNANCE_MAP_CACHE_SECONDS,
)
from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.governance.html import build_governance_map_html, governance_map_iframe_height
from stocks.governance.map_data import (
    build_governance_map_rows,
    hydrate_missing_profiles,
    map_company_ticker_markets,
    missing_profile_tickers,
)
from stocks.governance.service import governance_stats, init_governance_db


def _governance_db_mtime() -> float:
    try:
        return GOVERNANCE_DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


@st.cache_data(ttl=GOVERNANCE_MAP_CACHE_SECONDS, show_spinner=False)
def _cached_governance_map_rows(
    min_boards: int,
    db_mtime: float,
    *,
    hydrate_profiles: bool,
    hydrate_profile_max: int,
    hydrate_mcaps: bool,
    hydrate_mcap_max: int,
):
    return build_governance_map_rows(
        min_boards=min_boards,
        hydrate_profiles=hydrate_profiles,
        hydrate_max=hydrate_profile_max,
        hydrate_mcaps=hydrate_mcaps,
        hydrate_mcap_max=hydrate_mcap_max,
    )


def render_governance_map(*, show_title: bool = True) -> None:
    init_governance_db()
    if show_title:
        st.markdown("### Governance Map")

    min_boards = 2
    ticker_markets = map_company_ticker_markets(min_boards=int(min_boards))
    missing = missing_profile_tickers(ticker_markets)
    stats = governance_stats()

    hydrate_profiles = GOVERNANCE_MAP_AUTO_HYDRATE_PROFILES
    hydrate_mcaps = GOVERNANCE_MAP_AUTO_HYDRATE_MCAPS
    hydrate_profile_max = (
        GOVERNANCE_MAP_AUTO_HYDRATE_PROFILE_MAX if hydrate_profiles else 0
    )
    hydrate_mcap_max = GOVERNANCE_MAP_AUTO_HYDRATE_MCAP_MAX if hydrate_mcaps else 0

    with st.expander("Stats & fill (open / hide)", expanded=False):
        st.caption(
            "**DIN-backed** directors on **2+** boards · "
            "**By company** = shared board · **By role** = same title across cos."
        )
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Companies", stats["companies"])
        with c2:
            st.metric("On 2+ boards", stats["multi_board_directors"])
        with c3:
            st.metric("With DIN", stats.get("directors_with_din", 0))
        with c4:
            st.metric("Seats", stats["seats"])

        fill_cols = st.columns([1, 2])
        with fill_cols[0]:
            if st.button(
                f"Fill missing about/web ({len(missing)})",
                width="stretch",
                disabled=not missing,
                help="Slow screener.in + Yahoo backfill for companies still missing website or about.",
            ):
                batch = min(120, len(missing) or 0)
                with st.spinner(
                    f"Slow-fetching profiles for up to {batch} companies "
                    "(~1.5s each via screener)…"
                ):
                    n = hydrate_missing_profiles(
                        ticker_markets,
                        max_fetch=batch,
                        workers=1,
                    )
                _cached_governance_map_rows.clear()
                st.success(f"Filled {n} profile(s).") if n else st.info(
                    "No new profiles fetched."
                )
                st.rerun()
        with fill_cols[1]:
            if missing:
                st.caption(f"**{len(missing):,}** map companies still missing website or about.")
            if hydrate_profiles or hydrate_mcaps:
                st.caption(
                    "Auto screener backfill on load is **on** "
                    f"(profiles≤{hydrate_profile_max}, mcap≤{hydrate_mcap_max}) — "
                    "set `GOVERNANCE_MAP_AUTO_HYDRATE_*=false` for faster loads."
                )
            else:
                st.caption(
                    "Map loads from **SQLite cache** (fast). Use **Fill missing** for screener backfill."
                )

    spinner_msg = (
        "Building governance map (screener backfill)…"
        if (hydrate_profiles and hydrate_profile_max) or (hydrate_mcaps and hydrate_mcap_max)
        else "Loading governance map…"
    )
    with st.spinner(spinner_msg):
        rows = _cached_governance_map_rows(
            int(min_boards),
            _governance_db_mtime(),
            hydrate_profiles=hydrate_profiles,
            hydrate_profile_max=hydrate_profile_max,
            hydrate_mcaps=hydrate_mcaps,
            hydrate_mcap_max=hydrate_mcap_max,
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

    bridge_n = (
        int(rows["bridge"].fillna(False).astype(bool).sum())
        if "bridge" in rows.columns
        else 0
    )
    st.caption(
        f"**{len(rows):,}** directors · **{bridge_n:,}** big↔small bridge · "
        "DIN only · min **2** shared boards · Cap · Holdings · Superstar tags"
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
        key="governance_map",
    )
