import streamlit as st

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    STRATEGY_MAX_WORKERS,
    STRATEGY_MAX_WORKERS_CAP,
    cap_tier_id_from_label,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.scans.results_utils import analysis_universe
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.scan_toolbar import (
    SCAN_BTN_COL_WIDTH,
    STOP_BTN_COL_WIDTH,
    WORKERS_COL_WIDTH,
    base_scan_extra_widths,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.scan_universe import resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.listings.stocks_data import load_india_stocks
from stocks.strategies.tq_recovery.html import build_tq_recovery_html, tq_recovery_iframe_height
from stocks.strategies.tq_recovery.service import (
    TQ_ADX_THRESHOLD,
    TQ_DMI_LENGTH,
    TQ_MA_LENGTH,
    TQ_RS_LONG_EXIT_THRESHOLD,
    TQ_RS_LONG_TERM,
    TQ_RS_SHORT_TERM,
    TQ_RSI_ENTRY,
    TQ_RSI_EXIT,
    TQ_RSI_LENGTH,
    TQ_SUPERTREND_ATR,
    TQ_SUPERTREND_FACTOR,
    prepare_tq_recovery_universe,
    run_tq_recovery_scan,
    run_tq_worker_count,
)


def render_tq_recovery() -> None:
    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    st.markdown("### TQ W52 Recovery")

    with scan_toolbar_row(
        *base_scan_extra_widths(WORKERS_COL_WIDTH, SCAN_BTN_COL_WIDTH, STOP_BTN_COL_WIDTH)
    ) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="tqrec",
            cap_tier_key="tqrec_cap_tier",
            holdings_key="tqrec_holdings_industries_only",
        )
        with row[5]:
            max_workers = st.number_input(
                "Workers",
                min_value=1,
                max_value=STRATEGY_MAX_WORKERS_CAP,
                value=STRATEGY_MAX_WORKERS,
                key="tqrec_max_workers",
            )
        with row[6]:
            run_scan = st.button("Scan", type="primary", width="stretch", key="tqrec_scan")
        with row[7]:
            if st.button("Stop", width="stretch", key="tqrec_stop"):
                st.session_state.tqrec_scan_stop = True

    cap_tier_id = resolve_cap_tier_id(filters.market, cap_tier_id_from_label(cap_tier_label_ui))
    filtered = apply_stock_filters(stocks, filters)
    applied = apply_holdings_industries_if_checked(
        filtered, enabled=holdings_industries_only
    )
    if applied is None:
        return
    filtered, _holdings_industry_note = applied

    if not run_scan:
        return

    st.session_state.tqrec_scan_stop = False
    base_universe = analysis_universe(filtered, limit=0)
    universe, cap_excluded, mcap_excluded = prepare_tq_recovery_universe(
        base_universe,
        cap_tier_id=cap_tier_id,
    )

    if universe.empty:
        st.warning("No tickers in the selected universe.")
        return

    workers = run_tq_worker_count(max_workers, len(universe))
    progress = st.progress(0, text="TQ W52 recovery scan...")
    try:

        def _progress(done: int, total: int) -> None:
            progress.progress(done / total, text=f"TQ recovery {done}/{total}...")

        result = run_tq_recovery_scan(
            universe,
            max_workers=max_workers,
            progress_callback=_progress,
            should_stop=lambda: st.session_state.get("tqrec_scan_stop", False),
        )
    except Exception as exc:
        progress.empty()
        st.error(f"TQ recovery scan failed: {exc}")
        return
    progress.empty()

    if result.empty:
        st.warning(
            "No stocks with TQ W52 red → yellow (below zero) in the current selection."
        )
        return

    with st.spinner("Loading price snapshot & quarterly data..."):
        from stocks.strategies.tq_bb.panel import enrich_strategy_dataframe

        result = enrich_strategy_dataframe(result, max_workers=max_workers)

    embed_html = build_tq_recovery_html(result, standalone=False)

    embed_html_iframe(embed_html, height=tq_recovery_iframe_height(len(result)))

    st.download_button(
        "Download CSV",
        data=result.to_csv(index=False).encode("utf-8"),
        file_name="tq_w52_recovery.csv",
        mime="text/csv",
        key="tqrec_csv",
    )
