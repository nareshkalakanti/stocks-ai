"""Watching — Early Edge curated watchlist (HTML board with Cap / Sector filters)."""

from __future__ import annotations

import streamlit as st

from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.shared.early_edge import (
    EARLY_EDGE_PLAYLIST_LABEL,
    enrich_early_edge_display,
    hydrate_early_edge_missing,
    load_early_edge_df,
    resolve_early_edge_queries,
    seed_early_edge,
)
from stocks.shared.early_edge_html import build_early_edge_html, early_edge_iframe_height


def render_watching(*, show_title: bool = True) -> None:
    if show_title:
        st.markdown("### Watching")
    st.caption(
        f"**Early Edge** curated list · Edge tag on Strategy / PEAD / GovMap · "
        f"Market = **{EARLY_EDGE_PLAYLIST_LABEL}** on all scans (like Negen / Holdings)."
    )

    _c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
    with c2:
        fill = st.button(
            "Fill missing from web",
            use_container_width=True,
            help="Fetch missing mcap / website / sector from screener + Yahoo and save to DB.",
        )
    with c3:
        reseed = st.button(
            "Re-seed from names",
            type="primary",
            use_container_width=True,
            help="Replace DB list from the built-in Early Edge name list.",
        )
    if reseed:
        info = seed_early_edge(force=True)
        unresolved = info.get("unresolved") or []
        st.success(f"Early Edge · **{info.get('written', 0)}** tickers in DB")
        if unresolved:
            st.warning("Unresolved names: " + ", ".join(unresolved))

    raw = load_early_edge_df()
    _, unresolved = resolve_early_edge_queries()
    if unresolved and raw.empty:
        st.info("No tickers yet — click **Re-seed from names**.")
        return
    if raw is None or raw.empty:
        st.caption("No Early Edge tickers in DB.")
        return

    if fill:
        progress = st.progress(0, text="Early Edge — filling missing mcap / website / sector…")

        def _progress(done: int, total: int, ticker: str) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            label = f" · {ticker}" if ticker else ""
            progress.progress(
                min(done / total, 1.0),
                text=f"Filling gaps {done:,}/{total:,}{label}…",
            )

        stats = hydrate_early_edge_missing(raw, progress_callback=_progress)
        progress.empty()
        st.success(
            f"Filled · tried **{stats['tried']}** · "
            f"mcap **{stats['mcap']}** · website **{stats['website']}** · "
            f"sector **{stats['sector']}** (saved to DB)"
        )

    view = enrich_early_edge_display(raw)
    with_sector = int(view["sector"].astype(str).str.strip().ne("").sum()) if "sector" in view.columns else 0
    with_mcap = (
        int(view["market_cap_cr"].notna().sum()) if "market_cap_cr" in view.columns else 0
    )
    with_web = (
        int(view["website"].astype(str).str.strip().ne("").sum())
        if "website" in view.columns
        else 0
    )
    with_price = int(view["price"].notna().sum()) if "price" in view.columns else 0
    st.caption(
        f"{len(view):,} stocks · price **{with_price}** · sector **{with_sector}** · "
        f"mcap **{with_mcap}** · web **{with_web}** · playlist **{EARLY_EDGE_PLAYLIST_LABEL}** · "
        f"filter Cap / Sector in the board"
    )

    html = build_early_edge_html(view, title="Early Edge", standalone=False)
    embed_html_iframe(
        html,
        height=early_edge_iframe_height(len(view)),
        key="early_edge_watching",
        static_stem=None,
    )
