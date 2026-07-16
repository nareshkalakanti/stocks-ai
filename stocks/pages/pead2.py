import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    PEAD2_CACHE_HOURS,
    PEAD2_RECENT_MAX_FETCH,
    cap_tier_id_from_label,
)
from stocks.market.fundamentals_service import cap_tier_label
from stocks.strategies.pead2.html import build_pead2_dashboard_html, pead2_iframe_height
from stocks.strategies.pead2.service import (
    Pead2ScanCoverage,
    PendingFetchMode,
    expand_pead_candidates_to_universe,
    pead2_scan_coverage,
    prepare_pead_universe,
    run_pead2_scan,
)
from stocks.strategies.pead2.strategy import (
    enrich_pead_candidates,
    format_pead_export_df,
)
from stocks.scans.holdings_playlist import is_holdings_playlist
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
.st-key-pead2_scan button,
.st-key-pead2_fetch_missing button,
.st-key-pead2_fetch_stale button,
.st-key-pead2_fetch_aged button,
.st-key-pead2_fetch_no_data button,
.st-key-pead2_fetch_stop button,
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
            "aged": coverage.pending_count("aged"),
            "no_data": coverage.pending_count("no_data"),
        }
        st.session_state.pead2_fetch_baselines = baselines
        st.session_state.pop("pead2_last_fetch", None)
    return baselines


_PEAD_AUTO_MAX_BATCHES = 200
_PEAD_AUTO_STALL_LIMIT = 3


def _ensure_pead_batch_default() -> None:
    if "pead2_fetch_batch" not in st.session_state:
        st.session_state.pead2_fetch_batch = PEAD2_RECENT_MAX_FETCH


def _pead_fetch_batch_size() -> int:
    _ensure_pead_batch_default()
    return max(10, int(st.session_state.pead2_fetch_batch))


def _stop_auto_fetch() -> None:
    st.session_state.pead2_auto_active = False
    st.session_state.pop("pead2_fetch_queue", None)


def _queue_pead_fetch(mode: PendingFetchMode) -> None:
    st.session_state.pead2_fetch_queue = mode
    if st.session_state.get("pead2_auto_run"):
        st.session_state.pead2_auto_active = True
        st.session_state.pead2_auto_mode = mode
        st.session_state.pead2_auto_stall = 0
        st.session_state.pead2_auto_batch_n = 0
        st.session_state.pop("pead2_auto_stall_msg", None)
        st.session_state.pop("pead2_auto_done", None)
    else:
        st.session_state.pead2_auto_active = False


def _clear_auto_fetch_state() -> None:
    for key in (
        "pead2_auto_active",
        "pead2_auto_mode",
        "pead2_auto_stall",
        "pead2_auto_batch_n",
        "pead2_auto_stall_msg",
        "pead2_auto_done",
    ):
        st.session_state.pop(key, None)


def _auto_mode_label(mode: PendingFetchMode | str | None) -> str:
    labels = {
        "missing": "new",
        "stale": "stale formula",
        "aged": f"aged (>{PEAD2_CACHE_HOURS}h)",
        "no_data": "no-data retry",
    }
    return labels.get(str(mode or ""), "batch")


