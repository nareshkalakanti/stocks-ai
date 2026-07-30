import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    PEAD2_CACHE_HOURS,
    cap_tier_id_from_label,
)
from stocks.market.fundamentals_service import cap_tier_label
from stocks.strategies.pead2.html import build_pead2_dashboard_html, pead2_iframe_height
from stocks.strategies.pead2.service import (
    Pead2ScanCoverage,
    expand_pead_candidates_to_universe,
    prepare_pead_universe,
    refresh_pead2_returns_only,
    run_pead2_scan,
)
from stocks.strategies.pead2.strategy import (
    attach_strategy_breakout_signals,
    enrich_pead_candidates,
    format_pead_export_df,
)
from stocks.scans.holdings_playlist import is_holdings_playlist
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
from stocks.pages.stocks_cache import load_stocks_cached

_PEAD2_HTML_KEY = "pead2_html_cache_key"
_PEAD2_HTML_BODY = "pead2_embed_html_v2"
_PEAD2_DISPLAY_KEY = "pead2_display_cache_key"
_PEAD2_DISPLAY_DF = "pead2_display_df_v2"


def _inject_pead_scan_css() -> None:
    if st.session_state.get("_pead_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_pead_scan_css"] = True


def _pead_filter_key(
    filters,
    *,
    cap_tier_id: str,
) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
    )


def _resolve_universe_and_coverage(
    filtered: pd.DataFrame,
    *,
    cap_tier_id: str,
    filter_key: tuple,
) -> tuple[pd.DataFrame, Pead2ScanCoverage]:
    if st.session_state.get("pead2_universe_key") == filter_key:
        universe = st.session_state.get("pead2_universe")
        coverage = st.session_state.get("pead2_coverage")
        if universe is not None and isinstance(coverage, Pead2ScanCoverage):
            return universe, coverage

    universe, _, _ = prepare_pead_universe(filtered, cap_tier_id=cap_tier_id)
    from stocks.strategies.pead2.service import pead2_scan_coverage

    coverage = pead2_scan_coverage(universe)
    st.session_state.pead2_universe = universe
    st.session_state.pead2_coverage = coverage
    st.session_state.pead2_universe_key = filter_key
    return universe, coverage


def _invalidate_pead_html_cache() -> None:
    st.session_state.pop(_PEAD2_HTML_KEY, None)
    st.session_state.pop(_PEAD2_HTML_BODY, None)


def _invalidate_pead_display_cache() -> None:
    _invalidate_pead_html_cache()
    st.session_state.pop(_PEAD2_DISPLAY_KEY, None)
    st.session_state.pop(_PEAD2_DISPLAY_DF, None)


def _store_scan_result(result: dict) -> None:
    st.session_state.pead2_candidates = result["candidates"]
    st.session_state.pead2_candidates_previous = result.get(
        "candidates_previous", pd.DataFrame()
    )
    st.session_state.pead2_cache_hits = int(result.get("cache_hits") or 0)
    st.session_state.pead2_results_gen = int(
        st.session_state.get("pead2_results_gen", 0)
    ) + 1
    _invalidate_pead_display_cache()


def _display_cache_key(
    filter_key: tuple,
    *,
    holdings_view: bool,
) -> tuple:
    return (
        filter_key,
        holdings_view,
        int(st.session_state.get("pead2_results_gen", 0)),
    )


