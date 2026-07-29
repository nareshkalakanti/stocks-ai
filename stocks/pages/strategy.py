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
from stocks.strategies.base_breakout.html import (
    base_breakout_iframe_height,
    build_base_breakout_html,
)
from stocks.strategies.base_breakout.service import (
    prepare_base_breakout_universe,
    run_base_breakout_scan,
)
from stocks.strategies.rsi_weekly.html import build_rsi_weekly_html, rsi_weekly_iframe_height
from stocks.strategies.rsi_weekly.service import (
    RSI_ENTRY,
    RSI_ENTRY_MAX,
    prepare_rsi_weekly_universe,
    run_rsi_weekly_scan,
)
from stocks.strategies.factor.html import build_factor_html, factor_iframe_height
from stocks.strategies.factor.service import (
    prepare_factor_universe,
    run_factor_scan,
)
from stocks.strategies.low_vol.html import build_low_vol_html, low_vol_iframe_height
from stocks.strategies.low_vol.service import (
    prepare_low_vol_universe,
    run_low_vol_scan,
)
from stocks.strategies.cup_vcp.html import (
    build_cup_handle_html,
    build_vcp_html,
    pattern_scan_iframe_height,
)
from stocks.strategies.cup_vcp.service import (
    prepare_cup_handle_universe,
    prepare_vcp_universe,
    run_cup_handle_scan,
    run_vcp_scan,
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
    "Momentum",
    "Low Volatility",
    "Weekly Base Breakout",
    "Cup & Handle",
    "VCP",
)


STRATEGY_SECTIONS = (
    "Quant Tab",
    "PEAD",
    "H&T",
    "Governance",
)


@st.cache_data(ttl=120, show_spinner=False)
def _load_stocks_cached() -> pd.DataFrame:
    return load_india_stocks()


def _prepare_quant_report(df: pd.DataFrame) -> pd.DataFrame:
    # Expand: PEAD cache + Yahoo fill for quarters / website / snapshot.
    return prepare_interactive_report_df(df, max_workers=8)


def _prepare_pattern_report(df: pd.DataFrame) -> pd.DataFrame:
    """Same as full quant report — website + quarterly on expand."""
    return _prepare_quant_report(df)


