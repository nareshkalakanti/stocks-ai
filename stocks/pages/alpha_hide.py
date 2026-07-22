"""Alpha Hide — SARVADA-style multi-bagger discovery screen."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    ALPHA_HIDE_CACHE_HOURS,
    INDIA_STOCKS_DATASET,
    cap_tier_id_from_label,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.listings.stocks_data import load_india_stocks
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.scan_toolbar import (
    COMPACT_SCAN_BTN_COL_WIDTH,
    base_scan_extra_widths,
    inject_scan_toolbar_css,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.scan_universe import resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.strategies.alpha_hide.html import (
    alpha_hide_iframe_height,
    build_alpha_hide_html,
)
from stocks.strategies.alpha_hide.service import (
    prepare_alpha_hide_universe,
    run_alpha_hide_scan,
)
from stocks.strategies.alpha_hide.strategy import (
    alpha_hide_caption,
    format_alpha_hide_export_df,
)


def _inject_css() -> None:
    if st.session_state.get("_alphahide_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_alphahide_scan_css"] = True


def _filter_key(filters, *, cap_tier_id: str, holdings_industries_only: bool) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        holdings_industries_only,
    )


def render_alpha_hide(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### Alpha Hide")
    st.caption(alpha_hide_caption())

    if "alphahide_cap_tier" not in st.session_state:
        st.session_state["alphahide_cap_tier"] = "Alpha Hide (50–1,000 Cr)"

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="alphahide",
            cap_tier_key="alphahide_cap_tier",
            holdings_key="alphahide_holdings_industries_only",
        )
        cap_tier_id = resolve_cap_tier_id(
            filters.market, cap_tier_id_from_label(cap_tier_label_ui)
        )
        filtered = apply_stock_filters(stocks, filters)
        applied = apply_holdings_industries_if_checked(
            filtered, enabled=holdings_industries_only
        )
        if applied is None:
            return
        filtered, _note = applied

        filter_key = _filter_key(
            filters,
            cap_tier_id=cap_tier_id,
            holdings_industries_only=holdings_industries_only,
        )
        if st.session_state.get("alphahide_filter_key") != filter_key:
            st.session_state.alphahide_filter_key = filter_key
            st.session_state.pop("alphahide_candidates", None)

        universe, _, _ = prepare_alpha_hide_universe(
            filtered, cap_tier_id=cap_tier_id
        )

        with row[5]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                width="stretch",
                key="alphahide_scan",
                help=(
                    "SARVADA-style Phase I/II screen with 5 ingredient gates "
                    f"(cache hint ≤ {ALPHA_HIDE_CACHE_HOURS}h)."
                ),
            )

    if run_clicked:
        if universe.empty:
            st.warning(
                "No stocks in Alpha Hide band (50–1,000 Cr) for current filters."
            )
            return

        progress = st.progress(0, text="Alpha Hide — loading…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Alpha Hide {done:,}/{total:,}…",
            )

        try:
            result = run_alpha_hide_scan(
                universe,
                progress_callback=_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Alpha Hide scan failed: {exc}")
            return
        progress.empty()

        candidates_df = result.get("candidates")
        st.session_state.alphahide_candidates = candidates_df
        scanned = int(result.get("scanned") or 0)
        with_data = int(result.get("with_data") or 0)
        n_pass = (
            len(candidates_df)
            if isinstance(candidates_df, pd.DataFrame)
            else 0
        )
        st.caption(
            f"Scanned **{scanned:,}** · fundamentals **{with_data:,}** · "
            f"**{n_pass:,}** passed ingredient gates."
        )

    candidates = st.session_state.get("alphahide_candidates")
    if candidates is None:
        st.caption(
            "Set filters, then **Scan** (defaults to 50–1,000 Cr). "
            "Inspired by Raas Capital SARVADA / Where Alpha Hides."
        )
        return

    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        st.caption(
            "No names passed (need Valuation + Growth and ≥3 ingredients). "
            "Try widening sector filters or filling shareholding for Promoter."
        )
        return

    embed_html = build_alpha_hide_html(candidates, standalone=False)
    embed_html_iframe(embed_html, height=alpha_hide_iframe_height(len(candidates)))

    export = format_alpha_hide_export_df(candidates)
    st.download_button(
        "Download CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="alpha_hide.csv",
        mime="text/csv",
        key="alphahide_csv",
    )
