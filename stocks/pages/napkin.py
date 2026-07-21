"""Napkin Investing — LotusDew near-term vs terminal PE framework."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    NAPKIN_HORIZON_YEARS,
    NAPKIN_NEAR_WEIGHT,
    PEAD2_CACHE_HOURS,
    cap_tier_id_from_label,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.listings.stocks_data import load_india_stocks
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.holdings_playlist import is_holdings_playlist
from stocks.scans.scan_toolbar import (
    COMPACT_SCAN_BTN_COL_WIDTH,
    base_scan_extra_widths,
    inject_scan_toolbar_css,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.scan_universe import cap_tier_min_mcap_cr, resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.strategies.napkin.service import prepare_pead_universe, run_napkin_scan
from stocks.strategies.napkin.strategy import format_napkin_export_df, napkin_caption
from stocks.strategies.pead2.html import build_pead2_dashboard_html, pead2_iframe_height
from stocks.strategies.pead2.service import (
    Pead2ScanCoverage,
    expand_pead_candidates_to_universe,
)


def _inject_css() -> None:
    if st.session_state.get("_napkin_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_napkin_scan_css"] = True


def _filter_key(filters, *, cap_tier_id: str, holdings_industries_only: bool) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        holdings_industries_only,
    )


def render_napkin(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### Napkin Investing")
    st.caption(napkin_caption())

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="napkin",
            cap_tier_key="napkin_cap_tier",
            holdings_key="napkin_holdings_industries_only",
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
        if st.session_state.get("napkin_filter_key") != filter_key:
            st.session_state.napkin_filter_key = filter_key
            st.session_state.pop("napkin_candidates", None)

        universe, _, _ = prepare_pead_universe(filtered, cap_tier_id=cap_tier_id)

        with row[5]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                width="stretch",
                key="napkin_scan",
                help=(
                    f"Load PEAD fundamentals (cache ≤ {PEAD2_CACHE_HOURS}h), apply "
                    f"LotusDew napkin: near-term weight {NAPKIN_NEAR_WEIGHT:.0%} over "
                    f"{NAPKIN_HORIZON_YEARS}Y vs terminal value."
                ),
            )

    holdings_view = is_holdings_playlist(filters.market)

    if run_clicked:
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        progress = st.progress(0, text="Napkin Investing — loading…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Napkin Investing {done:,}/{total:,}…",
            )

        try:
            result = run_napkin_scan(
                universe,
                progress_callback=_progress,
                min_mcap_cr=min_mcap_cr,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Napkin Investing scan failed: {exc}")
            return
        progress.empty()

        st.session_state.napkin_candidates = result.get("candidates")
        st.session_state.napkin_candidates_previous = result.get("candidates_previous")
        st.session_state.napkin_cache_hits = int(result.get("cache_hits") or 0)
        coverage = result.get("coverage")
        if isinstance(coverage, Pead2ScanCoverage):
            st.session_state.napkin_coverage = coverage

        fetched = int(result.get("fetched") or 0)
        if fetched > 0:
            st.caption(
                f"Updated **{int(result.get('saved') or 0):,}** tickers from Yahoo "
                f"({fetched:,} tried)."
            )

    candidates = st.session_state.get("napkin_candidates")
    candidates_previous = st.session_state.get("napkin_candidates_previous")

    if candidates is None:
        st.caption("Set filters, then click **Scan**.")
        return

    if holdings_view and not universe.empty:
        candidates = expand_pead_candidates_to_universe(universe, candidates)
        if candidates_previous is not None and not candidates_previous.empty:
            candidates_previous = expand_pead_candidates_to_universe(
                universe, candidates_previous
            )

    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        st.caption(
            "No napkin-scorable names in this universe "
            "(need a usable PE — try widening filters or refreshing cache)."
        )
        return

    prev_df = (
        candidates_previous
        if isinstance(candidates_previous, pd.DataFrame) and not candidates_previous.empty
        else pd.DataFrame()
    )
    cache_hits = int(st.session_state.get("napkin_cache_hits") or 0)
    tq_n = (
        int(candidates["has_tq"].fillna(False).astype(bool).sum())
        if "has_tq" in candidates.columns
        else 0
    )
    bb_n = (
        int(candidates["has_bb"].fillna(False).astype(bool).sum())
        if "has_bb" in candidates.columns
        else 0
    )

    embed_html = build_pead2_dashboard_html(
        candidates,
        df_previous=prev_df,
        title="Napkin Investing",
        list_label="Napkin screen",
        standalone=False,
        variant="napkin",
        default_sort_col="pead_score",
        score_high_min=50.0,
    )
    st.caption(
        f"{len(candidates)} names · {cache_hits:,} from DB · "
        f"TQ **{tq_n}** · BB **{bb_n}** · "
        f"score ≥50 ⇒ growth covers required near-term CAGR · "
        f"**click a row** to expand detail."
    )
    embed_html_iframe(embed_html, height=pead2_iframe_height(len(candidates)))

    csv = format_napkin_export_df(candidates).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Napkin CSV",
        data=csv,
        file_name="napkin_investing.csv",
        mime="text/csv",
        key="napkin_csv",
    )
