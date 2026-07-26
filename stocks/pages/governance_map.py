"""Governance Map — PEAD-style director report (shared boards + Dir Score)."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from stocks.core.text_utils import safe_str
from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.governance.html import build_governance_map_html, governance_map_iframe_height
from stocks.governance.map_data import (
    build_governance_map_rows,
    hydrate_missing_profiles,
    map_company_ticker_markets,
    missing_profile_tickers,
    missing_public_holder_tickers,
)
from stocks.governance.service import governance_stats, init_governance_db
from stocks.market.shareholding import export_scanned_shareholding_data
from stocks.market.shareholding_bg import (
    individual_holders_background_status,
    start_individual_holders_background,
    stop_individual_holders_background,
)

_HOLDER_BG_BATCH = 100


def _holder_bg_caption(map_tickers: list[str]) -> None:
    bg = individual_holders_background_status()
    missing_n = len(missing_public_holder_tickers(map_tickers))
    if bg.get("running"):
        scanned = int(bg.get("scanned") or 0)
        pending_now = int(bg.get("pending_now") or missing_n)
        last = safe_str(bg.get("last_ticker")) or "…"
        st.caption(
            f"Background fill running · scanned **{scanned:,}** · "
            f"pending **{pending_now:,}** · last `{last}` · "
            f"batches of {_HOLDER_BG_BATCH}"
        )
        return
    bits: list[str] = []
    if missing_n:
        bits.append(f"**{missing_n:,}** missing individuals >1%")
    err = safe_str(bg.get("error"))
    if err:
        bits.append(f"last error: {err}")
    elif bg.get("finished_at") and st.session_state.pop("govmap_holders_bg_notice", None):
        st.success(
            f"Individuals fill finished · scanned {int(bg.get('scanned') or 0):,}."
        )
    if bits:
        st.caption(
            " · ".join(bits)
            + " — fill starts automatically in the background until done."
        )


def render_governance_map(*, show_title: bool = True) -> None:
    init_governance_db()
    if show_title:
        st.markdown("### Governance Map")

    # Fixed defaults (filters UI removed): DIN-only, min 2 boards.
    min_boards = 2

    ticker_markets = map_company_ticker_markets(min_boards=int(min_boards))
    missing = missing_profile_tickers(ticker_markets)
    map_tickers = sorted(
        {safe_str(t).upper() for t, _ in ticker_markets if safe_str(t)}
    )
    missing_holders = missing_public_holder_tickers(map_tickers)
    bg = individual_holders_background_status()
    bg_running = bool(bg.get("running"))

    # Auto-start background fill whenever map opens with missing holders,
    # unless the user pressed Stop this session.
    if (
        missing_holders
        and not bg_running
        and not st.session_state.get("govmap_holders_bg_stopped")
    ):
        if start_individual_holders_background(
            missing_holders,
            batch_size=_HOLDER_BG_BATCH,
        ):
            st.session_state["govmap_holders_bg_notice"] = True
            bg = individual_holders_background_status()
            bg_running = bool(bg.get("running"))

    stats = governance_stats()
    with st.expander("Stats & fill (open / hide)", expanded=False):
        st.caption(
            "**DIN-backed** directors on **2+** boards · "
            "**By company** = shared board · **By role** = same title across cos · "
            "**By holder** = public individuals ≥1%."
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

        fill_cols = st.columns([1, 1, 1, 2])
        with fill_cols[0]:
            if st.button(
                f"Fill missing about/web ({len(missing)})",
                width="stretch",
                disabled=not missing,
                help="Pull website + about from screener.in for companies still blank (batched).",
            ):
                with st.spinner(
                    f"Fetching profiles for up to {min(120, len(missing))} companies…"
                ):
                    n = hydrate_missing_profiles(
                        ticker_markets, max_fetch=min(120, len(missing) or 0)
                    )
                st.success(f"Filled {n} profile(s).") if n else st.info(
                    "No new profiles fetched."
                )
                st.rerun()
        with fill_cols[1]:
            if st.button(
                "Stop fill",
                width="stretch",
                disabled=not bg_running,
                help="Stop the background individuals fill (won’t auto-restart until Resume).",
            ):
                stop_individual_holders_background()
                st.session_state["govmap_holders_bg_stopped"] = True
                st.rerun()
        with fill_cols[2]:
            if st.button(
                "Save scanned data",
                width="stretch",
                help="Export holders / scan log / shareholding quarters from SQLite to data/*.csv",
            ):
                counts = export_scanned_shareholding_data()
                st.success(
                    f"Saved CSV · holders {counts['holders']:,} · "
                    f"scans {counts['scans']:,} · quarters {counts['quarters']:,}"
                )
        with fill_cols[3]:
            if missing and not bg_running:
                st.caption(f"**{len(missing):,}** missing about/web")
            if (
                st.session_state.get("govmap_holders_bg_stopped")
                and missing_holders
                and not bg_running
            ):
                if st.button("Resume individuals fill", width="stretch"):
                    st.session_state.pop("govmap_holders_bg_stopped", None)
                    st.rerun()
            poll = getattr(st, "fragment", None)
            if poll is not None and bg_running:

                @poll(run_every=timedelta(seconds=5))
                def _poll_holder_bg() -> None:
                    _holder_bg_caption(map_tickers)

                _poll_holder_bg()
            else:
                _holder_bg_caption(map_tickers)

    # Slim status line outside expander so fill progress stays visible when hidden.
    if bg_running:
        scanned = int(bg.get("scanned") or 0)
        pending_now = int(bg.get("pending_now") or len(missing_holders))
        last = safe_str(bg.get("last_ticker")) or "…"
        st.caption(
            f"Filling individuals · **{scanned:,}** done · **{pending_now:,}** left · `{last}`"
        )

    # While background fill runs, avoid competing NSE hydrate on map build.
    holder_hydrate_max = 0 if bg_running else 25

    with st.spinner("Building governance map…"):
        rows = build_governance_map_rows(
            min_boards=int(min_boards),
            hydrate_profiles=True,
            hydrate_max=60,
            hydrate_mcaps=True,
            hydrate_mcap_max=40,
            hydrate_public_holders=not bg_running,
            hydrate_public_holder_max=holder_hydrate_max,
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
        "DIN only · Cap · Holdings · By holder"
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
