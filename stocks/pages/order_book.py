"""Order Book — NSE order/contract inflow by company."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    ORDER_INFLOW_MAX_WORKERS,
    STRATEGY_MAX_WORKERS_CAP,
    cap_tier_id_from_label,
)
from stocks.dashboards.order_book_html import (
    build_order_book_html,
    flat_order_count,
    order_book_iframe_height,
)
from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.listings.stocks_data import load_india_stocks
from stocks.market.order_inflow import fy_label, scan_order_inflow_universe
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.scan_toolbar import (
    COMPACT_SCAN_BTN_COL_WIDTH,
    WORKERS_COL_WIDTH,
    base_scan_extra_widths,
    inject_scan_toolbar_css,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.scan_universe import resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.strategies.pead.service import prepare_pead_universe


def _inject_css() -> None:
    if st.session_state.get("_order_book_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_order_book_css"] = True


def _filter_key(filters, *, cap_tier_id: str, holdings_industries_only: bool) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        holdings_industries_only,
    )


def render_order_book() -> None:
    _inject_css()
    st.markdown("### Order Book")
    cur_fy = fy_label(pd.Timestamp.now()) or "current FY"
    st.caption(
        f"NSE order disclosures · **All Orders** table with filters · **By Company** tab for summary · "
        f"₹ Cr = crore · **{cur_fy}** FY bucket on company view"
    )

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    with scan_toolbar_row(
        *base_scan_extra_widths(WORKERS_COL_WIDTH, 0.55, COMPACT_SCAN_BTN_COL_WIDTH)
    ) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="orderbook",
            cap_tier_key="orderbook_cap_tier",
            holdings_key="orderbook_holdings_industries_only",
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
        if st.session_state.get("orderbook_filter_key") != filter_key:
            st.session_state.orderbook_filter_key = filter_key
            st.session_state.pop("orderbook_results", None)

        with row[5]:
            max_workers = st.number_input(
                "Workers",
                min_value=1,
                max_value=min(STRATEGY_MAX_WORKERS_CAP, 16),
                value=min(ORDER_INFLOW_MAX_WORKERS, 16),
                key="orderbook_max_workers",
            )
        with row[6]:
            refresh = st.checkbox("Refresh NSE", value=False, key="orderbook_refresh")
        with row[7]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                use_container_width=True,
                key="orderbook_scan",
            )

    universe, _cap_ex, _mcap_ex = prepare_pead_universe(
        filtered, cap_tier_id=cap_tier_id
    )

    if run_clicked:
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        progress = st.progress(0, text="Scanning NSE order disclosures…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Order book {done:,}/{total:,}…",
            )

        try:
            results = scan_order_inflow_universe(
                universe,
                max_workers=int(max_workers),
                refresh=refresh,
                progress_callback=_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Order book scan failed: {exc}")
            return
        progress.empty()

        if results.empty:
            st.session_state.pop("orderbook_results", None)
            st.warning(
                "No order disclosures found in the lookback window "
                "(try Refresh NSE or widen universe)."
            )
            return

        st.session_state.orderbook_results = results
        st.caption(
            f"**{len(results):,}** companies with orders · scanned **{len(universe):,}** tickers"
        )

    results = st.session_state.get("orderbook_results")
    if results is None:
        st.info("Set filters, then click **Scan** to load order inflow from NSE.")
        return
    if not isinstance(results, pd.DataFrame) or results.empty:
        st.caption("No order book results loaded.")
        return

    embed_html = build_order_book_html(
        results,
        title="All Orders",
        standalone=False,
    )
    n_orders = flat_order_count(results)
    embed_html_iframe(embed_html, height=order_book_iframe_height(n_orders))

    export_cols = [
        "ticker",
        "name",
        "order_count",
        "total_cr",
        "current_fy_cr",
        "growth_pct",
    ]
    present = [c for c in export_cols if c in results.columns]
    st.download_button(
        "Download summary CSV",
        results[present].to_csv(index=False).encode("utf-8"),
        file_name="order_book_summary.csv",
        mime="text/csv",
        key="orderbook_csv",
    )
