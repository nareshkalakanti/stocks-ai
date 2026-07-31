"""Watching — curated lists: Early Edge, Holdings, Negen, Niveshaay."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.text_utils import safe_str
from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.listings.stocks_data import load_india_stocks
from stocks.scans.holdings_playlist import HOLDINGS_PLAYLIST_LABEL
from stocks.scans.list_playlist import (
    WATCHING_LIST_LABELS,
    format_watching_list_option,
)
from stocks.scans.scan_toolbar import inject_scan_toolbar_css
from stocks.shared.early_edge import (
    EARLY_EDGE_PLAYLIST_LABEL,
    enrich_early_edge_display,
    enrich_watching_board,
    hydrate_watching_missing,
    load_early_edge_df,
    resolve_early_edge_queries,
    seed_early_edge,
    watching_gap_counts,
    format_watching_gaps,
)
from stocks.shared.early_edge_html import build_early_edge_html, early_edge_iframe_height
from stocks.shared.fund_watchlists import (
    FUND_WATCHLIST_DEFS,
    NEGEN_PLAYLIST_LABEL,
    NIVESHAAY_PLAYLIST_LABEL,
    load_fund_watchlist_df,
)
from stocks.shared.portfolio import (
    add_holdings,
    load_holdings,
    remove_holdings,
    seed_default_holdings,
)

from stocks.shared.watching_common_html import (
    build_watching_common_html,
    watching_common_iframe_height,
)

_WATCHING_LIST_KEY = "watching_list"
_COMMON_TILES_MAX = 12

_LABEL_TO_FUND_KEY = {
    NEGEN_PLAYLIST_LABEL: "negen",
    NIVESHAAY_PLAYLIST_LABEL: "niveshaay",
}

_LIST_CAPTIONS: dict[str, str] = {
    EARLY_EDGE_PLAYLIST_LABEL: (
        f"**Early Edge** curated names · Edge tag on Strategy / PEAD / GovMap · "
        f"Market = **{EARLY_EDGE_PLAYLIST_LABEL}** on scans."
    ),
    HOLDINGS_PLAYLIST_LABEL: (
        "Personal portfolio · **Holding** tag on Strategy reports and Governance Map."
    ),
    NEGEN_PLAYLIST_LABEL: "**Negen** fund watchlist.",
    NIVESHAAY_PLAYLIST_LABEL: "**Niveshaay** fund watchlist.",
}


def _tickers_from_df(df: pd.DataFrame | None) -> set[str]:
    if df is None or df.empty or "ticker" not in df.columns:
        return set()
    return {safe_str(t).upper() for t in df["ticker"] if safe_str(t)}


def _raw_for_list(selected: str) -> pd.DataFrame:
    if selected == EARLY_EDGE_PLAYLIST_LABEL:
        return load_early_edge_df()
    if selected == HOLDINGS_PLAYLIST_LABEL:
        return load_holdings(seed_if_empty=True)
    if selected in _LABEL_TO_FUND_KEY:
        return load_fund_watchlist_df(_LABEL_TO_FUND_KEY[selected])
    return pd.DataFrame()


def _list_membership() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for label in WATCHING_LIST_LABELS:
        for ticker in _tickers_from_df(_raw_for_list(label)):
            out.setdefault(ticker, set()).add(label)
    return out


def _common_stocks() -> list[tuple[str, list[str]]]:
    membership = _list_membership()
    common = [
        (ticker, sorted(lists))
        for ticker, lists in membership.items()
        if len(lists) >= 2
    ]
    common.sort(key=lambda item: (-len(item[1]), item[0]))
    return common


def _lookup_ticker_row(ticker: str) -> dict:
    key = safe_str(ticker).upper()
    for label in WATCHING_LIST_LABELS:
        raw = _raw_for_list(label)
        if raw is None or raw.empty or "ticker" not in raw.columns:
            continue
        match = raw[raw["ticker"].astype(str).str.upper() == key]
        if not match.empty:
            row = match.iloc[0].to_dict()
            row["ticker"] = key
            return row
    return {"ticker": key, "name": key, "market": "NSE"}


def _build_common_enriched(limit: int = _COMMON_TILES_MAX) -> tuple[pd.DataFrame, int]:
    common = _common_stocks()
    if not common:
        return pd.DataFrame(), 0

    total = len(common)
    rows: list[dict] = []
    for ticker, lists in common[:limit]:
        row = _lookup_ticker_row(ticker)
        row["on_lists"] = "|".join(lists)
        rows.append(row)

    if not rows:
        return pd.DataFrame(), total

    lists_map = {safe_str(r["ticker"]).upper(): r["on_lists"] for r in rows}
    enriched = enrich_watching_board(pd.DataFrame(rows))
    enriched["on_lists"] = enriched["ticker"].astype(str).str.upper().map(lists_map).fillna("")
    return enriched, total


def _render_common_tiles() -> None:
    view, total = _build_common_enriched(limit=_COMMON_TILES_MAX)
    if view.empty:
        return

    gaps = watching_gap_counts(view)
    html = build_watching_common_html(
        view,
        total_common=total,
        limit=_COMMON_TILES_MAX,
        gap_counts=gaps,
    )
    if not html:
        return
    embed_html_iframe(
        html,
        height=watching_common_iframe_height(len(view)),
        key="watching_common_tiles",
    )


def _board_stats_caption(view) -> None:
    gaps = watching_gap_counts(view)
    with_sector = gaps["total"] - gaps["sector"]
    with_sub = gaps["total"] - int(gaps.get("sub_sector") or 0)
    with_mcap = gaps["total"] - gaps["mcap"]
    with_web = gaps["total"] - gaps["web"]
    with_price = gaps["total"] - gaps["price"]
    st.caption(
        f"{gaps['total']:,} stocks · price **{with_price}** · sector **{with_sector}** · "
        f"sub-sector **{with_sub}** · mcap **{with_mcap}** · web **{with_web}** · "
        f"filter Cap / Sector in the board"
    )
    gap_txt = format_watching_gaps(gaps)
    if gap_txt:
        st.caption(gap_txt)


def _render_watching_board(view, *, title: str, iframe_key: str) -> None:
    if view is None or view.empty:
        st.caption("No tickers in this list yet.")
        return
    _board_stats_caption(view)
    html = build_early_edge_html(view, title=title, standalone=False)
    embed_html_iframe(
        html,
        height=early_edge_iframe_height(len(view)),
        key=iframe_key,
    )


def _run_fill_missing(raw: pd.DataFrame, *, list_label: str) -> None:
    if raw is None or raw.empty:
        st.warning("No tickers in this list to fill.")
        return
    progress = st.progress(
        0, text=f"{list_label} — filling price / mcap / website / sector / sub-sector…"
    )

    def _progress(done: int, total: int, ticker: str) -> None:
        if total <= 0:
            progress.progress(1.0, text="Done")
            return
        label = f" · {ticker}" if ticker else ""
        progress.progress(
            min(done / total, 1.0),
            text=f"Filling gaps {done:,}/{total:,}{label}…",
        )

    stats = hydrate_watching_missing(raw, progress_callback=_progress)
    progress.empty()
    st.success(
        f"Filled · tried **{stats['tried']}** · "
        f"price **{stats.get('price', 0)}** · "
        f"mcap **{stats['mcap']}** · website **{stats['website']}** · "
        f"sector/sub-sector **{stats['sector']}** (saved to DB)"
    )


def _enrich_for_list(selected: str, raw: pd.DataFrame) -> pd.DataFrame:
    if selected == EARLY_EDGE_PLAYLIST_LABEL:
        return enrich_early_edge_display(raw)
    if selected == HOLDINGS_PLAYLIST_LABEL:
        return enrich_watching_board(raw, list_tag="Holding", is_holding=True)
    return enrich_watching_board(raw, list_tag=selected)


def _render_early_edge_actions() -> bool:
    """Early Edge–only controls. Returns False if board should not render yet."""
    if st.button(
        "Re-seed from names",
        type="primary",
        use_container_width=False,
        help="Replace DB list from the built-in Early Edge name list.",
        key="watching_ee_reseed",
    ):
        info = seed_early_edge(force=True)
        unresolved = info.get("unresolved") or []
        st.success(f"Early Edge · **{info.get('written', 0)}** tickers in DB")
        if unresolved:
            st.warning("Unresolved names: " + ", ".join(unresolved))

    raw = load_early_edge_df()
    _, unresolved = resolve_early_edge_queries()
    if unresolved and raw.empty:
        st.info("No tickers yet — click **Re-seed from names**.")
        return False
    return True


def _render_holdings_actions() -> bool:
    """Holdings add/remove. Returns False if board should not render yet."""
    holdings = load_holdings(seed_if_empty=True)

    with st.expander("Add / remove holding", expanded=False):
        try:
            universe = load_india_stocks()
        except Exception:
            universe = pd.DataFrame()

        add_c1, add_c2, add_c3 = st.columns([2, 1, 1])
        with add_c1:
            ticker_in = st.text_input(
                "Ticker",
                key="watching_holdings_add_ticker",
                placeholder="e.g. INA or AARTECH",
            )
        with add_c2:
            market_in = st.selectbox(
                "Market",
                options=["NSE", "BSE"],
                index=0,
                key="watching_holdings_add_market",
            )
        with add_c3:
            st.write("")
            st.write("")
            add_clicked = st.button("Add holding", type="primary", use_container_width=True)

        if add_clicked:
            ticker = safe_str(ticker_in).upper()
            if not ticker:
                st.warning("Enter a ticker.")
            else:
                market = safe_str(market_in).upper() or "NSE"
                name = None
                if not universe.empty and "ticker" in universe.columns:
                    match = universe[universe["ticker"].astype(str).str.upper() == ticker]
                    if not match.empty:
                        if "market" in match.columns:
                            mkt_match = match[match["market"].astype(str).str.upper() == market]
                            row = (mkt_match if not mkt_match.empty else match).iloc[0]
                        else:
                            row = match.iloc[0]
                        name = safe_str(row.get("name")) or None
                        if "market" in row.index and safe_str(row.get("market")):
                            market = safe_str(row.get("market")).upper() or market
                n = add_holdings([{"ticker": ticker, "market": market, "name": name}])
                if n:
                    st.success(f"Added **{ticker}** ({market}).")
                else:
                    st.warning("Nothing added.")
                st.rerun()

        if not holdings.empty:
            options = sorted(
                {
                    f"{safe_str(r.ticker).upper()}"
                    + (f" — {safe_str(r.name)}" if safe_str(getattr(r, 'name', None)) else "")
                    for r in holdings.itertuples()
                    if safe_str(getattr(r, "ticker", None))
                }
            )
            pick = st.multiselect(
                "Remove holdings",
                options=options,
                key="watching_holdings_remove_pick",
            )
            if st.button("Remove selected", use_container_width=True, disabled=not pick):
                tickers = [safe_str(p.split(" — ")[0]).upper() for p in pick]
                n = remove_holdings(tickers)
                st.success(f"Removed {n} holding(s).") if n else st.info("Nothing removed.")
                st.rerun()

    if holdings.empty:
        st.warning("No holdings in database.")
        if st.button("Load default portfolio", key="watching_holdings_seed"):
            seed_default_holdings(force=True)
            st.rerun()
        return False
    return True


def _render_fund_caption(list_key: str, label: str) -> None:
    meta = FUND_WATCHLIST_DEFS.get(list_key) or {}
    inv = ", ".join(meta.get("investor_names") or [])
    extra = f" · {inv}" if inv else ""
    st.caption(_LIST_CAPTIONS.get(label, f"**{label}**") + extra)


def _render_selected_list(selected: str) -> None:
    caption = _LIST_CAPTIONS.get(selected, f"**{selected}**")
    if selected in _LABEL_TO_FUND_KEY:
        _render_fund_caption(_LABEL_TO_FUND_KEY[selected], selected)
    else:
        st.caption(caption)

    if selected == EARLY_EDGE_PLAYLIST_LABEL and not _render_early_edge_actions():
        return
    if selected == HOLDINGS_PLAYLIST_LABEL and not _render_holdings_actions():
        return

    raw = _raw_for_list(selected)
    if raw is None or raw.empty:
        st.info("No tickers in this list yet.")
        return

    view = _enrich_for_list(selected, raw)
    iframe_key = f"watching_board_{selected.lower().replace(' ', '_')}"
    _render_watching_board(view, title=selected, iframe_key=iframe_key)


def render_watching(*, show_title: bool = True) -> None:
    if show_title:
        st.markdown("### Watching")

    list_opts = list(WATCHING_LIST_LABELS)
    if _WATCHING_LIST_KEY not in st.session_state or st.session_state[_WATCHING_LIST_KEY] not in list_opts:
        st.session_state[_WATCHING_LIST_KEY] = EARLY_EDGE_PLAYLIST_LABEL

    inject_scan_toolbar_css()
    with st.container(border=True):
        row = st.columns([1.05, 1.2], vertical_alignment="bottom", gap="small")
        with row[0]:
            selected = st.selectbox(
                "List",
                list_opts,
                key=_WATCHING_LIST_KEY,
                format_func=format_watching_list_option,
                help="Early Edge, Holdings, Negen, Niveshaay — same board and Fill missing for every list.",
            )
        with row[1]:
            fill = st.button(
                "Fill missing from web",
                use_container_width=True,
                help=(
                    "Fetch missing price, mcap, website, sector, and sub-sector "
                    "from screener + Yahoo for the current list (same as agent fixes)."
                ),
                key="watching_fill",
            )

    raw_selected = _raw_for_list(selected)
    if not raw_selected.empty:
        gap_view = _enrich_for_list(selected, raw_selected)
        gap_line = format_watching_gaps(watching_gap_counts(gap_view))
        if gap_line:
            st.caption(gap_line)

    _render_common_tiles()

    if fill:
        _run_fill_missing(_raw_for_list(selected), list_label=selected)

    _render_selected_list(selected)
