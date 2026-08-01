"""DCF — forecast FCF + terminal value (over / under / fair + reverse growth)."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    DCF_CACHE_HOURS,
    DCF_DISCOUNT_RATE,
    DCF_FORECAST_YEARS,
    DCF_TERMINAL_GROWTH,
    INDIA_STOCKS_DATASET,
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
from stocks.scans.scan_universe import cap_tier_min_mcap_cr, resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.strategies.dcf.html import build_dcf_html, dcf_iframe_height
from stocks.strategies.dcf.service import prepare_pead_universe, run_dcf_scan
from stocks.strategies.dcf.strategy import dcf_caption, format_dcf_export_df


def _inject_css() -> None:
    if st.session_state.get("_dcf_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_dcf_scan_css"] = True


def _filter_key(
    filters,
    *,
    cap_tier_id: str,
    discount_pct: float,
    years: int,
    term_g_pct: float,
    growth_override: float | None,
) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        discount_pct,
        years,
        term_g_pct,
        growth_override,
    )


def render_dcf(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### DCF")
    st.caption(dcf_caption())

    with st.expander("Assumptions", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            discount_pct = st.number_input(
                "Discount rate %",
                min_value=1.0,
                max_value=30.0,
                value=float(round(DCF_DISCOUNT_RATE * 100, 2)),
                step=0.5,
                key="dcf_discount_pct",
                help="Opportunity cost / required return (video default 8.5%).",
            )
        with c2:
            years = st.number_input(
                "Forecast years",
                min_value=5,
                max_value=20,
                value=int(DCF_FORECAST_YEARS),
                step=1,
                key="dcf_years",
            )
        with c3:
            term_g_pct = st.number_input(
                "Terminal growth %",
                min_value=0.0,
                max_value=8.0,
                value=float(round(DCF_TERMINAL_GROWTH * 100, 2)),
                step=0.5,
                key="dcf_term_g",
                help="Perpetual growth after forecast (must stay below discount rate).",
            )
        with c4:
            use_override = st.checkbox(
                "Force forecast growth",
                value=False,
                key="dcf_force_g",
                help="Off = use historical FCF CAGR (capped). On = flat/custom path.",
            )
            growth_override = None
            if use_override:
                growth_override = st.number_input(
                    "Forecast growth %",
                    min_value=-20.0,
                    max_value=40.0,
                    value=0.0,
                    step=1.0,
                    key="dcf_growth_pct",
                )

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui = render_base_scan_filters(
            stocks,
            row,
            key_prefix="dcf",
            cap_tier_key="dcf_cap_tier",
        )
        cap_tier_id = resolve_cap_tier_id(
            filters.market, cap_tier_id_from_label(cap_tier_label_ui)
        )
        min_mcap_cr = cap_tier_min_mcap_cr(cap_tier_id)
        filtered = apply_stock_filters(stocks, filters)

        filter_key = _filter_key(
            filters,
            cap_tier_id=cap_tier_id,
            discount_pct=float(discount_pct),
            years=int(years),
            term_g_pct=float(term_g_pct),
            growth_override=growth_override,
        )
        if st.session_state.get("dcf_filter_key") != filter_key:
            st.session_state.dcf_filter_key = filter_key
            st.session_state.pop("dcf_candidates", None)

        universe, _, _ = prepare_pead_universe(filtered, cap_tier_id=cap_tier_id)

        with row[4]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                width="stretch",
                key="dcf_scan",
                help=(
                    "Fetch FCF via yfinance and run two-stage DCF "
                    f"(cache hint ≤ {DCF_CACHE_HOURS}h)."
                ),
            )

    if run_clicked:
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return
        if float(term_g_pct) / 100.0 >= float(discount_pct) / 100.0:
            st.error("Terminal growth must be strictly below the discount rate.")
            return

        progress = st.progress(0, text="DCF — loading…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"DCF {done:,}/{total:,}…",
            )

        try:
            result = run_dcf_scan(
                universe,
                progress_callback=_progress,
                min_mcap_cr=min_mcap_cr,
                discount_rate=float(discount_pct) / 100.0,
                forecast_years=int(years),
                growth_pct=growth_override,
                terminal_growth=float(term_g_pct) / 100.0,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"DCF scan failed: {exc}")
            return
        progress.empty()

        candidates_df = result.get("candidates")
        st.session_state.dcf_candidates = candidates_df
        scanned = int(result.get("scanned") or 0)
        with_data = int(result.get("with_data") or 0)
        n_pass = (
            len(candidates_df) if isinstance(candidates_df, pd.DataFrame) else 0
        )
        und = 0
        if isinstance(candidates_df, pd.DataFrame) and not candidates_df.empty:
            if "verdict" in candidates_df.columns:
                und = int((candidates_df["verdict"] == "Undervalued").sum())
        st.caption(
            f"Scanned **{scanned:,}** · DCF for **{with_data:,}** · "
            f"**{n_pass:,}** with fair price · **{und:,}** undervalued."
        )

    candidates = st.session_state.get("dcf_candidates")
    if candidates is None:
        st.caption(
            "Set filters / assumptions, then **Scan**. "
            "Needs positive Free Cash Flow + share count from Yahoo."
        )
        return

    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        st.caption(
            "No DCF-able names (need positive FCF and shares). "
            "Try another cap tier or force 0% growth for flat FCF."
        )
        return

    embed_html = build_dcf_html(candidates, standalone=False)
    embed_html_iframe(embed_html, height=dcf_iframe_height(len(candidates)))

    export = format_dcf_export_df(candidates)
    st.download_button(
        "Download CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="dcf.csv",
        mime="text/csv",
        key="dcf_csv",
    )
