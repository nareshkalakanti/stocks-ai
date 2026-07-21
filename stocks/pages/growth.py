"""Growth strategy — quantitative yfinance screen."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    GROWTH_CACHE_HOURS,
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
from stocks.scans.scan_universe import cap_tier_min_mcap_cr, resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.strategies.growth.html import build_growth_html, growth_iframe_height
from stocks.strategies.growth.service import prepare_pead_universe, run_growth_scan
from stocks.strategies.growth.strategy import format_growth_export_df, growth_caption


def _inject_css() -> None:
    if st.session_state.get("_growth_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_growth_scan_css"] = True


def _filter_key(filters, *, cap_tier_id: str, holdings_industries_only: bool) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        holdings_industries_only,
    )


def render_growth(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### Growth")
    st.caption(growth_caption())

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="growth",
            cap_tier_key="growth_cap_tier",
            holdings_key="growth_holdings_industries_only",
        )
        cap_tier_id = resolve_cap_tier_id(
            filters.market, cap_tier_id_from_label(cap_tier_label_ui)
        )
        min_mcap_cr = cap_tier_min_mcap_cr(cap_tier_id)
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
        if st.session_state.get("growth_filter_key") != filter_key:
            st.session_state.growth_filter_key = filter_key
            st.session_state.pop("growth_candidates", None)

        universe, _, _ = prepare_pead_universe(filtered, cap_tier_id=cap_tier_id)

        with row[5]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                width="stretch",
                key="growth_scan",
                help=(
                    "Fetch annual statements via yfinance and apply growth "
                    f"quantitative filters (cache hint ≤ {GROWTH_CACHE_HOURS}h for related fundamentals)."
                ),
            )

    if run_clicked:
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        progress = st.progress(0, text="Growth screen — loading…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Growth screen {done:,}/{total:,}…",
            )

        try:
            result = run_growth_scan(
                universe,
                progress_callback=_progress,
                min_mcap_cr=min_mcap_cr,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Growth scan failed: {exc}")
            return
        progress.empty()

        candidates_df = result.get("candidates")
        st.session_state.growth_candidates = candidates_df
        scanned = int(result.get("scanned") or 0)
        with_data = int(result.get("with_data") or 0)
        n_pass = (
            len(candidates_df)
            if isinstance(candidates_df, pd.DataFrame)
            else 0
        )
        st.caption(
            f"Scanned **{scanned:,}** · fundamentals for **{with_data:,}** · "
            f"**{n_pass:,}** passed quantitative checks."
        )

    candidates = st.session_state.get("growth_candidates")
    if candidates is None:
        st.caption("Set filters, then click **Scan**.")
        return

    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        st.caption(
            "No names passed the growth quantitative filters "
            "(try widening filters or a lower market-cap floor)."
        )
        return

    embed_html = build_growth_html(candidates, standalone=False)
    embed_html_iframe(embed_html, height=growth_iframe_height(len(candidates)))

    export = format_growth_export_df(candidates)
    st.download_button(
        "Download CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="growth_strategy.csv",
        mime="text/csv",
        key="growth_csv",
    )