def _maybe_auto_continue_fetch(
    *,
    filter_key: tuple,
    pending_mode: PendingFetchMode,
    remaining_before: int,
    remaining_after: int,
    fetched: int,
) -> None:
    if not st.session_state.get("pead2_auto_active"):
        return
    if st.session_state.get("pead2_auto_mode") != pending_mode:
        return

    if remaining_after <= 0:
        st.session_state.pead2_auto_active = False
        st.session_state.pead2_auto_done = {
            "filter_key": filter_key,
            "mode": pending_mode,
        }
        return

    if fetched > 0 and remaining_after >= remaining_before:
        stall = int(st.session_state.get("pead2_auto_stall") or 0) + 1
        st.session_state.pead2_auto_stall = stall
    else:
        st.session_state.pead2_auto_stall = 0

    if int(st.session_state.get("pead2_auto_stall") or 0) >= _PEAD_AUTO_STALL_LIMIT:
        st.session_state.pead2_auto_active = False
        st.session_state.pead2_auto_stall_msg = (
            f"Auto-run stopped after {_PEAD_AUTO_STALL_LIMIT} batches with no progress. "
            "Try a smaller batch size."
        )
        return

    batch_n = int(st.session_state.get("pead2_auto_batch_n") or 0) + 1
    if batch_n >= _PEAD_AUTO_MAX_BATCHES:
        st.session_state.pead2_auto_active = False
        st.session_state.pead2_auto_stall_msg = (
            f"Auto-run stopped after {_PEAD_AUTO_MAX_BATCHES:,} batches."
        )
        return

    st.session_state.pead2_auto_batch_n = batch_n
    st.session_state.pead2_fetch_queue = pending_mode
    st.rerun()