def _prepare_display_frames(
    candidates: pd.DataFrame,
    candidates_previous: pd.DataFrame | None,
    universe: pd.DataFrame,
    *,
    holdings_view: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = candidates
    prev = (
        candidates_previous
        if candidates_previous is not None and not candidates_previous.empty
        else pd.DataFrame()
    )
    if holdings_view and not universe.empty:
        work = expand_pead_candidates_to_universe(universe, work)
        prev = (
            expand_pead_candidates_to_universe(universe, prev)
            if not prev.empty
            else expand_pead_candidates_to_universe(universe, pd.DataFrame())
        )
    work = enrich_pead_candidates(work)
    work = attach_strategy_breakout_signals(work)
    if not prev.empty:
        prev = attach_strategy_breakout_signals(enrich_pead_candidates(prev))
    return work, prev


def _clear_pead2_refresh_query() -> None:
    if st.query_params.get("pead2_refresh") != "1":
        return
    params = {k: v for k, v in st.query_params.items() if k != "pead2_refresh"}
    st.query_params.from_dict(params)


def _run_scan(
    universe: pd.DataFrame,
    *,
    min_mcap_cr: float | None,
    status_slot=None,
) -> dict | None:
    host = status_slot if status_slot is not None else st
    progress = host.progress(0, text="PEAD — loading from DB...")

    def _progress(done: int, total: int, phase: str = "pead") -> None:
        labels = {
            "pead": "PEAD fetch",
            "returns": "Returns refresh",
            "breakouts": "BB+TQ weekly",
            "persist": "Saving TQ/BB",
        }
        label = labels.get(phase, "PEAD")
        if total <= 0:
            progress.progress(1.0, text=f"{label}…")
            return
        progress.progress(
            min(done / total, 1.0),
            text=f"{label} {done:,}/{total:,}…",
        )

    try:
        result = run_pead2_scan(
            universe,
            progress_callback=_progress,
            min_mcap_cr=min_mcap_cr,
        )
    except Exception as exc:
        progress.empty()
        host.error(f"PEAD scan failed: {exc}")
        return None
    progress.empty()
    return result


def render_pead2(*, show_title: bool = True) -> None:
    _inject_pead_scan_css()

    try:
        stocks = load_stocks_cached()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    if show_title:
        st.markdown("### PEAD")

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui = render_base_scan_filters(
            stocks,
            row,
            key_prefix="pead2",
            cap_tier_key="pead2_cap_tier",
        )
        cap_tier_id = resolve_cap_tier_id(filters.market, cap_tier_id_from_label(cap_tier_label_ui))
        min_mcap_cr = cap_tier_min_mcap_cr(cap_tier_id)
        filtered = apply_stock_filters(stocks, filters)

        filter_key = _pead_filter_key(
            filters,
            cap_tier_id=cap_tier_id,
        )
        if st.session_state.get("pead2_filter_key") != filter_key:
            st.session_state.pead2_filter_key = filter_key
            st.session_state.pop("pead2_candidates", None)
            st.session_state.pop("pead2_universe_key", None)
            _invalidate_pead_display_cache()

        universe, coverage = _resolve_universe_and_coverage(
            filtered,
            cap_tier_id=cap_tier_id,
            filter_key=filter_key,
        )

        with row[4]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                use_container_width=True,
                key="pead2_scan",
                help=(
                    f"Fetch missing or cache older than {PEAD2_CACHE_HOURS}h from Yahoo, "
                    "refresh returns (aged rows only), score PEAD, then check BB/TQ weekly."
                ),
            )

    holdings_view = is_holdings_playlist(filters.market)

    if st.query_params.get("pead2_refresh") == "1":
        _clear_pead2_refresh_query()
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return
        status_slot = st.empty()
        with status_slot.container():
            st.info("Refreshing returns from Yahoo...")
        try:
            result = refresh_pead2_returns_only(universe)
        except Exception as exc:
            status_slot.empty()
            st.error(f"Returns refresh failed: {exc}")
            return
        status_slot.empty()
        _store_scan_result(result)
        coverage = result.get("coverage")
        if isinstance(coverage, Pead2ScanCoverage):
            st.session_state.pead2_coverage = coverage
        st.caption("Returns refreshed from latest Yahoo prices.")
        st.rerun()

    if run_clicked:
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        status_slot = st.empty()
        with status_slot.container():
            st.info("Running PEAD scan...")

        result = _run_scan(
            universe,
            min_mcap_cr=min_mcap_cr,
            status_slot=status_slot,
        )
        status_slot.empty()
        if result is None:
            return
        _store_scan_result(result)
        coverage = result.get("coverage")
        if isinstance(coverage, Pead2ScanCoverage):
            st.session_state.pead2_coverage = coverage
        st.session_state.pead2_universe_key = filter_key

        fetched = int(result.get("fetched") or 0)
        if fetched > 0:
            st.caption(
                f"Updated **{int(result.get('saved') or 0):,}** tickers from Yahoo "
                f"({fetched:,} tried)."
            )

    candidates = st.session_state.get("pead2_candidates")
    candidates_previous = st.session_state.get("pead2_candidates_previous")

    if candidates is None:
        st.caption("Set filters, then click **Scan**.")
        return

    if candidates.empty:
        st.caption("Set filters, then click **Scan**.")
        return

    display_key = _display_cache_key(filter_key, holdings_view=holdings_view)
    cached_display = st.session_state.get(_PEAD2_DISPLAY_DF)
    if (
        st.session_state.get(_PEAD2_DISPLAY_KEY) == display_key
        and isinstance(cached_display, dict)
        and "current" in cached_display
    ):
        candidates = cached_display["current"]
        prev_df = cached_display.get("previous", pd.DataFrame())
    else:
        candidates, prev_df = _prepare_display_frames(
            candidates,
            candidates_previous,
            universe,
            holdings_view=holdings_view,
        )
        st.session_state[_PEAD2_DISPLAY_DF] = {
            "current": candidates,
            "previous": prev_df,
        }
        st.session_state[_PEAD2_DISPLAY_KEY] = display_key
        _invalidate_pead_html_cache()

    cache_hits = int(st.session_state.get("pead2_cache_hits") or 0)
    scored_n = (
        int(candidates["pead_score"].notna().sum())
        if "pead_score" in candidates.columns
        else len(candidates)
    )
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

    html_cache_key = (
        display_key,
        len(candidates),
        scored_n,
        holdings_view,
    )
    embed_html = None
    if st.session_state.get(_PEAD2_HTML_KEY) == html_cache_key:
        embed_html = st.session_state.get(_PEAD2_HTML_BODY)

    if not embed_html:
        with st.spinner("Building PEAD report…"):
            embed_html = build_pead2_dashboard_html(
                candidates,
                df_previous=prev_df,
                title="Holdings PEAD" if holdings_view else "Top PEAD Candidates",
                list_label="Holdings" if holdings_view else "PEAD candidates",
                show_scored_split=holdings_view,
                standalone=False,
            )
        st.session_state[_PEAD2_HTML_KEY] = html_cache_key
        st.session_state[_PEAD2_HTML_BODY] = embed_html

    if holdings_view:
        no_data_n = coverage.no_data if isinstance(coverage, Pead2ScanCoverage) else 0
        tier_note = (
            f" · **{cap_tier_label(cap_tier_id)}**"
            if cap_tier_id not in ("all", "", None)
            else ""
        )
        st.caption(
            f"{len(candidates)} holdings{tier_note} · **{scored_n:,}** with PEAD scores · "
            f"**{no_data_n:,}** without quarterly data · "
            f"TQ **{tq_n}** · BB **{bb_n}** · "
            f"{cache_hits:,} loaded from DB · "
            f"**search** in the results table · "
            f"filter **TQ / BB NEW** in the toolbar · "
            f"**click a row** to expand the detail panel."
        )
    else:
        st.caption(
            f"{len(candidates)} stocks · {cache_hits:,} from DB · "
            f"TQ weekly **{tq_n}** · BB NEW **{bb_n}** · "
            f"sorted by **latest result date** · "
            f"**search** in the results table · "
            f"filter **TQ / BB NEW** in the toolbar · "
            f"**click a row** to expand the detail panel."
        )
    embed_html_iframe(
        embed_html,
        height=pead2_iframe_height(len(candidates)),
    )

    csv = format_pead_export_df(candidates).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download PEAD CSV",
        data=csv,
        file_name="pead_candidates.csv",
        mime="text/csv",
    )
