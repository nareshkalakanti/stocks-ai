"""100X Formula scan page — Strategy tab."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import FORMULA_100X_MAX_WORKERS, INDIA_STOCKS_DATASET, cap_tier_id_from_label
from stocks.dashboards.report_html import embed_html_iframe
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.scan_toolbar import (
    COMPACT_SCAN_BTN_COL_WIDTH,
    WORKERS_COL_WIDTH,
    base_scan_extra_widths,
    inject_scan_toolbar_css,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.scan_universe import cap_tier_min_mcap_cr, resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.listings.stocks_data import load_india_stocks
from stocks.strategies.formula_100x.html import build_100x_dashboard_html, formula_100x_iframe_height
from stocks.strategies.formula_100x.service import prepare_100x_universe, run_100x_scan


def render_100x(*, show_title: bool = True) -> None:
    inject_scan_toolbar_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### 100X Formula")

    with scan_toolbar_row(
        *base_scan_extra_widths(WORKERS_COL_WIDTH, COMPACT_SCAN_BTN_COL_WIDTH)
    ) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="x100",
            cap_tier_key="x100_cap_tier",
            holdings_key="x100_holdings_industries_only",
        )
        cap_tier_id = resolve_cap_tier_id(filters.market, cap_tier_id_from_label(cap_tier_label_ui))
        min_mcap_cr = cap_tier_min_mcap_cr(cap_tier_id)
        filtered = apply_stock_filters(stocks, filters)
        applied = apply_holdings_industries_if_checked(
            filtered, enabled=holdings_industries_only
        )
        if applied is None:
            return
        filtered, _note = applied

        with row[5]:
            st.number_input(
                "Conc",
                min_value=1,
                max_value=32,
                value=min(FORMULA_100X_MAX_WORKERS, 16),
                step=1,
                key="x100_workers",
                help="Parallel yfinance workers.",
            )
        with row[6]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                use_container_width=True,
                key="x100_scan",
            )

    if not run_clicked:
        cached = st.session_state.get("x100_results")
        if cached is None or (isinstance(cached, pd.DataFrame) and cached.empty):
            st.caption(
                "Cash-flow quality screen: **rising CFO · CFO/EBIT > 60% · "
                "EBT/capital > 12% · CFO/mcap > 15%**. Set filters and click **Scan**."
            )
            return
        results = cached
    else:
        with st.spinner("Preparing universe..."):
            universe, cap_excluded, mcap_excluded = prepare_100x_universe(
                filtered,
                cap_tier_id=cap_tier_id,
            )
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        workers = int(st.session_state.get("x100_workers") or FORMULA_100X_MAX_WORKERS)
        progress = st.progress(0, text="Running 100X scan...")
        try:

            def _progress(done: int, total: int) -> None:
                progress.progress(done / max(total, 1), text=f"100X {done}/{total}...")

            results = run_100x_scan(
                universe,
                min_mcap_cr=min_mcap_cr,
                max_workers=workers,
                progress_callback=_progress,
            )
        finally:
            progress.empty()

        if results.empty:
            st.warning("No 100X data returned (missing annual statements on Yahoo).")
            return

        st.session_state.x100_results = results
        if cap_excluded or mcap_excluded:
            st.caption(
                f"Excluded **{cap_excluded + mcap_excluded:,}** below cap tier · "
                f"**{len(results):,}** with 100X metrics."
            )

    pass_n = int((results["criteria_score"] >= 4).sum()) if "criteria_score" in results.columns else 0
    embed_html = build_100x_dashboard_html(results, title="100X Formula", standalone=False)
    st.caption(
        f"**{len(results):,}** stocks · **{pass_n:,}** pass 4/4 · "
        f"**Show** pills filter the table · **click a row** for criteria breakdown."
    )
    embed_html_iframe(embed_html, height=formula_100x_iframe_height(len(results)))

    st.download_button(
        "Download 100X CSV",
        data=results.to_csv(index=False).encode("utf-8"),
        file_name="formula_100x.csv",
        mime="text/csv",
        key="download_x100_csv",
    )
