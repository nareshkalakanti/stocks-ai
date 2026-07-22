"""Micro Value — mcap 20–200 Cr · Mcap/Sales < 1."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    MICRO_VALUE_CACHE_HOURS,
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
from stocks.strategies.micro_value.html import (
    build_micro_value_html,
    micro_value_iframe_height,
)
from stocks.strategies.micro_value.service import (
    prepare_micro_value_universe,
    run_micro_value_scan,
)
from stocks.strategies.micro_value.strategy import (
    format_micro_value_export_df,
    micro_value_caption,
)


def _inject_css() -> None:
    if st.session_state.get("_microv_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_microv_scan_css"] = True


def _filter_key(filters, *, cap_tier_id: str, holdings_industries_only: bool) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        holdings_industries_only,
    )


def render_micro_value(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### Micro Value")
    st.caption(micro_value_caption())

    # Default toolbar tier to Micro Value band when unset.
    if "microv_cap_tier" not in st.session_state:
        st.session_state["microv_cap_tier"] = "Micro Value (20–200 Cr)"

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="microv",
            cap_tier_key="microv_cap_tier",
            holdings_key="microv_holdings_industries_only",
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
        if st.session_state.get("microv_filter_key") != filter_key:
            st.session_state.microv_filter_key = filter_key
            st.session_state.pop("microv_candidates", None)

        universe, _, _ = prepare_micro_value_universe(
            filtered, cap_tier_id=cap_tier_id
        )

        with row[5]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                width="stretch",
                key="microv_scan",
                help=(
                    "Scan ₹20–200 Cr names with Market cap/Sales < 1 "
                    f"(cache hint ≤ {MICRO_VALUE_CACHE_HOURS}h)."
                ),
            )

    if run_clicked:
        if universe.empty:
            st.warning(
                "No stocks in the Micro Value band (20–200 Cr) for current filters. "
                "Try All markets / wider sector, or wait for mcap cache to fill."
            )
            return

        progress = st.progress(0, text="Micro Value — loading…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Micro Value {done:,}/{total:,}…",
            )

        try:
            result = run_micro_value_scan(
                universe,
                progress_callback=_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Micro Value scan failed: {exc}")
            return
        progress.empty()

        candidates_df = result.get("candidates")
        st.session_state.microv_candidates = candidates_df
        scanned = int(result.get("scanned") or 0)
        with_data = int(result.get("with_data") or 0)
        n_pass = (
            len(candidates_df)
            if isinstance(candidates_df, pd.DataFrame)
            else 0
        )
        st.caption(
            f"Scanned **{scanned:,}** · fundamentals for **{with_data:,}** · "
            f"**{n_pass:,}** with Mcap/Sales < 1 in band."
        )

    candidates = st.session_state.get("microv_candidates")
    if candidates is None:
        st.caption("Set filters, then click **Scan** (defaults to 20–200 Cr).")
        return

    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        st.caption(
            "No names with **Mcap/Sales < 1** in ₹20–200 Cr "
            "(try widening sector filters)."
        )
        return

    embed_html = build_micro_value_html(candidates, standalone=False)
    embed_html_iframe(embed_html, height=micro_value_iframe_height(len(candidates)))

    export = format_micro_value_export_df(candidates)
    st.download_button(
        "Download CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="micro_value.csv",
        mime="text/csv",
        key="microv_csv",
    )
