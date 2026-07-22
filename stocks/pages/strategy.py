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
from stocks.dashboards.interactive_table import prepare_interactive_report_df
from stocks.dashboards.report_html import embed_html_iframe
from stocks.scans.results_utils import analysis_universe
from stocks.scans.scan_universe import resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.listings.stocks_data import load_india_stocks
from stocks.strategies.ema_daily.html import build_ema_daily_html, ema_daily_iframe_height
from stocks.strategies.ema_daily.service import (
    prepare_ema_daily_universe,
    run_ema_daily_scan,
)
from stocks.strategies.rsi_weekly.html import build_rsi_weekly_html, rsi_weekly_iframe_height
from stocks.strategies.rsi_weekly.service import (
    RSI_ENTRY,
    RSI_ENTRY_MAX,
    prepare_rsi_weekly_universe,
    run_rsi_weekly_scan,
)
from stocks.strategies.tq_bb.html import build_strategy_dashboard_html, strategy_iframe_height
from stocks.strategies.tq_bb.service import (
    prepare_strategy_universe,
    run_bb_strategy,
    run_tq_strategy,
    strategy_timeframe_options,
)
from stocks.strategies.tq_recovery.html import build_tq_recovery_html, tq_recovery_iframe_height
from stocks.strategies.tq_recovery.service import (
    prepare_tq_recovery_universe,
    run_tq_recovery_scan,
)


STRATEGY_OPTIONS = (
    "Both",
    "TQ",
    "Bollinger Bands",
    "TQ W52 Recovery",
    "RSI Weekly",
    "Above All EMAs",
)


def _prepare_quant_report(df: pd.DataFrame) -> pd.DataFrame:
    # Expand enrichment uses throttled Yahoo calls — keep separate from scan concurrency.
    return prepare_interactive_report_df(df, max_workers=8)


QUANT_HTML_CACHE_KEYS = {
    "ema": "strat_ema_html_v3",
    "rsi": "strat_rsi_html_v3",
    "recovery": "strat_recovery_html_v3",
    "tq_bb": "strat_tq_bb_html_v3",
}


def _embed_cached_quant_html(html_key: str, html: str, *, height: int) -> None:
    st.session_state[html_key] = html
    embed_html_iframe(html, height=height)


def _export_scan_csv(df: pd.DataFrame) -> bytes:
    export = df.copy()
    for col in ("snapshot", "quarters"):
        if col in export.columns:
            export = export.drop(columns=[col])
    return export.to_csv(index=False).encode("utf-8")


def render_strategy() -> None:
    tab_quant, tab_pead2, tab_ht, tab_gov = st.tabs(
        ["Quant Tab", "PEAD", "H&T", "Governance"]
    )

    with tab_quant:
        render_strategy_scan()

    with tab_pead2:
        from stocks.pages.pead2 import render_pead2

        render_pead2(show_title=False)
    with tab_ht:
        from stocks.pages.headwind_tailwind import render_headwind_tailwind

        render_headwind_tailwind()
    with tab_gov:
        from stocks.pages.governance import render_governance

        render_governance(show_title=False)

def _show_ema_daily_results(result: pd.DataFrame) -> None:
    st.caption(
        f"**{len(result):,}** stocks with daily close above EMA 20, 50, 100, and 200."
    )
    embed_html = build_ema_daily_html(result, standalone=False)
    _embed_cached_quant_html(QUANT_HTML_CACHE_KEYS["ema"], embed_html, height=ema_daily_iframe_height(len(result)))
    st.download_button(
        "Download CSV",
        data=_export_scan_csv(result),
        file_name="above_all_emas_daily.csv",
        mime="text/csv",
        key="strat_ema_csv",
    )


