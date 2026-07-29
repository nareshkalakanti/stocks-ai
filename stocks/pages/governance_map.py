"""Governance Map — PEAD-style director report (shared boards + Dir Score)."""

from __future__ import annotations

import streamlit as st

from stocks.core.config import (
    DB_PATH,
    GOVERNANCE_DB_PATH,
    GOVERNANCE_MAP_AUTO_HYDRATE_MCAP_MAX,
    GOVERNANCE_MAP_AUTO_HYDRATE_MCAPS,
    GOVERNANCE_MAP_AUTO_HYDRATE_PROFILE_MAX,
    GOVERNANCE_MAP_AUTO_HYDRATE_PROFILES,
    GOVERNANCE_MAP_CACHE_SECONDS,
)
from stocks.core.database import strategy_signals_summary
from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.governance.html import build_governance_map_html, governance_map_iframe_height
from stocks.governance.map_data import (
    build_governance_map_rows,
    hydrate_missing_mcaps,
    hydrate_missing_profiles,
    map_company_ticker_markets,
    missing_mcap_tickers,
    missing_profile_tickers,
)
from stocks.governance.profile_gaps import audit_map_profile_gaps, gap_summary
from stocks.governance.service import governance_stats, init_governance_db


def _governance_db_mtime() -> float:
    try:
        return GOVERNANCE_DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _signals_db_mtime() -> float:
    """Invalidate map cache when Strategy TQ/BB scan updates stocks_ai.db."""
    try:
        return DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


@st.cache_data(ttl=GOVERNANCE_MAP_CACHE_SECONDS, show_spinner=False)
def _cached_governance_map_rows(
    min_boards: int,
    db_mtime: float,
    signals_db_mtime: float,
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
    missing_mcap = missing_mcap_tickers(ticker_markets)
    gaps_nse = audit_map_profile_gaps(min_boards=int(min_boards), nse_only=True)
    gap_stats = gap_summary(gaps_nse)
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

        fill_cols = st.columns([1, 1, 2])
        with fill_cols[0]:
            if st.button(
                f"Fill missing about/web ({len(missing)})",
                use_container_width=True,
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
            if st.button(
                f"Fill missing mcap ({len(missing_mcap)})",
                use_container_width=True,
                disabled=not missing_mcap,
                help="Screener then Yahoo finance · batched on map load was disabled for speed.",
            ):
                batch = min(80, len(missing_mcap) or 0)
                with st.spinner(f"Fetching market cap for up to {batch} names…"):
                    n = hydrate_missing_mcaps(
                        ticker_markets,
                        max_fetch=batch,
                        workers=1,
                    )
                _cached_governance_map_rows.clear()
                st.success(f"Filled {n} market cap row(s).") if n else st.info(
                    "No new market caps fetched."
                )
                st.rerun()
        with fill_cols[2]:
            st.caption(
                f"**NSE map** ({gap_stats['tickers']:,} cos): "
                f"mcap **{gap_stats['missing_mcap']:,}** · "
                f"web **{gap_stats['missing_website']:,}** · "
                f"about **{gap_stats['missing_about']:,}** missing"
            )
            if missing:
                st.caption(f"**{len(missing):,}** still missing website or about (any market).")
            if hydrate_profiles or hydrate_mcaps:
                st.caption(
                    "Auto screener backfill on load is **on** "
                    f"(profiles≤{hydrate_profile_max}, mcap≤{hydrate_mcap_max}) — "
                    "set `GOVERNANCE_MAP_AUTO_HYDRATE_*=false` for faster loads."
                )
            else:
                st.caption(
                    "Map loads from **SQLite cache** (fast). Use **Fill missing** buttons above."
                )
            st.download_button(
                "Download NSE gap CSV",
                data=gaps_nse.to_csv(index=False).encode("utf-8"),
                file_name="governance_map_profile_gaps_nse.csv",
                mime="text/csv",
                key="govmap_gaps_csv",
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
            _signals_db_mtime(),
            hydrate_profiles=hydrate_profiles,
            hydrate_profile_max=hydrate_profile_max,
            hydrate_mcaps=hydrate_mcaps,
            hydrate_mcap_max=hydrate_mcap_max,
        )

    if rows.empty:
        st.info(
            "No shared directors yet. Run **Scan & boards** (Governance → first tab), "
            "then reopen **Director map**."
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
    sig = strategy_signals_summary()
    st.caption(
        f"**{len(rows):,}** directors · **{bridge_n:,}** big↔small bridge · "
        "DIN only · min **2** shared boards · Cap · Holdings · Superstar · "
        f"**TQ** ({sig.get('tq_count', 0):,} cached) · **BB** ({sig.get('bb_count', 0):,} cached) tags"
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
