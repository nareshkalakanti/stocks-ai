"""Watching — curated lists: Early Edge, Holdings, Negen, Niveshaay, NSE, NSE SME."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.text_utils import safe_str
from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.listings.stocks_data import apply_market_column_filter, load_india_stocks
from stocks.scans.holdings_playlist import HOLDINGS_PLAYLIST_LABEL
from stocks.scans.list_playlist import (
    MARKET_WATCHING_LIST_LABELS,
    WATCHING_COMMON_LIST_LABELS,
    WATCHING_LIST_LABELS,
    format_watching_list_option,
    is_market_watching_list,
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
    watching_gap_rows,
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

from stocks.shared.watching_common_html import build_watching_common_html

_WATCHING_LIST_KEY = "watching_list"
_COMMON_TILES_MAX = 12
_BOARD_PAGE_SIZE = 100
_PAGINATED_LISTS = frozenset(MARKET_WATCHING_LIST_LABELS)

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
    "NSE": "All **NSE mainboard** listings.",
    "NSE SME": "All **NSE Emerge / SME** listings.",
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
    if is_market_watching_list(selected):
        stocks = load_india_stocks()
        df = apply_market_column_filter(stocks, selected)
        if df is None or df.empty:
            return pd.DataFrame()
        sort_col = "ticker" if "ticker" in df.columns else df.columns[0]
        return df.sort_values(sort_col, ascending=True).reset_index(drop=True)
    return pd.DataFrame()


def _list_membership() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for label in WATCHING_COMMON_LIST_LABELS:
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
    for label in WATCHING_COMMON_LIST_LABELS:
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

    shown = len(view)
    count_label = f"showing {shown} of {total}" if total > shown else str(shown)
    with st.expander(f"On 2+ lists · {count_label}", expanded=False):
        gaps = watching_gap_counts(view)
        html = build_watching_common_html(
            view,
            total_common=total,
            limit=_COMMON_TILES_MAX,
            gap_counts=gaps,
            include_heading=False,
        )
        if html:
            st.markdown(html, unsafe_allow_html=True)


def _board_stats_lines(view) -> list[str]:
    gaps = watching_gap_counts(view)
    with_sector = gaps["total"] - gaps["sector"]
    with_sub = gaps["total"] - int(gaps.get("sub_sector") or 0)
    with_mcap = gaps["total"] - gaps["mcap"]
    with_web = gaps["total"] - gaps["web"]
    with_price = gaps["total"] - gaps["price"]
    lines = [
        f"{gaps['total']:,} stocks · price **{with_price}** · sector **{with_sector}** · "
        f"sub-sector **{with_sub}** · mcap **{with_mcap}** · web **{with_web}** · "
        f"filter Cap / SME / Sector in the board"
    ]
    gap_txt = format_watching_gaps(gaps)
    if gap_txt:
        lines.append(gap_txt)
    return lines


def _render_list_stats(
    *,
    list_caption: str,
    view,
    list_label: str = "",
) -> None:
    lines = [list_caption, *_board_stats_lines(view)]
    gaps = watching_gap_counts(view)
    missing = gaps.get("any_rows") or 0
    label = "List stats"
    if missing:
        label = f"List stats · {missing} need fill"
    with st.expander(label, expanded=bool(missing)):
        for line in lines:
            st.caption(line)
        if missing:
            gap_df = watching_gap_rows(view)
            show_cols = [
                c
                for c in (
                    "ticker",
                    "name",
                    "market",
                    "missing",
                    "sector",
                    "sub_sector",
                    "market_cap_cr",
                    "website",
                    "price",
                )
                if c in gap_df.columns
            ]
            st.dataframe(gap_df[show_cols], width="stretch", hide_index=True)
            slug = safe_str(list_label).lower().replace(" ", "_") or "watching"
            st.download_button(
                f"Download missing CSV · {missing}",
                data=gap_df[show_cols].to_csv(index=False).encode("utf-8"),
                file_name=f"watching_missing_{slug}.csv",
                mime="text/csv",
                key=f"watching_missing_csv_{slug}",
                help="Tickers still missing price, sector, sub-sector, mcap, and/or website.",
            )


def _render_watching_board(
    view,
    *,
    title: str,
    iframe_key: str,
    client_page_size: int | None = None,
    list_caption: str = "",
) -> None:
    if view is None or view.empty:
        st.caption("No tickers in this list yet.")
        return
    if list_caption:
        _render_list_stats(list_caption=list_caption, view=view, list_label=title)
    else:
        with st.expander("List stats", expanded=False):
            for line in _board_stats_lines(view):
                st.caption(line)
    display_rows = len(view)
    if client_page_size:
        display_rows = min(display_rows, client_page_size)
    html = build_early_edge_html(
        view,
        title=title,
        standalone=False,
        client_page_size=client_page_size,
    )
    embed_html_iframe(
        html,
        height=early_edge_iframe_height(display_rows),
        key=iframe_key,
    )


def _run_fill_missing(
    raw: pd.DataFrame,
    *,
    list_label: str,
    max_tried: int | None = None,
) -> None:
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

    stats = hydrate_watching_missing(
        raw,
        progress_callback=_progress,
        max_tried=max_tried,
    )
    progress.empty()
    st.success(
        f"Filled · tried **{stats['tried']}** · "
        f"price **{stats.get('price', 0)}** · "
        f"mcap **{stats['mcap']}** · website **{stats['website']}** · "
        f"sector/sub-sector **{stats['sector']}** (saved to DB)"
    )


def _enrich_for_list(selected: str, raw: pd.DataFrame) -> pd.DataFrame:
    bulk = selected in _PAGINATED_LISTS
    if selected == EARLY_EDGE_PLAYLIST_LABEL:
        return enrich_early_edge_display(raw)
    if selected == HOLDINGS_PLAYLIST_LABEL:
        return enrich_watching_board(
            raw,
            list_tag="Holding",
            is_holding=True,
            fetch_live_prices=not bulk,
        )
    return enrich_watching_board(
        raw,
        list_tag=selected,
        fetch_live_prices=not bulk,
    )


def _render_early_edge_actions() -> bool:
    """Early Edge–only controls. Returns False if board should not render yet."""
    if st.button(
        "Re-seed from names",
        type="primary",
        width="content",
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
            add_clicked = st.button("Add holding", type="primary", width="stretch")

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
            if st.button("Remove selected", width="stretch", disabled=not pick):
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


def _render_selected_list(selected: str) -> None:
    if selected in _LABEL_TO_FUND_KEY:
        meta = FUND_WATCHLIST_DEFS.get(_LABEL_TO_FUND_KEY[selected]) or {}
        inv = ", ".join(meta.get("investor_names") or [])
        extra = f" · {inv}" if inv else ""
        list_caption = _LIST_CAPTIONS.get(selected, f"**{selected}**") + extra
    else:
        list_caption = _LIST_CAPTIONS.get(selected, f"**{selected}**")

    if selected == EARLY_EDGE_PLAYLIST_LABEL and not _render_early_edge_actions():
        return
    if selected == HOLDINGS_PLAYLIST_LABEL and not _render_holdings_actions():
        return

    raw = _raw_for_list(selected)
    if raw is None or raw.empty:
        st.info("No tickers in this list yet.")
        return

    view = _enrich_for_list(selected, raw)
    page_size = _BOARD_PAGE_SIZE if selected in _PAGINATED_LISTS else None
    iframe_key = f"watching_board_{selected.lower().replace(' ', '_')}"
    _render_watching_board(
        view,
        title=selected,
        iframe_key=iframe_key,
        client_page_size=page_size,
        list_caption=list_caption,
    )


def render_watching(*, show_title: bool = True) -> None:
    if show_title:
        st.markdown("### Watching")

    list_opts = list(WATCHING_LIST_LABELS)
    if _WATCHING_LIST_KEY not in st.session_state or st.session_state[_WATCHING_LIST_KEY] not in list_opts:
        st.session_state[_WATCHING_LIST_KEY] = EARLY_EDGE_PLAYLIST_LABEL

    inject_scan_toolbar_css()
    with st.container(border=True):
        row = st.columns([1.2, 1.0], vertical_alignment="bottom", gap="small")
        with row[0]:
            selected = st.selectbox(
                "List",
                list_opts,
                key=_WATCHING_LIST_KEY,
                format_func=format_watching_list_option,
                help=(
                    "Early Edge, Holdings, Negen, Niveshaay, NSE, NSE SME — "
                    "same board; NSE / SME page with ‹ › inside the table toolbar."
                ),
            )
        with row[1]:
            fill = st.button(
                "Fill missing from web",
                width="stretch",
                help=(
                    "Fetch missing price, mcap, website, sector, and sub-sector "
                    "from screener + Yahoo for every gap in this list. "
                    "Download the gap list from List stats."
                ),
                key="watching_fill",
            )

    _render_common_tiles()

    raw_selected = _raw_for_list(selected)
    if fill:
        if raw_selected is None or raw_selected.empty:
            st.info("Nothing in this list.")
        else:
            bulk = selected in _PAGINATED_LISTS
            preview = enrich_watching_board(
                raw_selected,
                list_tag=selected,
                is_holding=(selected == HOLDINGS_PLAYLIST_LABEL),
                is_edge=(selected == EARLY_EDGE_PLAYLIST_LABEL),
                fetch_live_prices=not bulk,
            )
            gap_df = watching_gap_rows(preview)
            if gap_df.empty:
                st.info("Nothing missing on this list.")
            else:
                gap_tickers = set(gap_df["ticker"].astype(str).str.upper())
                raw_gaps = raw_selected[
                    raw_selected["ticker"].astype(str).str.upper().isin(gap_tickers)
                ].copy()
                st.info(f"Filling **{len(raw_gaps)}** names with gaps…")
                _run_fill_missing(raw_gaps, list_label=selected, max_tried=None)

    _render_selected_list(selected)