def _show_rsi_weekly_results(result: pd.DataFrame) -> None:
    st.caption(
        f"**{len(result):,}** stocks crossed RSI {RSI_ENTRY:g}–{RSI_ENTRY_MAX:g} this week."
    )
    embed_html = build_rsi_weekly_html(result, standalone=False)
    _embed_cached_quant_html(QUANT_HTML_CACHE_KEYS["rsi"], embed_html, height=rsi_weekly_iframe_height(len(result)))
    st.download_button(
        "Download CSV",
        data=_export_scan_csv(result),
        file_name="rsi_weekly.csv",
        mime="text/csv",
        key="strat_rsi_csv",
    )


def _show_tq_recovery_results(result: pd.DataFrame) -> None:
    embed_html = build_tq_recovery_html(result, standalone=False)
    _embed_cached_quant_html(
        QUANT_HTML_CACHE_KEYS["recovery"],
        embed_html,
        height=tq_recovery_iframe_height(len(result)),
    )
    st.download_button(
        "Download CSV",
        data=_export_scan_csv(result),
        file_name="tq_w52_recovery.csv",
        mime="text/csv",
        key="strat_recovery_csv",
    )


def _render_quant_cached_results(strategy_choice: str) -> None:
    if strategy_choice == "Above All EMAs":
        cached_html = st.session_state.get(QUANT_HTML_CACHE_KEYS["ema"])
        cached = st.session_state.get("strat_ema_result")
        if cached_html:
            if cached is not None and hasattr(cached, "__len__"):
                st.caption(
                    f"**{len(cached):,}** stocks with daily close above EMA 20, 50, 100, and 200."
                )
            _embed_cached_quant_html(
                QUANT_HTML_CACHE_KEYS["ema"],
                cached_html,
                height=ema_daily_iframe_height(len(cached) if cached is not None else 0),
            )
            if cached is not None and hasattr(cached, "empty") and not cached.empty:
                st.download_button(
                    "Download CSV",
                    data=_export_scan_csv(cached),
                    file_name="above_all_emas_daily.csv",
                    mime="text/csv",
                    key="strat_ema_csv",
                )
            return
        if cached is not None and hasattr(cached, "empty") and not cached.empty:
            _show_ema_daily_results(cached)
        return
    if strategy_choice == "RSI Weekly":
        cached_html = st.session_state.get(QUANT_HTML_CACHE_KEYS["rsi"])
        cached = st.session_state.get("strat_rsi_result")
        if cached_html:
            if cached is not None and hasattr(cached, "__len__"):
                st.caption(
                    f"**{len(cached):,}** stocks crossed RSI {RSI_ENTRY:g}–{RSI_ENTRY_MAX:g} this week."
                )
            _embed_cached_quant_html(
                QUANT_HTML_CACHE_KEYS["rsi"],
                cached_html,
                height=rsi_weekly_iframe_height(len(cached) if cached is not None else 0),
            )
            if cached is not None and hasattr(cached, "empty") and not cached.empty:
                st.download_button(
                    "Download CSV",
                    data=_export_scan_csv(cached),
                    file_name="rsi_weekly.csv",
                    mime="text/csv",
                    key="strat_rsi_csv",
                )
            return
        if cached is not None and hasattr(cached, "empty") and not cached.empty:
            _show_rsi_weekly_results(cached)
        return
    if strategy_choice == "TQ W52 Recovery":
        cached_html = st.session_state.get(QUANT_HTML_CACHE_KEYS["recovery"])
        cached = st.session_state.get("strat_recovery_result")
        if cached_html:
            _embed_cached_quant_html(
                QUANT_HTML_CACHE_KEYS["recovery"],
                cached_html,
                height=tq_recovery_iframe_height(len(cached) if cached is not None else 0),
            )
            if cached is not None and hasattr(cached, "empty") and not cached.empty:
                st.download_button(
                    "Download CSV",
                    data=_export_scan_csv(cached),
                    file_name="tq_w52_recovery.csv",
                    mime="text/csv",
                    key="strat_recovery_csv",
                )
            return
        if cached is not None and hasattr(cached, "empty") and not cached.empty:
            _show_tq_recovery_results(cached)


