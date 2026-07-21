import streamlit as st

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    STRATEGY_MAX_WORKERS,
    STRATEGY_MAX_WORKERS_CAP,
    cap_tier_id_from_label,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.listings.stocks_data import load_india_stocks
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.results_utils import analysis_universe
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
from stocks.strategies.rsi_weekly.html import build_rsi_weekly_html, rsi_weekly_iframe_height
from stocks.strategies.rsi_weekly.service import (
    RSI_ENTRY,
    RSI_ENTRY_MAX,
    RSI_LENGTH,
    prepare_rsi_weekly_universe,
    run_rsi_weekly_scan,
    run_tq_worker_count,
)


def render_rsi_weekly() -> None:
    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    st.markdown("### RSI Weekly")
    st.caption(
        f"Weekly RSI({RSI_LENGTH}) · **entry {RSI_ENTRY:g}–{RSI_ENTRY_MAX:g}** "
        "(fresh cross only — prev below 60, this week 60–61) · new cross replaces prior"
    )

    with scan_toolbar_row(
        *base_scan_extra_widths(WORKERS_COL_WIDTH, SCAN_BTN_COL_WIDTH, STOP_BTN_COL_WIDTH)
    ) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="rsiw",
            cap_tier_key="rsiw_cap_tier",
            holdings_key="rsiw_holdings_industries_only",
        )
        with row[5]:
            max_workers = st.number_input(
                "Workers",
                min_value=1,
                max_value=STRATEGY_MAX_WORKERS_CAP,
                value=STRATEGY_MAX_WORKERS,
                key="rsiw_max_workers",
            )
        with row[6]:
            run_scan = st.button("Scan", type="primary", width="stretch", key="rsiw_scan")
        with row[7]:
            if st.button("Stop", width="stretch", key="rsiw_stop"):
                st.session_state.rsiw_scan_stop = True

    cap_tier_id = resolve_cap_tier_id(filters.market, cap_tier_id_from_label(cap_tier_label_ui))
    filtered = apply_stock_filters(stocks, filters)
    applied = apply_holdings_industries_if_checked(
        filtered, enabled=holdings_industries_only
    )
    if applied is None:
        return
    filtered, _holdings_industry_note = applied

    # Keep last result so the table stays after reruns without re-scanning.
    if not run_scan:
        cached = st.session_state.get("rsiw_result")
        if cached is not None and hasattr(cached, "empty") and not cached.empty:
            embed_html = build_rsi_weekly_html(cached, standalone=False)
            embed_html_iframe(embed_html, height=rsi_weekly_iframe_height(len(cached)))
            st.download_button(
                "Download CSV",
                data=cached.to_csv(index=False).encode("utf-8"),
                file_name="rsi_weekly.csv",
                mime="text/csv",
                key="rsiw_csv_cached",
            )
        return

    st.session_state.rsiw_scan_stop = False
    base_universe = analysis_universe(filtered, limit=0)
    universe, _cap_excluded, _mcap_excluded = prepare_rsi_weekly_universe(
        base_universe,
        cap_tier_id=cap_tier_id,
    )

    if universe.empty:
        st.warning("No tickers in the selected universe.")
        return

    workers = run_tq_worker_count(max_workers, len(universe))
    progress = st.progress(0, text=f"RSI weekly scan ({workers} workers)...")
    try:

        def _progress(done: int, total: int) -> None:
            progress.progress(done / total, text=f"RSI weekly {done}/{total}...")

        result = run_rsi_weekly_scan(
            universe,
            max_workers=max_workers,
            progress_callback=_progress,
            should_stop=lambda: st.session_state.get("rsiw_scan_stop", False),
        )
    except Exception as exc:
        progress.empty()
        st.error(f"RSI weekly scan failed: {exc}")
        return
    progress.empty()

    if result.empty:
        st.session_state.pop("rsiw_result", None)
        st.warning(
            f"No stocks with a fresh weekly RSI cross in {RSI_ENTRY:g}–{RSI_ENTRY_MAX:g} this week."
        )
        return

    # Skip quarterly/snapshot enrich — that was making the report crawl.
    st.session_state.rsiw_result = result
    st.caption(
        f"**{len(result):,}** stocks crossed RSI {RSI_ENTRY:g}–{RSI_ENTRY_MAX:g} this week."
    )
    embed_html = build_rsi_weekly_html(result, standalone=False)
    embed_html_iframe(embed_html, height=rsi_weekly_iframe_height(len(result)))

    st.download_button(
        "Download CSV",
        data=result.to_csv(index=False).encode("utf-8"),
        file_name="rsi_weekly.csv",
        mime="text/csv",
        key="rsiw_csv",
    )
