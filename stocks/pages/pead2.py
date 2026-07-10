import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    PEAD2_RECENT_DAYS_DEFAULT,
    STRATEGY_YFINANCE_MAX_INFLIGHT,
    cap_tier_id_from_label,
)
from stocks.strategies.pead2.html import build_pead2_dashboard_html, pead2_iframe_height
from stocks.strategies.pead2.service import prepare_pead_universe, run_pead2_scan
from stocks.strategies.pead2.strategy import (
    enrich_pead_candidates,
    format_pead_export_df,
)
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.scan_toolbar import (
    COMPACT_SCAN_BTN_COL_WIDTH,
    base_scan_extra_widths,
    inject_scan_toolbar_css,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.scans.scan_universe import cap_tier_min_mcap_cr, resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.listings.stocks_data import load_india_stocks

_PEAD_SCAN_CSS = """
<style>
.st-key-pead2_scan button {
  min-height: 1.85rem;
  padding: 0.12rem 0.55rem;
  font-size: 0.78rem;
  font-weight: 600;
  border-radius: 6px;
  white-space: nowrap;
}
</style>
"""


def _inject_pead_scan_css() -> None:
    if st.session_state.get("_pead_scan_css"):
        return
    inject_scan_toolbar_css()
    st.markdown(_PEAD_SCAN_CSS, unsafe_allow_html=True)
    st.session_state["_pead_scan_css"] = True


def _pead_filter_key(
    filters,
    *,
    cap_tier_id: str,
    holdings_industries_only: bool,
) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        holdings_industries_only,
    )


def render_pead2(*, show_title: bool = True) -> None:
    _inject_pead_scan_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### PEAD")

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="pead2",
            cap_tier_key="pead2_cap_tier",
            holdings_key="pead2_holdings_industries_only",
        )
        with row[5]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                use_container_width=True,
                key="pead2_scan",
                help="Full universe scan — loads saved DB first, fetches only missing tickers.",
            )

    cap_tier_id = resolve_cap_tier_id(filters.market, cap_tier_id_from_label(cap_tier_label_ui))
    min_mcap_cr = cap_tier_min_mcap_cr(cap_tier_id)
    filtered = apply_stock_filters(stocks, filters)

    applied = apply_holdings_industries_if_checked(
        filtered, enabled=holdings_industries_only
    )
    if applied is None:
        return
    filtered, _holdings_industry_note = applied

    filter_key = _pead_filter_key(
        filters,
        cap_tier_id=cap_tier_id,
        holdings_industries_only=holdings_industries_only,
    )
    if st.session_state.get("pead2_filter_key") != filter_key:
        st.session_state.pead2_filter_key = filter_key
        st.session_state.pop("pead2_candidates", None)

    if run_clicked:
        with st.spinner("Applying market-cap filter..."):
            universe, cap_excluded, mcap_excluded = prepare_pead_universe(
                filtered,
                cap_tier_id=cap_tier_id,
            )

        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        progress = st.progress(0, text="PEAD — loading from DB...")
        try:

            def _progress(done: int, total: int) -> None:
                progress.progress(done / total, text=f"PEAD {done}/{total}...")

            result = run_pead2_scan(
                universe,
                progress_callback=_progress,
                min_mcap_cr=min_mcap_cr,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"PEAD scan failed: {exc}")
            return
        progress.empty()

        st.session_state.pead2_candidates = result["candidates"]
        st.session_state.pead2_candidates_previous = result.get(
            "candidates_previous", pd.DataFrame()
        )
        st.session_state.pead2_scanned = result["scanned"]
        st.session_state.pead2_fetched = int(result.get("fetched") or 0)
        st.session_state.pead2_cache_hits = int(result.get("cache_hits") or 0)

    candidates = st.session_state.get("pead2_candidates")
    candidates_previous = st.session_state.get("pead2_candidates_previous")
    scanned = st.session_state.get("pead2_scanned", 0)

    if candidates is None or candidates.empty:
        st.caption("Set filters, then click **Scan** for a full-universe PEAD load (DB first).")
        return

    candidates = enrich_pead_candidates(candidates)

    prev_df = (
        candidates_previous
        if candidates_previous is not None and not candidates_previous.empty
        else pd.DataFrame()
    )
    cache_hits = int(st.session_state.get("pead2_cache_hits") or 0)
    fetched = int(st.session_state.get("pead2_fetched") or 0)
    embed_html = build_pead2_dashboard_html(
        candidates,
        df_previous=prev_df,
        title="Top PEAD Candidates",
        standalone=False,
        default_sort_col="returns_pct",
        default_sort_dir=-1,
        recent_filter_days=PEAD2_RECENT_DAYS_DEFAULT,
    )

    st.caption(
        f"{len(candidates)} stocks · {cache_hits:,} from DB"
        + (f" · {fetched:,} fetched" if fetched else "")
        + f" · **Latest results** in table = last {PEAD2_RECENT_DAYS_DEFAULT}d."
    )
    embed_html_iframe(embed_html, height=pead2_iframe_height(len(candidates)))

    csv = format_pead_export_df(candidates).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download PEAD CSV",
        data=csv,
        file_name="pead_candidates.csv",
        mime="text/csv",
    )