def _run_ema_daily_scan(filtered: pd.DataFrame, *, cap_tier_id: str) -> None:
    max_workers = int(st.session_state.strategy_max_workers)
    universe, _, _ = prepare_ema_daily_universe(filtered, cap_tier_id=cap_tier_id)
    if universe.empty:
        st.warning("No tickers in the selected universe.")
        return

    progress = st.progress(0, text="Above All EMAs scan...")
    try:

        def _progress(done: int, total: int) -> None:
            progress.progress(done / total, text=f"EMA daily {done}/{total}...")

        result = run_ema_daily_scan(
            universe,
            max_workers=max_workers,
            progress_callback=_progress,
            should_stop=lambda: st.session_state.get("strategy_scan_stop", False),
        )
    except Exception as exc:
        progress.empty()
        st.error(f"Above All EMAs scan failed: {exc}")
        return
    progress.empty()

    if result.empty:
        st.session_state.pop("strat_ema_result", None)
        st.warning(
            "No stocks with daily price above all four EMAs (20, 50, 100, 200) "
            "in the current selection."
        )
        return

    with st.spinner("Loading quarterly data & links..."):
        result = _prepare_quant_report(result)

    st.session_state.strat_ema_result = result
    _show_ema_daily_results(result)


def _run_tq_recovery_scan(filtered: pd.DataFrame, *, cap_tier_id: str) -> None:
    max_workers = int(st.session_state.strategy_max_workers)
    base_universe = analysis_universe(filtered, limit=0)
    universe, _, _ = prepare_tq_recovery_universe(base_universe, cap_tier_id=cap_tier_id)
    if universe.empty:
        st.warning("No tickers in the selected universe.")
        return

    progress = st.progress(0, text="TQ W52 recovery scan...")
    try:

        def _progress(done: int, total: int) -> None:
            progress.progress(done / total, text=f"TQ recovery {done}/{total}...")

        result = run_tq_recovery_scan(
            universe,
            max_workers=max_workers,
            progress_callback=_progress,
            should_stop=lambda: st.session_state.get("strategy_scan_stop", False),
        )
    except Exception as exc:
        progress.empty()
        st.error(f"TQ recovery scan failed: {exc}")
        return
    progress.empty()

    if result.empty:
        st.session_state.pop("strat_recovery_result", None)
        st.warning(
            "No stocks with TQ W52 red → yellow (below zero) in the current selection."
        )
        return

    with st.spinner("Loading quarterly data & links..."):
        result = _prepare_quant_report(result)

    st.session_state.strat_recovery_result = result
    _show_tq_recovery_results(result)


def _run_rsi_weekly_scan(filtered: pd.DataFrame, *, cap_tier_id: str) -> None:
    max_workers = int(st.session_state.strategy_max_workers)
    base_universe = analysis_universe(filtered, limit=0)
    universe, _, _ = prepare_rsi_weekly_universe(base_universe, cap_tier_id=cap_tier_id)
    if universe.empty:
        st.warning("No tickers in the selected universe.")
        return

    progress = st.progress(0, text="RSI weekly scan...")
    try:

        def _progress(done: int, total: int) -> None:
            progress.progress(done / total, text=f"RSI weekly {done}/{total}...")

        result = run_rsi_weekly_scan(
            universe,
            max_workers=max_workers,
            progress_callback=_progress,
            should_stop=lambda: st.session_state.get("strategy_scan_stop", False),
        )
    except Exception as exc:
        progress.empty()
        st.error(f"RSI weekly scan failed: {exc}")
        return
    progress.empty()

    if result.empty:
        st.session_state.pop("strat_rsi_result", None)
        st.warning(
            f"No stocks with a fresh weekly RSI cross in {RSI_ENTRY:g}–{RSI_ENTRY_MAX:g} this week."
        )
        return

    with st.spinner("Loading quarterly data & links..."):
        result = _prepare_quant_report(result)

    st.session_state.strat_rsi_result = result
    _show_rsi_weekly_results(result)


