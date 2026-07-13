import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    PEAD2_RECENT_MAX_FETCH,
    cap_tier_id_from_label,
)
from stocks.strategies.pead2.html import build_pead2_dashboard_html, pead2_iframe_height
from stocks.strategies.pead2.service import (
    Pead2ScanCoverage,
    PendingFetchMode,
    pead2_scan_coverage,
    prepare_pead_universe,
    run_pead2_scan,
)
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


def _render_ff_score_reference() -> None:
    from stocks.strategies.pead2.validation_refs import ff_monitor_score_comparison

    with st.expander("FF PEAD score test · KPL & WPIL"):
        st.caption(
            "FinanciallyFree monitor screenshots (Jul 2026). "
            "Compare our FF-mode score vs their PEAD. "
            "Run `pytest tests/test_pead_validation.py::TestPeadFfMonitorJul2026 -q`"
        )
        tab_card, tab_row = st.tabs(["Monitor card", "Dashboard row"])
        with tab_card:
            st.dataframe(
                ff_monitor_score_comparison(use_dashboard=False),
                use_container_width=True,
                hide_index=True,
            )
        with tab_row:
            st.dataframe(
                ff_monitor_score_comparison(use_dashboard=True),
                use_container_width=True,
                hide_index=True,
            )


_PEAD_SCAN_CSS = """
<style>
.st-key-pead2_scan button,
.st-key-pead2_fetch_missing button,
.st-key-pead2_fetch_stale button,
.st-key-pead2_fetch_toggle button {
  min-height: 1.55rem;
  padding: 0.08rem 0.4rem;
  font-size: 0.72rem;
  font-weight: 600;
  border-radius: 6px;
  white-space: nowrap;
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) {
  margin: 0.15rem 0 0.35rem;
  border-radius: 8px;
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) details {
  border: 1px solid rgba(49, 51, 63, 0.12);
  border-radius: 8px;
  background: rgba(250, 250, 252, 0.6);
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) summary {
  padding: 0.28rem 0.55rem;
  font-size: 0.76rem;
  font-weight: 500;
  min-height: unset;
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) [data-testid="stExpanderDetails"] {
  padding: 0.15rem 0.55rem 0.45rem;
  border-top: 1px solid rgba(49, 51, 63, 0.08);
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) [data-testid="stProgress"] {
  margin: 0;
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) [data-testid="stProgress"] > div {
  height: 0.35rem;
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) [data-testid="stProgress"] label {
  font-size: 0.64rem;
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) [data-testid="stNumberInput"] input {
  min-height: 1.45rem;
  font-size: 0.76rem;
  padding: 0.08rem 0.3rem;
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) [data-testid="stWidgetLabel"] p {
  font-size: 0.68rem;
  margin-bottom: 0.05rem;
}
div[data-testid="stExpander"]:has(.pead-fetch-panel) [data-testid="stCaptionContainer"] p {
  font-size: 0.68rem;
  margin: 0;
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


def _store_scan_result(result: dict) -> None:
    st.session_state.pead2_candidates = result["candidates"]
    st.session_state.pead2_candidates_previous = result.get(
        "candidates_previous", pd.DataFrame()
    )
    st.session_state.pead2_cache_hits = int(result.get("cache_hits") or 0)


def _sync_fetch_baselines(filter_key: tuple, coverage: Pead2ScanCoverage) -> dict[str, int]:
    """Track starting queue sizes so progress bars move as batches complete."""
    baselines = st.session_state.get("pead2_fetch_baselines")
    if baselines is None or baselines.get("filter_key") != filter_key:
        baselines = {
            "filter_key": filter_key,
            "missing": coverage.pending_count("missing"),
            "stale": coverage.pending_count("stale"),
        }
        st.session_state.pead2_fetch_baselines = baselines
        st.session_state.pop("pead2_last_fetch", None)
    return baselines


def _queue_pead_fetch(mode: PendingFetchMode) -> None:
    st.session_state.pead2_fetch_queue = mode


def _bucket_progress(done: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return min(max(done / total, 0.0), 1.0)


def _render_bucket_progress(remaining: int, baseline: int) -> None:
    done = max(baseline - remaining, 0)
    st.progress(
        _bucket_progress(done, baseline),
        text=f"{done:,}/{baseline:,} saved · {remaining:,} left",
    )


def _render_last_fetch_status(filter_key: tuple) -> None:
    last = st.session_state.get("pead2_last_fetch")
    if not isinstance(last, dict) or last.get("filter_key") != filter_key:
        return
    mode = last.get("mode")
    label = "New" if mode == "missing" else "Stale"
    delta = int(last["remaining_before"]) - int(last["remaining_after"])
    cleared = int(last.get("cleared") or last.get("saved") or 0)
    saved = int(last.get("saved") or 0)
    st.caption(
        f"Last {label} batch: {last['fetched']:,} tried · **{cleared:,} cleared** "
        f"({saved:,} with PEAD data) · queue **−{delta:,}** → **{last['remaining_after']:,}** left"
    )


def _run_scan(
    universe: pd.DataFrame,
    *,
    min_mcap_cr: float | None,
    only_pending: bool,
    pending_mode: PendingFetchMode,
    max_fetch: int | None = None,
    status_slot=None,
) -> dict | None:
    host = status_slot if status_slot is not None else st
    progress = host.progress(0, text="PEAD — loading from DB...")

    def _progress(done: int, total: int) -> None:
        if total <= 0:
            progress.progress(1.0, text="PEAD — loading from DB...")
            return
        if only_pending:
            mode_label = "never scanned" if pending_mode == "missing" else "stale"
            progress.progress(
                min(done / total, 1.0),
                text=f"Fetching {mode_label}: {done:,} / {total:,} this batch...",
            )
        else:
            progress.progress(
                min(done / total, 1.0),
                text=f"PEAD scanning {done:,}/{total:,}...",
            )

    try:
        result = run_pead2_scan(
            universe,
            progress_callback=_progress,
            min_mcap_cr=min_mcap_cr,
            only_pending=only_pending,
            pending_mode=pending_mode,
            max_fetch=max_fetch,
        )
    except Exception as exc:
        progress.empty()
        host.error(f"PEAD scan failed: {exc}")
        return None
    progress.empty()
    return result


def _render_fetch_remaining_box(
    coverage: Pead2ScanCoverage,
    *,
    filter_key: tuple,
    baselines: dict[str, int],
    batch_size: int,
) -> None:
    """Collapsible batch-fetch panel — collapsed when queue is empty."""
    missing_n = coverage.pending_count("missing")
    stale_n = coverage.pending_count("stale")
    pending_n = coverage.pending
    missing_base = max(int(baselines.get("missing") or missing_n), missing_n, 1)
    stale_base = max(int(baselines.get("stale") or stale_n), stale_n, 1)

    if pending_n > 0:
        summary = f"Fetch queue · {pending_n:,} remaining (new {missing_n:,} · stale {stale_n:,})"
    else:
        summary = f"Fetch queue · complete · {coverage.cached:,} in DB"

    with st.expander(summary, expanded=(pending_n > 0)):
        st.markdown('<div class="pead-fetch-panel"></div>', unsafe_allow_html=True)
        _render_last_fetch_status(filter_key)

        row = st.columns([0.55, 1.15, 1.15], gap="small", vertical_alignment="bottom")
        with row[0]:
            st.number_input(
                "Batch",
                min_value=10,
                max_value=2000,
                value=int(st.session_state.get("pead2_fetch_batch", PEAD2_RECENT_MAX_FETCH)),
                step=50,
                key="pead2_fetch_batch",
                help="Tickers per click from Yahoo.",
            )
        with row[1]:
            st.caption(f"New **{missing_n:,}**")
            if missing_n > 0:
                _render_bucket_progress(missing_n, missing_base)
            st.button(
                f"Fetch {min(missing_n, batch_size):,}",
                use_container_width=True,
                key="pead2_fetch_missing",
                disabled=missing_n == 0,
                on_click=_queue_pead_fetch,
                args=("missing",),
            )
        with row[2]:
            st.caption(f"Stale **{stale_n:,}**")
            if stale_n > 0:
                _render_bucket_progress(stale_n, stale_base)
            st.button(
                f"Fetch {min(stale_n, batch_size):,}",
                use_container_width=True,
                key="pead2_fetch_stale",
                disabled=stale_n == 0,
                on_click=_queue_pead_fetch,
                args=("stale",),
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

    _render_ff_score_reference()

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="pead2",
            cap_tier_key="pead2_cap_tier",
            holdings_key="pead2_holdings_industries_only",
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
            st.session_state.pop("pead2_universe_key", None)
            st.session_state.pop("pead2_fetch_baselines", None)
            st.session_state.pop("pead2_last_fetch", None)

        universe, coverage = _resolve_universe_and_coverage(
            filtered,
            cap_tier_id=cap_tier_id,
            filter_key=filter_key,
        )
        baselines = _sync_fetch_baselines(filter_key, coverage)
        batch_size = int(st.session_state.get("pead2_fetch_batch", PEAD2_RECENT_MAX_FETCH))

        with row[5]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                use_container_width=True,
                key="pead2_scan",
                help="Load from DB and fetch any missing tickers from Yahoo.",
            )

    fetch_queue = st.session_state.pop("pead2_fetch_queue", None)
    if run_clicked or fetch_queue:
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        if fetch_queue == "missing":
            pending_mode: PendingFetchMode = "missing"
        elif fetch_queue == "stale":
            pending_mode = "stale"
        else:
            pending_mode = "all"

        only_pending = fetch_queue is not None
        remaining_before = coverage.pending_count(pending_mode) if only_pending else coverage.pending

        status_slot = st.empty()
        with status_slot.container():
            st.info(
                f"Starting batch — **{min(remaining_before, batch_size):,}** "
                f"{'never scanned' if pending_mode == 'missing' else 'stale' if pending_mode == 'stale' else 'remaining'} "
                f"tickers (of {remaining_before:,} in queue)..."
            )

        result = _run_scan(
            universe,
            min_mcap_cr=min_mcap_cr,
            only_pending=only_pending,
            pending_mode=pending_mode,
            max_fetch=batch_size if only_pending else None,
            status_slot=status_slot,
        )
        status_slot.empty()
        if result is None:
            return
        _store_scan_result(result)
        coverage = result.get("coverage")
        if not isinstance(coverage, Pead2ScanCoverage):
            coverage = pead2_scan_coverage(universe)
        st.session_state.pead2_coverage = coverage
        st.session_state.pead2_universe_key = filter_key

        if fetch_queue:
            remaining_after = coverage.pending_count(pending_mode)
            saved = int(result.get("saved") or 0)
            cleared = int(result.get("cleared") or saved)
            fetched = int(result.get("fetched") or 0)
            tombstoned = int(result.get("tombstoned") or 0)
            st.session_state.pead2_last_fetch = {
                "filter_key": filter_key,
                "mode": pending_mode,
                "batch_size": batch_size,
                "remaining_before": remaining_before,
                "remaining_after": remaining_after,
                "saved": saved,
                "cleared": cleared,
                "tombstoned": tombstoned,
                "fetched": fetched,
            }

    coverage = pead2_scan_coverage(universe)
    st.session_state.pead2_coverage = coverage
    _render_fetch_remaining_box(
        coverage,
        filter_key=filter_key,
        baselines=baselines,
        batch_size=batch_size,
    )

    candidates = st.session_state.get("pead2_candidates")
    candidates_previous = st.session_state.get("pead2_candidates_previous")

    if candidates is None or candidates.empty:
        st.caption("Set filters, then click **Scan**.")
        return

    candidates = enrich_pead_candidates(candidates)

    prev_df = (
        candidates_previous
        if candidates_previous is not None and not candidates_previous.empty
        else pd.DataFrame()
    )
    cache_hits = int(st.session_state.get("pead2_cache_hits") or 0)
    embed_html = build_pead2_dashboard_html(
        candidates,
        df_previous=prev_df,
        title="Top PEAD Candidates",
        standalone=False,
    )

    st.caption(
        f"{len(candidates)} stocks · {cache_hits:,} from DB · "
        f"sorted by **latest result date** · "
        f"**green square** = rising CFO + CFO/EBIT gate · toggle **100X CFO** to filter · "
        f"**click a row** to expand the detail panel."
    )
    embed_html_iframe(embed_html, height=pead2_iframe_height(len(candidates)))

    csv = format_pead_export_df(candidates).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download PEAD CSV",
        data=csv,
        file_name="pead_candidates.csv",
        mime="text/csv",
    )
