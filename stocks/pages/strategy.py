import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    SCAN_MCAP_PREFETCH_LIMIT,
    STRATEGY_MAX_WORKERS,
    STRATEGY_MAX_WORKERS_CAP,
    cap_tier_id_from_label,
)
from stocks.core.database import save_strategy_bb_signals, save_strategy_tq_signals
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.scan_toolbar import (
    BB_TIMEFRAME_COL_WIDTH,
    SCAN_BTN_COL_WIDTH,
    STOP_BTN_COL_WIDTH,
    STRATEGY_CHOICE_COL_WIDTH,
    WORKERS_COL_WIDTH,
    base_scan_extra_widths,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.strategies.tq_bb.html import build_strategy_dashboard_html, strategy_iframe_height
from stocks.strategies.tq_bb.panel import enrich_strategy_dataframe
from stocks.scans.scan_universe import resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.listings.stocks_data import load_india_stocks
from stocks.strategies.tq_bb.service import (
    prepare_strategy_universe,
    run_bb_strategy,
    run_tq_strategy,
    strategy_timeframe_options,
)


STRATEGY_OPTIONS = ("Both", "TQ", "Bollinger Bands")


def render_strategy() -> None:
    tab_scan, tab_recovery, tab_rsi, tab_pead = st.tabs(
        ["TQ / Bollinger Bands", "TQ W52 Recovery", "RSI Weekly", "PEAD"]
    )
    with tab_scan:
        render_strategy_scan()
    with tab_recovery:
        from stocks.pages.tq_recovery import render_tq_recovery

        render_tq_recovery()
    with tab_rsi:
        from stocks.pages.rsi_weekly import render_rsi_weekly

        render_rsi_weekly()
    with tab_pead:
        from stocks.pages.pead2 import render_pead2

        render_pead2(show_title=False)


def render_strategy_scan() -> None:
    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    st.markdown("### Strategy scan")

    with scan_toolbar_row(
        *base_scan_extra_widths(
            STRATEGY_CHOICE_COL_WIDTH,
            BB_TIMEFRAME_COL_WIDTH,
            WORKERS_COL_WIDTH,
            SCAN_BTN_COL_WIDTH,
            STOP_BTN_COL_WIDTH,
        )
    ) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="strat",
            cap_tier_key="strat_cap_tier",
            holdings_key="strat_holdings_industries_only",
        )
        with row[5]:
            strategy_choice = st.selectbox(
                "Strategy",
                STRATEGY_OPTIONS,
                key="strat_choice",
                help="TQ = trend quality + RS vs NIFTY · BB = Bollinger breakout",
            )
        with row[6]:
            tf_options = strategy_timeframe_options(strategy_choice)
            if st.session_state.get("strat_timeframe") not in tf_options:
                st.session_state["strat_timeframe"] = tf_options[0]
            scan_timeframe = st.selectbox(
                "Timeframe",
                tf_options,
                key="strat_timeframe",
                help="Applies to TQ and BB when both run (TQ: daily/weekly only)",
            )
        with row[7]:
            st.number_input(
                "Conc",
                min_value=1,
                max_value=STRATEGY_MAX_WORKERS_CAP,
                value=STRATEGY_MAX_WORKERS,
                step=1,
                key="strategy_max_workers",
                help="Parallel workers for **TQ** and throttled scans (PEAD, Earnings, Turtle). Max 32.",
            )
        with row[8]:
            run_clicked = st.button("Scan", type="primary", use_container_width=True, key="strat_scan")
        with row[9]:
            stop_clicked = st.button("Stop", use_container_width=True, key="strat_stop")

    cap_tier_id = resolve_cap_tier_id(filters.market, cap_tier_id_from_label(cap_tier_label_ui))
    filtered = apply_stock_filters(stocks, filters)
    applied = apply_holdings_industries_if_checked(
        filtered, enabled=holdings_industries_only
    )
    if applied is None:
        return
    filtered, _holdings_industry_note = applied

    if "strategy_scan_stop" not in st.session_state:
        st.session_state.strategy_scan_stop = False
    if stop_clicked:
        st.session_state.strategy_scan_stop = True

    if not run_clicked:
        return

    st.session_state.strategy_scan_stop = False

    with st.spinner(
        f"Applying filters (market-cap prefetch up to {SCAN_MCAP_PREFETCH_LIMIT} tickers)..."
    ):
        universe, cap_excluded, mcap_excluded = prepare_strategy_universe(
            filtered,
            cap_tier_id=cap_tier_id,
        )

    if universe.empty:
        st.warning("No stocks match the current filters.")
        return

    max_workers = int(st.session_state.strategy_max_workers)

    run_tq = strategy_choice in {"Both", "TQ"}
    run_bb = strategy_choice in {"Both", "Bollinger Bands"}
    should_stop = lambda: st.session_state.strategy_scan_stop

    tq_df = None
    bb_df = None

    if run_tq:
        progress = st.progress(0, text="Running TQ strategy...")
        try:

            def _tq_progress(done: int, total: int) -> None:
                progress.progress(
                    done / total,
                    text=f"TQ {done}/{total} ({scan_timeframe})...",
                )

            tq_df = run_tq_strategy(
                universe,
                timeframe=scan_timeframe,
                max_workers=max_workers,
                progress_callback=_tq_progress,
                should_stop=should_stop,
            )
        except KeyboardInterrupt:
            progress.empty()
            st.session_state.strategy_scan_stop = True
            st.warning("Scan interrupted. Use **Stop** or close the terminal if it hangs.")
            return
        except Exception as exc:
            progress.empty()
            st.error(f"TQ scan failed: {exc}")
            return
        progress.empty()

    if run_bb and not st.session_state.strategy_scan_stop:
        progress = st.progress(0, text="Running Bollinger Bands strategy...")
        try:

            def _bb_progress(done: int, total: int) -> None:
                progress.progress(
                    done / total,
                    text=f"BB {done}/{total} ({scan_timeframe})...",
                )

            bb_df = run_bb_strategy(
                universe,
                timeframe=scan_timeframe,
                max_workers=max_workers,
                progress_callback=_bb_progress,
                should_stop=should_stop,
            )
        except KeyboardInterrupt:
            progress.empty()
            st.session_state.strategy_scan_stop = True
            st.warning("Scan interrupted. Use **Stop** or close the terminal if it hangs.")
            return
        except Exception as exc:
            progress.empty()
            st.error(f"Bollinger Bands scan failed: {exc}")
            return
        progress.empty()

    tq_result = tq_df if tq_df is not None else pd.DataFrame()
    bb_result = bb_df if bb_df is not None else pd.DataFrame()
    has_tq = run_tq and tq_df is not None
    has_bb = run_bb and bb_df is not None

    if has_tq and has_bb and tq_result.empty and bb_result.empty:
        st.warning("No TQ or Bollinger Bands signals in the current selection.")
        return
    if has_tq and not has_bb and tq_result.empty:
        st.warning(f"No TQ ({scan_timeframe}) signals in the current selection.")
        return
    if has_bb and not has_tq and bb_result.empty:
        st.warning(f"No Bollinger Bands ({scan_timeframe}) signals in the current selection.")
        return

    if has_tq and not tq_result.empty:
        with st.spinner("Loading price snapshot & quarterly data for TQ signals..."):
            tq_result = enrich_strategy_dataframe(tq_result, max_workers=max_workers)
        saved_tq = save_strategy_tq_signals(tq_result, timeframe=scan_timeframe)
    else:
        saved_tq = 0
    if has_bb and not bb_result.empty:
        with st.spinner("Loading price snapshot & quarterly data for BB signals..."):
            bb_result = enrich_strategy_dataframe(bb_result, max_workers=max_workers)
        saved_bb = save_strategy_bb_signals(bb_result, timeframe=scan_timeframe)
    else:
        saved_bb = 0

    if saved_tq or saved_bb:
        parts = []
        if saved_tq:
            parts.append(f"**{saved_tq}** TQ ({scan_timeframe})")
        if saved_bb:
            parts.append(f"**{saved_bb}** BB ({scan_timeframe})")
        st.success(f"Saved {' + '.join(parts)} signals to SQLite — available on the **PEAD** tab.")
    embed_html = build_strategy_dashboard_html(
        tq_df=tq_result,
        bb_df=bb_result,
        timeframe=scan_timeframe,
        include_tq=has_tq,
        include_bb=has_bb,
        title="",
        standalone=False,
    )

    sections = int(has_tq) + int(has_bb)
    embed_html_iframe(
        embed_html,
        height=strategy_iframe_height(
            tq_rows=len(tq_result),
            bb_rows=len(bb_result),
            sections=sections,
        ),
    )

    if has_tq and not tq_result.empty:
        st.download_button(
            f"Download TQ ({scan_timeframe}) CSV",
            data=tq_result.to_csv(index=False).encode("utf-8"),
            file_name=f"strategy_tq_{scan_timeframe}.csv",
            mime="text/csv",
            key="download_tq_csv",
        )
    if has_bb and not bb_result.empty:
        st.download_button(
            f"Download BB ({scan_timeframe}) CSV",
            data=bb_result.to_csv(index=False).encode("utf-8"),
            file_name=f"strategy_bb_{scan_timeframe}.csv",
            mime="text/csv",
            key="download_bb_csv",
        )
