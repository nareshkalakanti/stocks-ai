"""Inst Entry — micro deep value + institutional shareholding trigger."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    INST_ENTRY_CACHE_HOURS,
    INST_ENTRY_REQUIRE_SIGNAL,
    cap_tier_id_from_label,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.listings.stocks_data import load_india_stocks
from stocks.scans.scan_toolbar import (
    COMPACT_SCAN_BTN_COL_WIDTH,
    base_scan_extra_widths,
    inject_scan_toolbar_css,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.scan_universe import resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.strategies.inst_entry.html import (
    build_inst_entry_html,
    inst_entry_iframe_height,
)
from stocks.strategies.inst_entry.service import (
    prepare_inst_entry_universe,
    run_inst_entry_scan,
)
from stocks.strategies.inst_entry.strategy import (
    format_inst_entry_export_df,
    inst_entry_caption,
)


def _inject_css() -> None:
    if st.session_state.get("_instentry_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_instentry_scan_css"] = True


def _filter_key(filters, *, cap_tier_id: str) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
    )


def render_inst_entry(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### Inst Entry")
    st.caption(inst_entry_caption())

    if "instentry_cap_tier" not in st.session_state:
        st.session_state["instentry_cap_tier"] = "Inst Entry (20–100 Cr)"

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui = render_base_scan_filters(
            stocks,
            row,
            key_prefix="instentry",
            cap_tier_key="instentry_cap_tier",
        )
        cap_tier_id = resolve_cap_tier_id(
            filters.market, cap_tier_id_from_label(cap_tier_label_ui)
        )
        filtered = apply_stock_filters(stocks, filters)

        filter_key = _filter_key(
            filters,
            cap_tier_id=cap_tier_id,
            )
        if st.session_state.get("instentry_filter_key") != filter_key:
            st.session_state.instentry_filter_key = filter_key
            st.session_state.pop("instentry_candidates", None)
            st.session_state.pop("instentry_watchlist", None)

        universe, _, _ = prepare_inst_entry_universe(
            filtered, cap_tier_id=cap_tier_id
        )

        with row[4]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                width="stretch",
                key="instentry_scan",
                help=(
                    "Quant gates then DII/FII shareholding trigger "
                    f"(cache hint ≤ {INST_ENTRY_CACHE_HOURS}h)."
                ),
            )

    if run_clicked:
        if universe.empty:
            st.warning(
                "No stocks in the Inst Entry band (20–100 Cr) for current filters."
            )
            return

        progress = st.progress(0, text="Inst Entry — loading…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Inst Entry {done:,}/{total:,}…",
            )

        try:
            result = run_inst_entry_scan(
                universe,
                progress_callback=_progress,
                require_signal=INST_ENTRY_REQUIRE_SIGNAL,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Inst Entry scan failed: {exc}")
            return
        progress.empty()

        candidates_df = result.get("candidates")
        watchlist_df = result.get("watchlist")
        st.session_state.instentry_candidates = candidates_df
        st.session_state.instentry_watchlist = watchlist_df
        scanned = int(result.get("scanned") or 0)
        with_data = int(result.get("with_data") or 0)
        n_sig = (
            len(candidates_df) if isinstance(candidates_df, pd.DataFrame) else 0
        )
        n_watch = (
            len(watchlist_df) if isinstance(watchlist_df, pd.DataFrame) else 0
        )
        st.caption(
            f"Scanned **{scanned:,}** · quant data **{with_data:,}** · "
            f"quant watchlist **{n_watch:,}** · "
            f"**{n_sig:,}** with institutional entry trigger."
        )

    candidates = st.session_state.get("instentry_candidates")
    if candidates is None:
        st.caption(
            "Set filters, then **Scan**. Defaults to 20–100 Cr. "
            "Optional seed: `data/shareholding_seed.csv`. "
            "Shareholding loads from NSE filings (not screener.in)."
        )
        return

    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        watch = st.session_state.get("instentry_watchlist")
        n_watch = len(watch) if isinstance(watch, pd.DataFrame) else 0
        st.caption(
            f"No institutional-entry signals "
            f"(quant watchlist had **{n_watch:,}** names). "
            "Shareholding comes from NSE XBRL (auto on scan) or "
            "`data/shareholding_seed.csv` — then re-scan."
        )
        if isinstance(watch, pd.DataFrame) and not watch.empty:
            st.markdown("##### Quant watchlist (no inst trigger yet)")
            embed_html = build_inst_entry_html(watch, standalone=False)
            embed_html_iframe(embed_html, height=inst_entry_iframe_height(len(watch)))
        return

    embed_html = build_inst_entry_html(candidates, standalone=False)
    embed_html_iframe(embed_html, height=inst_entry_iframe_height(len(candidates)))

    export = format_inst_entry_export_df(candidates)
    st.download_button(
        "Download CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="inst_entry.csv",
        mime="text/csv",
        key="instentry_csv",
    )