QUANT_HTML_CACHE_KEYS = {
    "ema": "strat_ema_html_v4",
    "rsi": "strat_rsi_html_v4",
    "recovery": "strat_recovery_html_v4",
    "base_breakout": "strat_base_breakout_html_v3",
    "low_vol": "strat_low_vol_html_v2",
    "factor": "strat_factor_html_v8",
    "tq_bb": "strat_tq_bb_html_v4",
    "cup_handle": "strat_cup_handle_html_v5",
    "vcp": "strat_vcp_html_v4",
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
    if "strategy_section" not in st.session_state:
        st.session_state.strategy_section = STRATEGY_SECTIONS[0]

    section = st.radio(
        "Section",
        STRATEGY_SECTIONS,
        horizontal=True,
        label_visibility="collapsed",
        key="strategy_section",
    )

    if section == "Quant Tab":
        render_strategy_scan()
    elif section == "PEAD":
        from stocks.pages.pead2 import render_pead2

        render_pead2(show_title=False)
    elif section == "H&T":
        from stocks.pages.headwind_tailwind import render_headwind_tailwind

        render_headwind_tailwind()
    elif section == "Governance":
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


def _show_pattern_scan_results(
    result: pd.DataFrame,
    *,
    label: str,
    html_key: str,
    build_html,
    csv_name: str,
    csv_button_key: str,
) -> None:
    st.caption(
        f"**{len(result):,}** {label} · expand row for drawn chart · **TV** link to verify on TradingView."
    )
    embed_html = build_html(result, standalone=False)
    _embed_cached_quant_html(
        html_key,
        embed_html,
        height=pattern_scan_iframe_height(len(result)),
    )
    st.download_button(
        "Download CSV",
        data=_export_scan_csv(result),
        file_name=csv_name,
        mime="text/csv",
        key=csv_button_key,
    )


def _show_cup_handle_results(result: pd.DataFrame) -> None:
    tf = "weekly"
    if result is not None and not result.empty and "timeframe" in result.columns:
        tf = str(result["timeframe"].iloc[0] or "weekly")
    _show_pattern_scan_results(
        result,
        label=f"Cup & Handle setups ({tf})",
        html_key=QUANT_HTML_CACHE_KEYS["cup_handle"],
        build_html=build_cup_handle_html,
        csv_name=f"cup_handle_{tf}.csv",
        csv_button_key="strat_cup_handle_csv",
    )


def _show_vcp_results(result: pd.DataFrame) -> None:
    _show_pattern_scan_results(
        result,
        label="VCP setups",
        html_key=QUANT_HTML_CACHE_KEYS["vcp"],
        build_html=build_vcp_html,
        csv_name="vcp_daily.csv",
        csv_button_key="strat_vcp_csv",
    )


def _show_base_breakout_results(result: pd.DataFrame) -> None:
    st.caption(
        f"**{len(result):,}** Weekly Base Breakout setups · expand row for weekly base chart · **TV** link to verify."
    )
    embed_html = build_base_breakout_html(result, standalone=False)
    _embed_cached_quant_html(
        QUANT_HTML_CACHE_KEYS["base_breakout"],
        embed_html,
        height=base_breakout_iframe_height(len(result)),
    )
    st.download_button(
        "Download CSV",
        data=_export_scan_csv(result),
        file_name="weekly_base_breakout.csv",
        mime="text/csv",
        key="strat_base_breakout_csv",
    )


def _show_low_vol_results(result: pd.DataFrame) -> None:
    st.caption(
        f"**{len(result):,}** Low Volatility names (bottom 20% by ST+LT vol) · expand row · **TV** to verify."
    )
    embed_html = build_low_vol_html(result, standalone=False)
    _embed_cached_quant_html(
        QUANT_HTML_CACHE_KEYS["low_vol"],
        embed_html,
        height=low_vol_iframe_height(len(result)),
    )
    st.download_button(
        "Download CSV",
        data=_export_scan_csv(result),
        file_name="low_volatility.csv",
        mime="text/csv",
        key="strat_low_vol_csv",
    )


def _show_factor_results(result: pd.DataFrame) -> None:
    st.caption(
        f"**{len(result):,}** Momentum names (all, sorted by 12–1) · expand row · website · quarterly · **TV**."
    )
    embed_html = build_factor_html(result, standalone=False)
    _embed_cached_quant_html(
        QUANT_HTML_CACHE_KEYS["factor"],
        embed_html,
        height=factor_iframe_height(len(result)),
    )
    st.download_button(
        "Download CSV",
        data=_export_scan_csv(result),
        file_name="momentum.csv",
        mime="text/csv",
        key="strat_momentum_csv",
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
    if strategy_choice == "Cup & Handle":
        cached_html = st.session_state.get(QUANT_HTML_CACHE_KEYS["cup_handle"])
        cached = st.session_state.get("strat_cup_handle_result")
        if cached_html:
            if cached is not None and hasattr(cached, "__len__"):
                st.caption(
                    f"**{len(cached):,}** Cup & Handle setups · expand row · TV to verify."
                )
            _embed_cached_quant_html(
                QUANT_HTML_CACHE_KEYS["cup_handle"],
                cached_html,
                height=pattern_scan_iframe_height(len(cached) if cached is not None else 0),
            )
            if cached is not None and hasattr(cached, "empty") and not cached.empty:
                st.download_button(
                    "Download CSV",
                    data=_export_scan_csv(cached),
                    file_name="cup_handle_daily.csv",
                    mime="text/csv",
                    key="strat_cup_handle_csv",
                )
            return
        if cached is not None and hasattr(cached, "empty") and not cached.empty:
            _show_cup_handle_results(cached)
        return
    if strategy_choice == "VCP":
        cached_html = st.session_state.get(QUANT_HTML_CACHE_KEYS["vcp"])
        cached = st.session_state.get("strat_vcp_result")
        if cached_html:
            if cached is not None and hasattr(cached, "__len__"):
                st.caption(
                    f"**{len(cached):,}** VCP setups (daily) · expand row · TV to verify."
                )
            _embed_cached_quant_html(
                QUANT_HTML_CACHE_KEYS["vcp"],
                cached_html,
                height=pattern_scan_iframe_height(len(cached) if cached is not None else 0),
            )
            if cached is not None and hasattr(cached, "empty") and not cached.empty:
                st.download_button(
                    "Download CSV",
                    data=_export_scan_csv(cached),
                    file_name="vcp_daily.csv",
                    mime="text/csv",
                    key="strat_vcp_csv",
                )
            return
        if cached is not None and hasattr(cached, "empty") and not cached.empty:
            _show_vcp_results(cached)
        return
    if strategy_choice == "Weekly Base Breakout":
        cached_html = st.session_state.get(QUANT_HTML_CACHE_KEYS["base_breakout"])
        cached = st.session_state.get("strat_base_breakout_result")
        if cached_html:
            if cached is not None and hasattr(cached, "__len__"):
                st.caption(
                    f"**{len(cached):,}** Weekly Base Breakout setups · expand row · TV to verify."
                )
            _embed_cached_quant_html(
                QUANT_HTML_CACHE_KEYS["base_breakout"],
                cached_html,
                height=base_breakout_iframe_height(len(cached) if cached is not None else 0),
            )
            if cached is not None and hasattr(cached, "empty") and not cached.empty:
                st.download_button(
                    "Download CSV",
                    data=_export_scan_csv(cached),
                    file_name="weekly_base_breakout.csv",
                    mime="text/csv",
                    key="strat_base_breakout_csv",
                )
            return
        if cached is not None and hasattr(cached, "empty") and not cached.empty:
            _show_base_breakout_results(cached)
        return
    if strategy_choice == "Low Volatility":
        cached_html = st.session_state.get(QUANT_HTML_CACHE_KEYS["low_vol"])
        cached = st.session_state.get("strat_low_vol_result")
        if cached_html:
            if cached is not None and hasattr(cached, "__len__"):
                st.caption(
                    f"**{len(cached):,}** Low Volatility names · expand row · TV to verify."
                )
            _embed_cached_quant_html(
                QUANT_HTML_CACHE_KEYS["low_vol"],
                cached_html,
                height=low_vol_iframe_height(len(cached) if cached is not None else 0),
            )
            if cached is not None and hasattr(cached, "empty") and not cached.empty:
                st.download_button(
                    "Download CSV",
                    data=_export_scan_csv(cached),
                    file_name="low_volatility.csv",
                    mime="text/csv",
                    key="strat_low_vol_csv",
                )
            return
        if cached is not None and hasattr(cached, "empty") and not cached.empty:
            _show_low_vol_results(cached)
        return
    if strategy_choice == "Momentum":
        cached_html = st.session_state.get(QUANT_HTML_CACHE_KEYS["factor"])
        cached = st.session_state.get("strat_factor_result")
        if cached_html:
            if cached is not None and hasattr(cached, "__len__"):
                st.caption(
                    f"**{len(cached):,}** Momentum names · expand row · website · quarterly · TV."
                )
            _embed_cached_quant_html(
                QUANT_HTML_CACHE_KEYS["factor"],
                cached_html,
                height=factor_iframe_height(len(cached) if cached is not None else 0),
            )
            if cached is not None and hasattr(cached, "empty") and not cached.empty:
                st.download_button(
                    "Download CSV",
                    data=_export_scan_csv(cached),
                    file_name="momentum.csv",
                    mime="text/csv",
                    key="strat_momentum_csv",
                )
            return
        if cached is not None and hasattr(cached, "empty") and not cached.empty:
            _show_factor_results(cached)
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

    with st.spinner("Loading website, quarterly data & links..."):
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

    with st.spinner("Loading website, quarterly data & links..."):
        result = _prepare_quant_report(result)

    st.session_state.strat_recovery_result = result
    _show_tq_recovery_results(result)


def _run_pattern_scan(
    filtered: pd.DataFrame,
    *,
    cap_tier_id: str,
    label: str,
    run_scan,
    prepare_universe,
    empty_message: str,
    session_key: str,
    show_results,
    scan_kwargs: dict | None = None,
) -> None:
    max_workers = int(st.session_state.strategy_max_workers)
    base_universe = analysis_universe(filtered, limit=0)
    universe, _, _ = prepare_universe(base_universe, cap_tier_id=cap_tier_id)
    if universe.empty:
        st.warning("No tickers in the selected universe.")
        return

    progress = st.progress(0, text=f"{label} scan...")
    extra = dict(scan_kwargs or {})

    try:

        def _progress(done: int, total: int) -> None:
            progress.progress(done / total, text=f"{label} {done}/{total}...")

        result = run_scan(
            universe,
            max_workers=max_workers,
            progress_callback=_progress,
            should_stop=lambda: st.session_state.get("strategy_scan_stop", False),
            **extra,
        )
    except Exception as exc:
        progress.empty()
        st.error(f"{label} scan failed: {exc}")
        return
    progress.empty()

    if result.empty:
        st.session_state.pop(session_key, None)
        st.warning(empty_message)
        return

    with st.spinner("Loading website, quarterly data & links..."):
        result = _prepare_pattern_report(result)

    st.session_state[session_key] = result
    show_results(result)


def _run_cup_handle_scan(
    filtered: pd.DataFrame,
    *,
    cap_tier_id: str,
    timeframe: str = "weekly",
) -> None:
    tf = timeframe if timeframe in {"daily", "weekly"} else "weekly"
    _run_pattern_scan(
        filtered,
        cap_tier_id=cap_tier_id,
        label=f"Cup & Handle ({tf})",
        run_scan=run_cup_handle_scan,
        prepare_universe=prepare_cup_handle_universe,
        empty_message=f"No Cup & Handle setups near rim ({tf}) in the current selection.",
        session_key="strat_cup_handle_result",
        show_results=_show_cup_handle_results,
        scan_kwargs={"timeframe": tf},
    )


def _run_vcp_scan(filtered: pd.DataFrame, *, cap_tier_id: str) -> None:
    _run_pattern_scan(
        filtered,
        cap_tier_id=cap_tier_id,
        label="VCP",
        run_scan=run_vcp_scan,
        prepare_universe=prepare_vcp_universe,
        empty_message="No VCP setups near pivot in the current selection.",
        session_key="strat_vcp_result",
        show_results=_show_vcp_results,
    )


def _run_base_breakout_scan(filtered: pd.DataFrame, *, cap_tier_id: str) -> None:
    _run_pattern_scan(
        filtered,
        cap_tier_id=cap_tier_id,
        label="Weekly Base Breakout",
        run_scan=run_base_breakout_scan,
        prepare_universe=prepare_base_breakout_universe,
        empty_message="No weekly base breakout setups near pivot in the current selection.",
        session_key="strat_base_breakout_result",
        show_results=_show_base_breakout_results,
    )


def _run_low_vol_scan(filtered: pd.DataFrame, *, cap_tier_id: str) -> None:
    _run_pattern_scan(
        filtered,
        cap_tier_id=cap_tier_id,
        label="Low Volatility",
        run_scan=run_low_vol_scan,
        prepare_universe=prepare_low_vol_universe,
        empty_message="No low-volatility names in the current selection.",
        session_key="strat_low_vol_result",
        show_results=_show_low_vol_results,
    )


def _run_factor_scan(filtered: pd.DataFrame, *, cap_tier_id: str) -> None:
    _run_pattern_scan(
        filtered,
        cap_tier_id=cap_tier_id,
        label="Momentum",
        run_scan=run_factor_scan,
        prepare_universe=prepare_factor_universe,
        empty_message="No momentum names in the current selection.",
        session_key="strat_factor_result",
        show_results=_show_factor_results,
    )


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

    with st.spinner("Loading website, quarterly data & links..."):
        result = _prepare_quant_report(result)

    st.session_state.strat_rsi_result = result
    _show_rsi_weekly_results(result)


def render_strategy_scan() -> None:
    try:
        stocks = _load_stocks_cached()
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
                    "Momentum = all names by 12–1 return · "
                    "Low Volatility = bottom 20% short+long realized vol · "
                    "Weekly Base Breakout = long consolidation near breakout · "
                    "Cup & Handle = weekly (or daily) pattern · VCP = daily · TV in report"
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
                    "Cup & Handle defaults to weekly (daily also available) · "
                    "Weekly Base Breakout / RSI / W52 use weekly · "
                    "Above All EMAs, Momentum, Low Volatility, and VCP use daily"
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
    if strategy_choice == "Weekly Base Breakout":
        _run_base_breakout_scan(filtered, cap_tier_id=cap_tier_id)
        return
    if strategy_choice == "Low Volatility":
        _run_low_vol_scan(filtered, cap_tier_id=cap_tier_id)
        return
    if strategy_choice == "Momentum":
        _run_factor_scan(filtered, cap_tier_id=cap_tier_id)
        return
    if strategy_choice == "Cup & Handle":
        _run_cup_handle_scan(
            filtered, cap_tier_id=cap_tier_id, timeframe=scan_timeframe
        )
        return
    if strategy_choice == "VCP":
        _run_vcp_scan(filtered, cap_tier_id=cap_tier_id)
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
        with st.spinner("Loading website, quarterly data & links for TQ signals..."):
            tq_result = _prepare_quant_report(tq_result)
        saved_tq = save_strategy_tq_signals(tq_result, timeframe=scan_timeframe)
    else:
        saved_tq = 0
    if has_bb and not bb_result.empty:
        with st.spinner("Loading website, quarterly data & links for BB signals..."):
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
