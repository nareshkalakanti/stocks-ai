"""Cash Quality strategy — CROIC / CCC / OCF screen."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    CASH_QUALITY_CACHE_HOURS,
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
from stocks.strategies.cash_quality.html import (
    build_cash_quality_html,
    cash_quality_iframe_height,
)
from stocks.strategies.cash_quality.service import (
    prepare_pead_universe,
    run_cash_quality_scan,
)
from stocks.strategies.cash_quality.strategy import (
    cash_quality_caption,
    format_cash_quality_export_df,
)


def _inject_css() -> None:
    if st.session_state.get("_cashq_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_cashq_scan_css"] = True


def _filter_key(filters, *, cap_tier_id: str, holdings_industries_only: bool) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        holdings_industries_only,
    )


def render_cash_quality(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### Cash Quality")
    st.caption(cash_quality_caption())

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="cashq",
            cap_tier_key="cashq_cap_tier",
            holdings_key="cashq_holdings_industries_only",
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
        if st.session_state.get("cashq_filter_key") != filter_key:
            st.session_state.cashq_filter_key = filter_key
            st.session_state.pop("cashq_candidates", None)

        universe, _, _ = prepare_pead_universe(filtered, cap_tier_id=cap_tier_id)

        with row[5]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                width="stretch",
                key="cashq_scan",
                help=(
                    "Fetch annual statements via yfinance and apply Cash Quality "
                    f"filters (related fundamentals cache hint ≤ {CASH_QUALITY_CACHE_HOURS}h)."
                ),
            )

    if run_clicked:
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        progress = st.progress(0, text="Cash Quality — loading…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Cash Quality {done:,}/{total:,}…",
            )

        try:
            result = run_cash_quality_scan(
                universe,
                progress_callback=_progress,
                min_mcap_cr=min_mcap_cr,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Cash Quality scan failed: {exc}")
            return
        progress.empty()

        candidates_df = result.get("candidates")
        st.session_state.cashq_candidates = candidates_df
        scanned = int(result.get("scanned") or 0)
        with_data = int(result.get("with_data") or 0)
        n_pass = (
            len(candidates_df)
            if isinstance(candidates_df, pd.DataFrame)
            else 0
        )
        st.caption(
            f"Scanned **{scanned:,}** · fundamentals for **{with_data:,}** · "
            f"**{n_pass:,}** passed Cash Quality checks."
        )

    candidates = st.session_state.get("cashq_candidates")
    if candidates is None:
        st.caption("Set filters, then click **Scan**.")
        return

    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        st.caption(
            "No names passed Cash Quality filters "
            "(try widening filters or a lower market-cap floor)."
        )
        return

    embed_html = build_cash_quality_html(candidates, standalone=False)
    embed_html_iframe(embed_html, height=cash_quality_iframe_height(len(candidates)))

    export = format_cash_quality_export_df(candidates)
    st.download_button(
        "Download CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="cash_quality.csv",
        mime="text/csv",
        key="cashq_csv",
    )
