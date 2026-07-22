"""PEAD 1 — Earnings Explosion screen, PEAD 2–style dashboard report."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    STRATEGY_MAX_WORKERS,
    STRATEGY_MAX_WORKERS_CAP,
    cap_tier_id_from_label,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.listings.stocks_data import load_india_stocks
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
from stocks.strategies.pead.dashboard import (
    enrich_pead1_expand_panels,
    pead1_candidates_for_dashboard,
    pead1_export_df,
    pead1_needs_expand_enrich,
)
from stocks.strategies.pead.service import prepare_pead_universe, run_pead_scan
from stocks.strategies.pead2.html import build_pead2_dashboard_html, pead2_iframe_height


def _inject_css() -> None:
    if st.session_state.get("_pead1_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_pead1_scan_css"] = True


def _filter_key(filters, *, cap_tier_id: str) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
    )


def render_pead1(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### PEAD 1 — Earnings Explosion")

    st.caption(
        "PEAD 1: Rev/Op/EPS ≥1.5× · margin · gap+volume. "
        "**BUY** = fundamentals + price gate (gap/vol). "
        "**FUND** = fundamentals only (price gate failed). "
        "PE / Fwd PE from snapshot · extra cols behind Columns (like PEAD 2)."
    )

    with scan_toolbar_row(
        *base_scan_extra_widths(WORKERS_COL_WIDTH, COMPACT_SCAN_BTN_COL_WIDTH)
    ) as row:
        filters, cap_tier_label_ui = render_base_scan_filters(
            stocks,
            row,
            key_prefix="pead1",
            cap_tier_key="pead1_cap_tier",
        )
        cap_tier_id = resolve_cap_tier_id(
            filters.market, cap_tier_id_from_label(cap_tier_label_ui)
        )
        filtered = apply_stock_filters(stocks, filters)

        filter_key = _filter_key(
            filters,
            cap_tier_id=cap_tier_id,
            )
        if st.session_state.get("pead1_filter_key") != filter_key:
            st.session_state.pead1_filter_key = filter_key
            st.session_state.pop("pead1_candidates", None)

        with row[4]:
            max_workers = st.number_input(
                "Workers",
                min_value=1,
                max_value=STRATEGY_MAX_WORKERS_CAP,
                value=STRATEGY_MAX_WORKERS,
                key="pead1_max_workers",
            )
        with row[5]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                width="stretch",
                key="pead1_scan",
                help="Run PEAD 1 Earnings Explosion screen on the current universe.",
            )

    universe, _cap_ex, _mcap_ex = prepare_pead_universe(
        filtered, cap_tier_id=cap_tier_id
    )

    if run_clicked:
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        progress = st.progress(0, text="PEAD 1 scanning...")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="PEAD 1 done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"PEAD 1 scanning {done:,}/{total:,}...",
            )

        try:
            result = run_pead_scan(
                universe,
                max_workers=int(max_workers),
                progress_callback=_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"PEAD 1 scan failed: {exc}")
            return
        progress.empty()

        candidates = pead1_candidates_for_dashboard(result.get("candidates"))
        if candidates.empty:
            st.session_state.pop("pead1_candidates", None)
            st.warning("No PEAD 1 candidates (Rev/Op/EPS burst + margin gates).")
            return

        with st.spinner("Loading expand panels (price + quarters)..."):
            candidates = enrich_pead1_expand_panels(
                candidates, max_workers=int(max_workers)
            )
            candidates = pead1_candidates_for_dashboard(candidates)

        st.session_state.pead1_candidates = candidates
        buy_n = int((candidates.get("pead1_signal") == "BUY").sum()) if "pead1_signal" in candidates.columns else 0
        st.caption(
            f"**{len(candidates):,}** PEAD 1 hits · **{buy_n:,}** BUY (gap+volume) · "
            f"scanned {int(result.get('scanned') or 0):,}"
        )

    candidates = st.session_state.get("pead1_candidates")
    if candidates is None:
        st.caption("Set filters, then click **Scan**.")
        return
    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        st.caption("No PEAD 1 candidates loaded.")
        return

    # Backfill expand panel for older scans that lack quarters / snapshot.
    if pead1_needs_expand_enrich(candidates):
        with st.spinner("Loading PEAD 2–style quarterly panels + moving averages..."):
            candidates = enrich_pead1_expand_panels(
                candidates,
                max_workers=int(st.session_state.get("pead1_max_workers") or STRATEGY_MAX_WORKERS),
            )
            candidates = pead1_candidates_for_dashboard(candidates)
            st.session_state.pead1_candidates = candidates

    tq_n = int(candidates["has_tq"].fillna(False).astype(bool).sum()) if "has_tq" in candidates.columns else 0
    bb_n = int(candidates["has_bb"].fillna(False).astype(bool).sum()) if "has_bb" in candidates.columns else 0

    embed_html = build_pead2_dashboard_html(
        candidates,
        title="PEAD 1 — Earnings Explosion",
        list_label="PEAD 1 candidates",
        standalone=False,
        variant="pead1",
        default_sort_col="pead_score",
        default_sort_dir=-1,
        score_high_min=5.0,
    )
    st.caption(
        f"{len(candidates)} stocks · TQ **{tq_n}** · BB **{bb_n}** · "
        f"**Buy** filter · expand = quarterly earnings + MAs (like PEAD 2)"
    )
    embed_html_iframe(embed_html, height=pead2_iframe_height(len(candidates)))

    st.download_button(
        "Download PEAD 1 CSV",
        data=pead1_export_df(candidates).to_csv(index=False).encode("utf-8"),
        file_name="pead1_candidates.csv",
        mime="text/csv",
        key="pead1_csv",
    )