def _render_auto_fetch_status(
    *,
    filter_key: tuple,
    coverage: Pead2ScanCoverage,
) -> None:
    if st.session_state.get("pead2_auto_active"):
        mode = st.session_state.get("pead2_auto_mode", "aged")
        remaining = coverage.pending_count(mode) if mode in {
            "missing",
            "stale",
            "aged",
            "no_data",
        } else 0
        batch_n = int(st.session_state.get("pead2_auto_batch_n") or 0) + 1
        row = st.columns([5, 1], vertical_alignment="center")
        with row[0]:
            st.info(
                f"Auto-running **{_auto_mode_label(mode)}** batches "
                f"of **{_pead_fetch_batch_size():,}** (batch **#{batch_n}**) · "
                f"**{remaining:,}** left"
            )
        with row[1]:
            st.button(
                "Stop",
                key="pead2_fetch_stop",
                use_container_width=True,
                on_click=_stop_auto_fetch,
            )
        return

    done = st.session_state.get("pead2_auto_done")
    if isinstance(done, dict) and done.get("filter_key") == filter_key:
        st.success(
            f"Auto-run complete — all **{_auto_mode_label(done.get('mode'))}** "
            "tickers refreshed."
        )
        st.session_state.pop("pead2_auto_done", None)

    stall_msg = st.session_state.get("pead2_auto_stall_msg")
    if stall_msg:
        st.warning(stall_msg)
        st.session_state.pop("pead2_auto_stall_msg", None)


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
    label = {"missing": "New", "stale": "Stale", "aged": "Aged", "no_data": "No data"}.get(mode, "Batch")
    cleared = int(last.get("cleared") or last.get("saved") or 0)
    saved = int(last.get("saved") or 0)
    failed = max(int(last.get("fetched") or 0) - cleared, 0)
    st.caption(
        f"Last {label} batch: {last['fetched']:,} tried · **{saved:,} updated** "
        f"({failed:,} failed) · **{last['remaining_after']:,}** left "
        f"(was {last['remaining_before']:,})"
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
            mode_label = (
                "never scanned"
                if pending_mode == "missing"
                else "stale formula"
                if pending_mode == "stale"
                else f"aged (>{PEAD2_CACHE_HOURS}h)"
                if pending_mode == "aged"
                else "no PEAD data"
                if pending_mode == "no_data"
                else "remaining"
            )
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
    show_no_data_retry: bool = False,
) -> None:
    """Collapsible batch-fetch panel — collapsed when queue is empty."""
    missing_n = coverage.pending_count("missing")
    stale_n = coverage.pending_count("stale")
    aged_n = coverage.pending_count("aged")
    no_data_n = coverage.pending_count("no_data")
    refresh_n = coverage.refreshable
    missing_base = max(int(baselines.get("missing") or missing_n), missing_n, 1)
    stale_base = max(int(baselines.get("stale") or stale_n), stale_n, 1)
    aged_base = max(int(baselines.get("aged") or aged_n), aged_n, 1)
    no_data_base = max(int(baselines.get("no_data") or no_data_n), no_data_n, 1)

    if refresh_n > 0:
        summary = (
            f"Fetch queue · {refresh_n:,} to refresh "
            f"(new {missing_n:,} · stale {stale_n:,} · aged {aged_n:,})"
        )
    elif show_no_data_retry and no_data_n > 0:
        summary = (
            f"Fetch queue · complete · {coverage.cached:,} in DB · "
            f"{coverage.scorable:,} scorable · {no_data_n:,} no data"
        )
    else:
        summary = f"Fetch queue · complete · {coverage.cached:,} in DB"

    with st.expander(
        summary,
        expanded=(refresh_n > 0 or aged_n > 0 or (show_no_data_retry and no_data_n > 0)),
    ):
        st.markdown('<div class="pead-fetch-panel"></div>', unsafe_allow_html=True)
        st.checkbox(
            "Auto-run batches until done",
            value=bool(st.session_state.get("pead2_auto_run", True)),
            key="pead2_auto_run",
            help=(
                "When checked, Fetch / Refresh keeps running batch after batch "
                "until the queue is empty. Stops automatically if 3 batches make no progress."
            ),
        )
        _render_last_fetch_status(filter_key)

        col_count = 5 if show_no_data_retry else 4
        widths = [0.55] + [1.0] * (col_count - 1)
        row = st.columns(widths, gap="small", vertical_alignment="bottom")
        with row[0]:
            st.number_input(
                "Batch",
                min_value=10,
                max_value=2000,
                step=10,
                key="pead2_fetch_batch",
                help="Tickers per batch — change anytime; next batch uses this value.",
            )
        batch_size = _pead_fetch_batch_size()
        with row[1]:
            st.caption(f"New **{missing_n:,}**")
            if missing_n > 0:
                _render_bucket_progress(missing_n, missing_base)
            if st.button(
                f"Fetch {min(missing_n, batch_size):,}",
                use_container_width=True,
                key="pead2_fetch_missing",
                disabled=missing_n == 0,
            ):
                _queue_pead_fetch("missing")
        with row[2]:
            st.caption(f"Stale **{stale_n:,}**")
            if stale_n > 0:
                _render_bucket_progress(stale_n, stale_base)
            if st.button(
                f"Fetch {min(stale_n, batch_size):,}",
                use_container_width=True,
                key="pead2_fetch_stale",
                disabled=stale_n == 0,
                help="Old PEAD formula version after an app update.",
            ):
                _queue_pead_fetch("stale")
        with row[3]:
            st.caption(f"Aged **{aged_n:,}**")
            if aged_n > 0:
                _render_bucket_progress(aged_n, aged_base)
            if st.button(
                f"Refresh {min(aged_n, batch_size):,}",
                use_container_width=True,
                key="pead2_fetch_aged",
                disabled=aged_n == 0,
                help=f"Re-fetch from Yahoo when cache is older than {PEAD2_CACHE_HOURS}h (new earnings).",
            ):
                _queue_pead_fetch("aged")
        if show_no_data_retry:
            with row[4]:
                st.caption(f"No data **{no_data_n:,}**")
                if no_data_n > 0:
                    _render_bucket_progress(no_data_n, no_data_base)
                if st.button(
                    f"Retry {min(no_data_n, batch_size):,}",
                    use_container_width=True,
                    key="pead2_fetch_no_data",
                    disabled=no_data_n == 0,
                ):
                    _queue_pead_fetch("no_data")


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
            _clear_auto_fetch_state()

        universe, coverage = _resolve_universe_and_coverage(
            filtered,
            cap_tier_id=cap_tier_id,
            filter_key=filter_key,
        )
        baselines = _sync_fetch_baselines(filter_key, coverage)

        with row[5]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                use_container_width=True,
                key="pead2_scan",
                help=(
                    f"Load from DB and fetch missing, stale, or cache older than "
                    f"{PEAD2_CACHE_HOURS}h from Yahoo."
                ),
            )

    coverage = pead2_scan_coverage(universe)
    st.session_state.pead2_coverage = coverage
    holdings_view = is_holdings_playlist(filters.market)
    _render_auto_fetch_status(filter_key=filter_key, coverage=coverage)
    _render_fetch_remaining_box(
        coverage,
        filter_key=filter_key,
        baselines=baselines,
        show_no_data_retry=holdings_view,
    )

    fetch_queue = st.session_state.pop("pead2_fetch_queue", None)
    batch_size = _pead_fetch_batch_size()
    if run_clicked or fetch_queue:
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        if fetch_queue == "missing":
            pending_mode: PendingFetchMode = "missing"
        elif fetch_queue == "stale":
            pending_mode = "stale"
        elif fetch_queue == "aged":
            pending_mode = "aged"
        elif fetch_queue == "no_data":
            pending_mode = "no_data"
        else:
            pending_mode = "all"

        only_pending = fetch_queue is not None
        remaining_before = coverage.pending_count(pending_mode) if only_pending else coverage.pending

        status_slot = st.empty()
        with status_slot.container():
            st.info(
                f"Starting batch — **{min(remaining_before, batch_size):,}** "
                f"{'never scanned' if pending_mode == 'missing' else 'stale formula' if pending_mode == 'stale' else f'aged (>{PEAD2_CACHE_HOURS}h)' if pending_mode == 'aged' else 'no PEAD data' if pending_mode == 'no_data' else 'remaining'} "
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
            _maybe_auto_continue_fetch(
                filter_key=filter_key,
                pending_mode=pending_mode,
                remaining_before=remaining_before,
                remaining_after=remaining_after,
                fetched=fetched,
            )

    candidates = st.session_state.get("pead2_candidates")
    candidates_previous = st.session_state.get("pead2_candidates_previous")

    if candidates is None and holdings_view and not universe.empty:
        result = run_pead2_scan(universe, only_pending=True, max_fetch=0)
        _store_scan_result(result)
        candidates = result.get("candidates")
        candidates_previous = result.get("candidates_previous")

    if candidates is None:
        st.caption("Set filters, then click **Scan**.")
        return

    if holdings_view and not universe.empty:
        candidates = expand_pead_candidates_to_universe(universe, candidates)
        if candidates_previous is not None and not candidates_previous.empty:
            candidates_previous = expand_pead_candidates_to_universe(
                universe, candidates_previous
            )
        else:
            candidates_previous = expand_pead_candidates_to_universe(universe, pd.DataFrame())

    if candidates.empty:
        st.caption("Set filters, then click **Scan**.")
        return

    candidates = enrich_pead_candidates(candidates)

    prev_df = (
        candidates_previous
        if candidates_previous is not None and not candidates_previous.empty
        else pd.DataFrame()
    )
    cache_hits = int(st.session_state.get("pead2_cache_hits") or 0)
    scored_n = int(candidates["pead_score"].notna().sum()) if "pead_score" in candidates.columns else len(candidates)
    embed_html = build_pead2_dashboard_html(
        candidates,
        df_previous=prev_df,
        title="Holdings PEAD" if holdings_view else "Top PEAD Candidates",
        list_label="Holdings" if holdings_view else "PEAD candidates",
        show_scored_split=holdings_view,
        standalone=False,
    )

    if holdings_view:
        no_data_n = coverage.no_data
        tier_note = (
            f" · **{cap_tier_label(cap_tier_id)}**"
            if cap_tier_id not in ("all", "", None)
            else ""
        )
        st.caption(
            f"{len(candidates)} holdings{tier_note} · **{scored_n:,}** with PEAD scores · "
            f"**{no_data_n:,}** without quarterly data · "
            f"{cache_hits:,} loaded from DB · "
            f"**click a row** to expand the detail panel."
        )
    else:
        st.caption(
            f"{len(candidates)} stocks · {cache_hits:,} from DB · "
            f"sorted by **latest result date** · "
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
