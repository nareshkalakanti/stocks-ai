import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    PEAD2_CACHE_HOURS,
    PEAD2_REPORT_MAX_ROWS,
    cap_tier_id_from_label,
)
from stocks.market.fundamentals_service import cap_tier_label
from stocks.strategies.pead2.html import (
    build_pead2_dashboard_html,
    limit_pead_report_df,
    pead2_iframe_height,
)
from stocks.strategies.pead2.service import (
    Pead2ScanCoverage,
    expand_pead_candidates_to_universe,
    pead2_scan_coverage,
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

_DISPLAY_KEY = "pead2_display_cache_key_v3"
_DISPLAY_DF = "pead2_display_df_v3"


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
    coverage = pead2_scan_coverage(universe)
    st.session_state.pead2_universe = universe
    st.session_state.pead2_coverage = coverage
    st.session_state.pead2_universe_key = filter_key
    return universe, coverage


def _invalidate_pead_display_cache() -> None:
    st.session_state.pop(_DISPLAY_KEY, None)
    st.session_state.pop(_DISPLAY_DF, None)


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


def _hydrate_candidates_from_cache(universe: pd.DataFrame) -> dict | None:
    """Score from SQLite only (no Yahoo). Used when Market/Cap changes and Scan wasn't clicked yet."""
    if universe is None or universe.empty:
        return None
    try:
        return run_pead2_scan(
            universe,
            only_pending=True,
            max_fetch=0,
            check_breakouts=False,
            skip_returns_refresh=True,
        )
    except Exception as exc:
        st.warning(f"Could not load PEAD from cache: {exc}")
        return None


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
        filter_changed = st.session_state.get("pead2_filter_key") != filter_key
        if filter_changed:
            st.session_state.pead2_filter_key = filter_key
            # Do NOT clear candidates here — hydrate below replaces them so the
            # board never flashes empty when Cap / Market changes.
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
                width="stretch",
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

    # Cap/Market change (or empty session): load this filter from SQLite only.
    # Replace in place so the UI never goes blank while cache has scores.
    need_hydrate = filter_changed or candidates is None or (
        isinstance(candidates, pd.DataFrame) and candidates.empty
    )
    if need_hydrate and not universe.empty:
        cov = coverage if isinstance(coverage, Pead2ScanCoverage) else pead2_scan_coverage(universe)
        st.caption(
            f"**{cov.universe_total:,}** in filter · **{cov.scorable:,}** scored in cache · "
            f"**{cov.missing:,}** never fetched · **{cov.stale:,}** stale"
        )
        if cov.scorable > 0:
            with st.spinner(
                f"Loading PEAD from cache ({cov.scorable:,} of {cov.universe_total:,})…"
            ):
                cached_result = _hydrate_candidates_from_cache(universe)
            if cached_result is not None:
                _store_scan_result(cached_result)
                candidates = st.session_state.get("pead2_candidates")
                candidates_previous = st.session_state.get("pead2_candidates_previous")
                cov2 = cached_result.get("coverage")
                if isinstance(cov2, Pead2ScanCoverage):
                    coverage = cov2
                    st.session_state.pead2_coverage = cov2
                st.caption(
                    f"Loaded **{int(cached_result.get('cache_hits') or 0):,}** from PEAD cache · "
                    f"click **Scan** only to refresh Yahoo / fill gaps."
                )
            else:
                st.session_state.pop("pead2_candidates", None)
                st.session_state.pop("pead2_candidates_previous", None)
                candidates = None
                candidates_previous = None
        else:
            st.session_state.pop("pead2_candidates", None)
            st.session_state.pop("pead2_candidates_previous", None)
            candidates = None
            candidates_previous = None

    if candidates is None:
        cov = coverage if isinstance(coverage, Pead2ScanCoverage) else None
        if cov and cov.universe_total:
            st.info(
                f"**{cov.universe_total:,}** stocks in filter · "
                f"**{cov.scorable:,}** scorable in cache · "
                f"**{cov.missing:,}** never fetched · "
                f"**{cov.stale:,}** stale. "
                f"Click **Scan** to load / refresh."
            )
        else:
            st.caption("Set filters, then click **Scan**.")
        return

    if candidates.empty:
        if int(st.session_state.get("pead2_results_gen") or 0) > 0:
            st.warning(
                "No PEAD-scorable rows matched this filter. "
                "Try widening **Cap** / **Sector**, or click **Scan** after cache fills."
            )
        else:
            st.caption("Set filters, then click **Scan**.")
        return

    display_key = _display_cache_key(filter_key, holdings_view=holdings_view)
    cached_display = st.session_state.get(_DISPLAY_DF)
    if (
        st.session_state.get(_DISPLAY_KEY) == display_key
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
        st.session_state[_DISPLAY_DF] = {
            "current": candidates,
            "previous": prev_df,
        }
        st.session_state[_DISPLAY_KEY] = display_key

    cache_hits = int(st.session_state.get("pead2_cache_hits") or 0)
    scored_n = (
        int(candidates["pead_score"].notna().sum())
        if "pead_score" in candidates.columns
        else len(candidates)
    )
    def _flag_count(col: str) -> int:
        if col not in candidates.columns:
            return 0
        s = candidates[col]
        return int(sum(bool(v) for v in s.tolist() if v is not None and v == v))

    tq_n = _flag_count("has_tq")
    bb_n = _flag_count("has_bb")

    html_cache_key = (
        display_key,
        len(candidates),
        scored_n,
        holdings_view,
    )
    del html_cache_key  # HTML rebuilt each run — do not cache multi-MB strings in session

    report_df, report_total = limit_pead_report_df(candidates, PEAD2_REPORT_MAX_ROWS)
    report_prev, _ = limit_pead_report_df(prev_df, PEAD2_REPORT_MAX_ROWS)

    with st.spinner("Building PEAD report…"):
        try:
            embed_html = build_pead2_dashboard_html(
                report_df,
                df_previous=report_prev,
                title="Holdings PEAD" if holdings_view else "Top PEAD Candidates",
                list_label="Holdings" if holdings_view else "PEAD candidates",
                show_scored_split=holdings_view,
                standalone=True,
                variant="holdings" if holdings_view else "pead2",
                report_total=report_total,
                max_rows=PEAD2_REPORT_MAX_ROWS,
            )
        except Exception as exc:
            st.error(f"Could not build PEAD report: {exc}")
            return

    if len(embed_html) >= 2_000_000:
        st.caption(
            f"Report capped at **{len(report_df):,}** rows "
            f"(of **{report_total:,}** scanned) so the dashboard loads reliably. "
            f"Use **Download PEAD CSV** for the full list."
        )

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
        height=pead2_iframe_height(len(report_df)),
        static_stem="pead",
    )

    csv = format_pead_export_df(candidates).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download PEAD CSV",
        data=csv,
        file_name="pead_candidates.csv",
        mime="text/csv",
    )