def render_strategy_scan() -> None:
    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    st.markdown("### Quant scan")

    with scan_toolbar_row(
        *base_scan_extra_widths(
            STRATEGY_CHOICE_COL_WIDTH,
            BB_TIMEFRAME_COL_WIDTH,
            WORKERS_COL_WIDTH,
            SCAN_BTN_COL_WIDTH,
            STOP_BTN_COL_WIDTH,
        )
    ) as row:
        filters, cap_tier_label_ui = render_base_scan_filters(
            stocks,
            row,
            key_prefix="strat",
            cap_tier_key="strat_cap_tier",
        )
        with row[4]:
            strategy_choice = st.selectbox(
                "Strategy",
                STRATEGY_OPTIONS,
                key="strat_choice",
                help=(
                    "TQ = trend quality · BB = Bollinger breakout · "
                    "W52 Recovery = weekly TQ red→yellow · RSI Weekly = fresh RSI 60–61 cross · "
                    "Above All EMAs = daily price above EMA 20/50/100/200"
                ),
            )
        with row[5]:
            tf_options = strategy_timeframe_options(strategy_choice)
            if st.session_state.get("strat_timeframe") not in tf_options:
                st.session_state["strat_timeframe"] = tf_options[0]
            scan_timeframe = st.selectbox(
                "Timeframe",
                tf_options,
                key="strat_timeframe",
                help=(
                    "TQ / BB timeframe · W52 Recovery and RSI Weekly use weekly · "
                    "Above All EMAs uses daily"
                ),
            )
        with row[6]:
            st.number_input(
                "Conc",
                min_value=1,
                max_value=STRATEGY_MAX_WORKERS_CAP,
                value=STRATEGY_MAX_WORKERS,
                step=1,
                key="strategy_max_workers",
                help="Parallel workers for **TQ** and throttled scans (PEAD, Earnings, Turtle). Max 32.",
            )
        with row[7]:
            run_clicked = st.button("Scan", type="primary", width="stretch", key="strat_scan")
        with row[8]:
            stop_clicked = st.button("Stop", width="stretch", key="strat_stop")

    cap_tier_id = resolve_cap_tier_id(filters.market, cap_tier_id_from_label(cap_tier_label_ui))
    filtered = apply_stock_filters(stocks, filters)

    if "strategy_scan_stop" not in st.session_state:
        st.session_state.strategy_scan_stop = False
    if stop_clicked:
        st.session_state.strategy_scan_stop = True

    if not run_clicked:
        _render_quant_cached_results(strategy_choice)
        return

    st.session_state.strategy_scan_stop = False

    if strategy_choice == "Above All EMAs":
        _run_ema_daily_scan(filtered, cap_tier_id=cap_tier_id)
        return
    if strategy_choice == "TQ W52 Recovery":
        _run_tq_recovery_scan(filtered, cap_tier_id=cap_tier_id)
        return
    if strategy_choice == "RSI Weekly":
        _run_rsi_weekly_scan(filtered, cap_tier_id=cap_tier_id)
        return

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
        with st.spinner("Loading quarterly data & links for TQ signals..."):
            tq_result = _prepare_quant_report(tq_result)
        saved_tq = save_strategy_tq_signals(tq_result, timeframe=scan_timeframe)
    else:
        saved_tq = 0
    if has_bb and not bb_result.empty:
        with st.spinner("Loading quarterly data & links for BB signals..."):
            bb_result = _prepare_quant_report(bb_result)
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
    st.session_state[QUANT_HTML_CACHE_KEYS["tq_bb"]] = embed_html
    _embed_cached_quant_html(
        QUANT_HTML_CACHE_KEYS["tq_bb"],
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
            data=_export_scan_csv(tq_result),
            file_name=f"strategy_tq_{scan_timeframe}.csv",
            mime="text/csv",
            key="download_tq_csv",
        )
    if has_bb and not bb_result.empty:
        st.download_button(
            f"Download BB ({scan_timeframe}) CSV",
            data=_export_scan_csv(bb_result),
            file_name=f"strategy_bb_{scan_timeframe}.csv",
            mime="text/csv",
            key="download_bb_csv",
        )
