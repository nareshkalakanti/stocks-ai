"""Small + Cheap — mcap 20–200 Cr · Mcap/Sales < 1 · optional debt-free."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    SMALL_CHEAP_CACHE_HOURS,
    cap_tier_id_from_label,
)
from stocks.dashboards.report_html import embed_html_iframe
from stocks.listings.stocks_data import load_india_stocks
from stocks.scans.scan_toolbar import (
    COMPACT_SCAN_BTN_COL_WIDTH,
    base_scan_extra_widths,
    inject_scan_toolbar_css,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.scan_universe import resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.strategies.small_cheap.html import (
    build_small_cheap_html,
    small_cheap_iframe_height,
)
from stocks.strategies.small_cheap.service import (
    prepare_small_cheap_universe,
    run_small_cheap_scan,
)
from stocks.strategies.small_cheap.strategy import (
    format_small_cheap_export_df,
    small_cheap_caption,
)


def _inject_css() -> None:
    if st.session_state.get("_smallcheap_scan_css"):
        return
    inject_scan_toolbar_css()
    st.session_state["_smallcheap_scan_css"] = True


def _filter_key(
    filters,
    *,
    cap_tier_id: str,
    debt_free_only: bool,
) -> tuple:
    return (
        filters.market,
        tuple(filters.sectors),
        tuple(filters.industries),
        filters.search,
        cap_tier_id,
        debt_free_only,
    )


def render_small_cheap(*, show_title: bool = True) -> None:
    _inject_css()

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    debt_free_only = st.checkbox(
        "Debt-free / low debt only",
        value=True,
        key="smallcheap_debt_free",
        help=(
            "Keep names with totalDebt = 0 or D/E ≤ 0.1 from Yahoo. "
            "When debt data is missing, the stock is still kept (verify manually)."
        ),
    )

    if show_title:
        st.markdown("### Small + Cheap")
    st.caption(small_cheap_caption(debt_free_only=debt_free_only))

    if "smallcheap_cap_tier" not in st.session_state:
        st.session_state["smallcheap_cap_tier"] = "Micro Value (20–200 Cr)"

    with scan_toolbar_row(*base_scan_extra_widths(COMPACT_SCAN_BTN_COL_WIDTH)) as row:
        filters, cap_tier_label_ui = render_base_scan_filters(
            stocks,
            row,
            key_prefix="smallcheap",
            cap_tier_key="smallcheap_cap_tier",
        )
        cap_tier_id = resolve_cap_tier_id(
            filters.market, cap_tier_id_from_label(cap_tier_label_ui)
        )
        filtered = apply_stock_filters(stocks, filters)

        filter_key = _filter_key(
            filters,
            cap_tier_id=cap_tier_id,
            debt_free_only=debt_free_only,
        )
        if st.session_state.get("smallcheap_filter_key") != filter_key:
            st.session_state.smallcheap_filter_key = filter_key
            st.session_state.pop("smallcheap_candidates", None)

        universe, _, _ = prepare_small_cheap_universe(
            filtered, cap_tier_id=cap_tier_id
        )

        with row[4]:
            run_clicked = st.button(
                "Scan",
                type="primary",
                width="stretch",
                key="smallcheap_scan",
                help=(
                    "Scan ₹20–200 Cr names with Mcap/Sales < 1 via yfinance "
                    f"(cache hint ≤ {SMALL_CHEAP_CACHE_HOURS}h)."
                ),
            )

    if run_clicked:
        if universe.empty:
            st.warning(
                "No stocks in the 20–200 Cr band for current filters. "
                "Try All markets / wider sector, or wait for mcap cache to fill."
            )
            return

        progress = st.progress(0, text="Small + Cheap — loading…")

        def _progress(done: int, total: int) -> None:
            if total <= 0:
                progress.progress(1.0, text="Done")
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Small + Cheap {done:,}/{total:,}…",
            )

        try:
            result = run_small_cheap_scan(
                universe,
                debt_free_only=debt_free_only,
                progress_callback=_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Small + Cheap scan failed: {exc}")
            return
        progress.empty()

        candidates_df = result.get("candidates")
        st.session_state.smallcheap_candidates = candidates_df
        scanned = int(result.get("scanned") or 0)
        with_data = int(result.get("with_data") or 0)
        n_pass = (
            len(candidates_df)
            if isinstance(candidates_df, pd.DataFrame)
            else 0
        )
        debt_note = "debt-free filter on" if debt_free_only else "debt filter off"
        st.caption(
            f"Scanned **{scanned:,}** · fundamentals for **{with_data:,}** · "
            f"**{n_pass:,}** passed ({debt_note})."
        )

    candidates = st.session_state.get("smallcheap_candidates")
    if candidates is None:
        st.caption("Set filters, then click **Scan** (defaults to 20–200 Cr).")
        return

    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        st.caption(
            "No names matched **Mcap/Sales < 1** in ₹20–200 Cr "
            "(try turning off debt filter or widening sector filters)."
        )
        return

    embed_html = build_small_cheap_html(candidates, standalone=False)
    embed_html_iframe(embed_html, height=small_cheap_iframe_height(len(candidates)))

    export = format_small_cheap_export_df(candidates)
    st.download_button(
        "Download CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="small_cheap.csv",
        mime="text/csv",
        key="smallcheap_csv",
    )
