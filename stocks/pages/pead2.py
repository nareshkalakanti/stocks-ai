import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    STRATEGY_YFINANCE_MAX_INFLIGHT,
    cap_tier_id_from_label,
)
from stocks.strategies.pead2.html import build_pead2_dashboard_html, pead2_iframe_height
from stocks.strategies.pead2.service import prepare_pead_universe, run_pead2_scan
from stocks.core.database import strategy_signals_summary
from stocks.strategies.pead2.strategy import (
    attach_strategy_breakout_signals,
    enrich_pead_candidates,
    format_pead_export_df,
)
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.scan_toolbar import (
    SCAN_BTN_COL_WIDTH,
    base_scan_extra_widths,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.scans.scan_universe import cap_tier_min_mcap_cr, resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.listings.stocks_data import load_india_stocks

def render_pead2() -> None:
    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    st.markdown("### PEAD")

    with scan_toolbar_row(*base_scan_extra_widths(SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="pead2",
            cap_tier_key="pead2_cap_tier",
            holdings_key="pead2_holdings_industries_only",
        )
        with row[5]:
            run_clicked = st.button("Scan", type="primary", use_container_width=True)

    cap_tier_id = resolve_cap_tier_id(filters.market, cap_tier_id_from_label(cap_tier_label_ui))
    min_mcap_cr = cap_tier_min_mcap_cr(cap_tier_id)
    filtered = apply_stock_filters(stocks, filters)

    applied = apply_holdings_industries_if_checked(
        filtered, enabled=holdings_industries_only
    )
    if applied is None:
        return
    filtered, _holdings_industry_note = applied

    if not run_clicked and "pead2_candidates" not in st.session_state:
        st.info("Click **Scan** to load PEAD candidates.")
        return

    if run_clicked:
        with st.spinner("Applying market-cap filter..."):
            universe, cap_excluded, mcap_excluded = prepare_pead_universe(
                filtered,
                cap_tier_id=cap_tier_id,
            )

        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        progress = st.progress(0, text="PEAD — fetching quarterly data...")
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

    candidates = st.session_state.get("pead2_candidates")
    candidates_previous = st.session_state.get("pead2_candidates_previous")
    scanned = st.session_state.get("pead2_scanned", 0)

    if candidates is None or candidates.empty:
        st.warning(
            f"No PEAD results — scanned **{scanned:,}** tickers but yfinance returned no "
            f"quarterly P&L for any of them (often Yahoo rate limits). "
            f"Wait a minute and **Scan** again, narrow **Industry**, or lower "
            f"`STRATEGY_YFINANCE_MAX_INFLIGHT` in `.env` (currently {STRATEGY_YFINANCE_MAX_INFLIGHT})."
        )
        return

    candidates = attach_strategy_breakout_signals(enrich_pead_candidates(candidates))

    prev_df = (
        candidates_previous
        if candidates_previous is not None and not candidates_previous.empty
        else pd.DataFrame()
    )
    strat_meta = strategy_signals_summary()
    tq_hits = int(candidates["has_tq"].sum()) if "has_tq" in candidates.columns else 0
    bb_hits = int(candidates["has_bb"].sum()) if "has_bb" in candidates.columns else 0

    embed_html = build_pead2_dashboard_html(
        candidates,
        df_previous=prev_df,
        title="Top PEAD Candidates",
        standalone=False,
        strategy_meta=strat_meta,
    )

    strat_note = ""
    if strat_meta.get("tq_count") or strat_meta.get("bb_count"):
        strat_note = f" · **{tq_hits}** PEAD rows match TQ · **{bb_hits}** match BB (SQLite)"
    else:
        strat_note = " · Run **Strategy → TQ / Bollinger Bands** scan to fill TQ/BB cache"

    st.caption(
        "**PE** (Option A) = price ÷ sum of last 4 quarters’ EPS. "
        "**Fwd PE** (Option B) = price ÷ (latest quarter EPS × 4). "
        "**TQ** / **BB** columns = last Strategy scan saved in SQLite."
        f"{strat_note}"
    )
    embed_html_iframe(embed_html, height=pead2_iframe_height(len(candidates)))

    csv = format_pead_export_df(candidates).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download PEAD CSV",
        data=csv,
        file_name="pead_candidates.csv",
        mime="text/csv",
    )
