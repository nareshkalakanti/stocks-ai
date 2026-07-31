"""Positive Surprise Quant — NSE Integrated Filing XBRL (independent of PEAD)."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    PEAD_FACTOR_FRESH_DAYS,
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
from stocks.strategies.pead2.html import build_pead2_dashboard_html, pead2_iframe_height
from stocks.strategies.positive_surprise.service import (
    prepare_psq_universe,
    run_positive_surprise_scan,
)
from stocks.strategies.positive_surprise.strategy import format_psq_export_df, psq_caption


def _inject_css() -> None:
    if st.session_state.get("_psq_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_psq_scan_css"] = True


def _filter_key(filters, *, cap_tier_id: str, lookback_days: int) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        lookback_days,
    )


def render_positive_surprise(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### Positive Surprise Quant")
    st.caption(psq_caption())

    with scan_toolbar_row(*base_scan_extra_widths(0.55, COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui = render_base_scan_filters(
            stocks,
            row,
            key_prefix="psq",
            cap_tier_key="psq_cap_tier",
        )
        # Force NSE lens in caption even if filter says All — scan intersects NSE prints.
        cap_tier_id = resolve_cap_tier_id(
            filters.market, cap_tier_id_from_label(cap_tier_label_ui)
        )
        min_mcap_cr = cap_tier_min_mcap_cr(cap_tier_id)
        filtered = apply_stock_filters(stocks, filters)

        with row[4]:
            lookback = int(
                st.number_input(
                    "Lookback days",
                    min_value=14,
                    max_value=180,
                    value=int(st.session_state.get("psq_lookback") or 90),
                    step=7,
                    key="psq_lookback",
                    help="NSE financial-result announcements window (who printed).",
                )
            )

        filter_key = _filter_key(
            filters,
            cap_tier_id=cap_tier_id,
            lookback_days=lookback,
        )
        if st.session_state.get("psq_filter_key") != filter_key:
            st.session_state.psq_filter_key = filter_key
            st.session_state.pop("psq_candidates", None)

        universe = prepare_psq_universe(filtered, min_mcap_cr=min_mcap_cr)

        with row[5]:
            run_clicked = st.button(
                "Scan NSE",
                type="primary",
                use_container_width=True,
                key="psq_scan",
                help=(
                    "Pull NSE result announcements, then Integrated Filing Ind-AS XBRL "
                    "for same-quarter YoY. Does not use PEAD/Yahoo fundamentals."
                ),
            )

    if run_clicked:
        if universe.empty:
            st.warning("No NSE stocks match the current filters.")
            return

        progress = st.progress(0, text="PositiveQ — fetching NSE filings…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"NSE XBRL {done:,}/{total:,}…",
            )

        try:
            result = run_positive_surprise_scan(
                universe,
                lookback_days=lookback,
                progress_callback=_progress,
                min_mcap_cr=min_mcap_cr,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Positive Surprise Quant scan failed: {exc}")
            return
        progress.empty()

        st.session_state.psq_candidates = result.get("candidates")
        st.session_state.psq_candidates_previous = result.get("candidates_previous")
        st.session_state.psq_scan_stats = result.get("scan_stats") or {}
        stats = st.session_state.psq_scan_stats
        st.caption(
            f"NSE announcements **{int(stats.get('nse_announcements_raw') or 0):,}** → "
            f"**{int(stats.get('unique_tickers') or 0):,}** result stocks → "
            f"**{int(stats.get('to_fetch') or 0):,}** in filter → "
            f"**{int(stats.get('xbrl_ok') or 0):,}** XBRL YoY parsed."
        )

    candidates = st.session_state.get("psq_candidates")

    if candidates is None:
        st.caption("Set filters, then click **Scan NSE**.")
        return

    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        st.caption(
            "No positive NSE surprises in this window "
            "(try a longer lookback or wider filters)."
        )
        return

    prev_df = pd.DataFrame()
    stats = st.session_state.get("psq_scan_stats") or {}

    embed_html = build_pead2_dashboard_html(
        candidates,
        df_previous=prev_df,
        title="Positive Surprise Quant — NSE",
        list_label="Positive surprises (NSE XBRL)",
        standalone=False,
        variant="psq",
        default_sort_col="pead_score",
        score_high_min=55.0,
    )
    st.caption(
        f"{len(candidates)} positive-surprise names · NSE XBRL · "
        f"lookback **{lookback}d** · "
        f"prefer results within ~**{PEAD_FACTOR_FRESH_DAYS}–90** days for a 2–4 month hold · "
        f"**click a row** to expand detail."
    )
    with st.expander(
        f"Coverage · {int(stats.get('xbrl_ok') or 0):,} XBRL · "
        f"{int(stats.get('to_fetch') or 0):,} scanned",
        expanded=False,
    ):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("NSE announcements", f"{int(stats.get('nse_announcements_raw') or 0):,}")
        c2.metric("Result prints", f"{int(stats.get('unique_tickers') or 0):,}")
        c3.metric("In filter", f"{int(stats.get('to_fetch') or 0):,}")
        c4.metric("XBRL YoY ok", f"{int(stats.get('xbrl_ok') or 0):,}")

    embed_html_iframe(embed_html, height=pead2_iframe_height(len(candidates)))

    csv = format_psq_export_df(candidates).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Positive Surprise CSV",
        data=csv,
        file_name="positive_surprise_nse.csv",
        mime="text/csv",
        key="psq_csv",
    )
