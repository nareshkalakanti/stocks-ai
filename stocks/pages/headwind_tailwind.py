"""Market-wide Headwind / Tailwind board with per-industry stock drill-down."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.config import (
    HEADWIND_PEAD_BACKFILL_MAX,
    HEADWIND_PEAD_CACHE_HOURS,
    HEADWIND_SCAN_CACHE_HOURS,
    HEADWIND_TAILWIND_MCAP_MIN_CR,
    INDIA_STOCKS_DATASET,
    INTRINSIC_VALUE_CACHE_HOURS,
    PEAD2_MAX_WORKERS,
)
from stocks.listings.stocks_data import load_india_stocks
from stocks.dashboards.report_html import embed_html_iframe
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.results_utils import analysis_universe
from stocks.scans.scan_toolbar import (
    SCAN_BTN_COL_WIDTH,
    base_scan_extra_widths,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.stock_filters import apply_stock_filters, filter_caption_suffix
from stocks.strategies.intrinsic_value.cache import (
    ensure_pe_ratios,
    load_cached_headwind_scan,
    save_cached_headwind_scan,
)
from stocks.strategies.intrinsic_value.html import (
    build_headwind_board_html,
    build_headwind_drilldown_html,
    headwind_board_iframe_height,
    headwind_drilldown_iframe_height,
)
from stocks.strategies.intrinsic_value.service import (
    assemble_headwind_from_iv_cache,
    filter_universe_by_db_mcap,
    run_intrinsic_value_scan,
)
from stocks.strategies.pead2.cache_lookup import count_pead_backfill_pending, ensure_pead_scores
from stocks.core.text_utils import safe_str

_MIN_CR = HEADWIND_TAILWIND_MCAP_MIN_CR


def _as_df(value: pd.DataFrame | None) -> pd.DataFrame:
    return value if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _industry_column(ranked: pd.DataFrame) -> str:
    if "industry" in ranked.columns and ranked["industry"].astype(str).str.strip().ne("").any():
        return "industry"
    if "sub_sector" in ranked.columns and ranked["sub_sector"].astype(str).str.strip().ne("").any():
        return "sub_sector"
    return "sector"


def _apply_scan_result(result: dict, scan_market: str) -> None:
    st.session_state.ht_ranked = result["ranked"]
    st.session_state.ht_sectors = result["sectors"]
    st.session_state.ht_scanned = result["scanned"]
    st.session_state.ht_with_data = result["with_data"]
    st.session_state.ht_scan_market = scan_market
    industry_col = safe_str(result.get("industry_col"))
    if not industry_col:
        industry_col = _industry_column(_as_df(result.get("ranked")))
    st.session_state.ht_industry_col = industry_col
    if isinstance(result.get("sectors"), pd.DataFrame) and not result["sectors"].empty:
        st.session_state.ht_selected_sector = str(result["sectors"].iloc[0]["sector"])


def _scan_universe(stocks: pd.DataFrame, market: str) -> tuple[pd.DataFrame, dict[str, int]]:
    """Listings with fresh SQLite market_cap_cr ≥ floor (no yfinance)."""
    universe = analysis_universe(stocks, limit=0)
    market = safe_str(market).upper()
    if market in ("NSE", "BSE") and "market" in universe.columns:
        universe = universe[universe["market"].astype(str).str.upper() == market]
    return filter_universe_by_db_mcap(universe, min_cr=_MIN_CR)


def _resolve_scan_market(market: str) -> str:
    m = safe_str(market).upper()
    if m in ("NSE", "BSE"):
        return m
    return "All"


def _try_restore_results(stocks: pd.DataFrame, scan_market: str) -> bool:
    sectors_state = st.session_state.get("ht_sectors")
    if (
        isinstance(sectors_state, pd.DataFrame)
        and not sectors_state.empty
        and safe_str(st.session_state.get("ht_scan_market")) == scan_market
    ):
        return True

    cached = load_cached_headwind_scan(
        max_hours=HEADWIND_SCAN_CACHE_HOURS,
        scan_market=scan_market,
        min_mcap_cr=_MIN_CR,
    )
    if cached:
        _apply_scan_result(cached, scan_market)
        return True

    built = assemble_headwind_from_iv_cache(
        _scan_universe(stocks, scan_market)[0],
        min_mcap_cr=_MIN_CR,
        min_sector_companies=1,
    )
    if built:
        _apply_scan_result(built, scan_market)
        return True
    return False


def render_headwind_tailwind() -> None:
    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    st.markdown("### H&T")

    with scan_toolbar_row(*base_scan_extra_widths(SCAN_BTN_COL_WIDTH)) as row:
        filters, _, holdings_industries_only = render_base_scan_filters(
            stocks,
            row,
            key_prefix="htf",
            cap_tier_key="ht_cap_tier",
            holdings_key="ht_holdings_industries_only",
        )
        with row[5]:
            run_clicked = st.button("Run scan", type="primary", use_container_width=True)

    filtered = apply_stock_filters(stocks, filters)
    applied = apply_holdings_industries_if_checked(
        filtered, enabled=holdings_industries_only
    )
    if applied is None:
        return
    filtered, _holdings_industry_note = applied

    scan_market = _resolve_scan_market(filters.market)
    eligible, mcap_stats = _scan_universe(filtered, scan_market)

    if not run_clicked:
        _try_restore_results(stocks, scan_market)

    if run_clicked:
        if eligible.empty:
            scope = scan_market if scan_market in ("NSE", "BSE") else "filtered"
            st.warning(
                f"No {scope} listings with cached market cap ≥ ₹{_MIN_CR:.0f} Cr. "
                "Run **PEAD**, **Breakout**, or **Refresh prices** on Holdings to fill SQLite first."
            )
            return

        progress = st.progress(0, text="Scanning...")

        def _progress(done: int, total: int) -> None:
            progress.progress(done / max(total, 1), text=f"Scanning {done}/{total}...")

        try:
            result = run_intrinsic_value_scan(
                eligible,
                min_mcap_cr=_MIN_CR,
                min_sector_companies=1,
                prefilter_mcap=False,
                use_cache=True,
                progress_callback=_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Scan failed: {exc}")
            return
        progress.empty()

        if result.get("with_data", 0) == 0 or result.get("sectors") is None or result["sectors"].empty:
            partial = assemble_headwind_from_iv_cache(
                eligible,
                min_mcap_cr=_MIN_CR,
                min_sector_companies=1,
            )
            if partial:
                save_cached_headwind_scan(partial, scan_market=scan_market, min_mcap_cr=_MIN_CR)
                _apply_scan_result(partial, scan_market)
                st.rerun()
            st.error("No fundamentals returned. Wait a few minutes and run again.")
            return

        save_cached_headwind_scan(result, scan_market=scan_market, min_mcap_cr=_MIN_CR)
        _apply_scan_result(result, scan_market)
        st.rerun()

    ranked = _as_df(st.session_state.get("ht_ranked"))
    ranked = ensure_pe_ratios(
        ranked,
        max_hours=INTRINSIC_VALUE_CACHE_HOURS,
        pead_max_hours=HEADWIND_PEAD_CACHE_HOURS,
    )
    ranked = ensure_pead_scores(
        ranked,
        max_hours=HEADWIND_PEAD_CACHE_HOURS,
        backfill_max=0,
    )
    pending_pead = 0
    if not ranked.empty and "ticker" in ranked.columns:
        missing = ranked.loc[ranked["pead_score"].isna(), "ticker"].astype(str).str.upper().tolist()
        pending_pead = count_pead_backfill_pending(missing, max_hours=999999)

    if pending_pead and HEADWIND_PEAD_BACKFILL_MAX > 0:
        with st.spinner(
            f"Checking PEAD data for {min(pending_pead, HEADWIND_PEAD_BACKFILL_MAX)} stocks..."
        ):
            ranked = ensure_pead_scores(
                ranked,
                max_hours=HEADWIND_PEAD_CACHE_HOURS,
                backfill_max=HEADWIND_PEAD_BACKFILL_MAX,
                max_workers=PEAD2_MAX_WORKERS,
            )
            st.session_state.ht_ranked = ranked
    else:
        st.session_state.ht_ranked = ranked
    sectors = st.session_state.get("ht_sectors")
    if not isinstance(sectors, pd.DataFrame):
        sectors = None
    with_data = st.session_state.get("ht_with_data", 0)
    result_market = safe_str(st.session_state.get("ht_scan_market"))

    if result_market and result_market != scan_market:
        st.info(f"Results are for **{result_market}**. Run scan for **{scan_market}**.")
        sectors = None

    if sectors is None or sectors.empty:
        hint = filter_caption_suffix(filters)
        if hint:
            st.info(f"Click **Run scan** — {hint}.")
        else:
            st.info("Click **Run scan** to build the headwind / tailwind board.")
        return

    industry_col = safe_str(st.session_state.get("ht_industry_col"))
    if not industry_col:
        industry_col = _industry_column(ranked)

    tab_all, tab_trend = st.tabs(["All", "Trend bars"])

    market_label = result_market or scan_market

    with tab_all:
        st.caption(
            "**PE** (Option A) = price ÷ sum of last 4 quarters’ EPS. "
            "**Fwd PE** (Option B) = price ÷ (latest quarter EPS × 4). "
            "**PEAD** = earnings-drift score from the PEAD scan (hover **—** for why). "
            "Yellow **SS** tags = SuperStar investors holding the stock (refresh on **SuperStars** page). "
            "Re-run **Run scan** if PE shows —."
        )
        render_all_drilldown(
            sectors,
            ranked,
            industry_col,
            min_mcap_cr=_MIN_CR,
            title=f"H&T — {market_label}",
        )

    with tab_trend:
        board_embed = build_headwind_board_html(
            sectors,
            standalone=True,
        )
        embed_html_iframe(board_embed, height=headwind_board_iframe_height(len(sectors)))


def render_all_drilldown(
    sectors: pd.DataFrame,
    ranked: pd.DataFrame,
    industry_col: str,
    *,
    min_mcap_cr: float,
    title: str,
) -> None:
    """Full industry board — click a row to expand ranked stocks in that group."""
    if sectors is None or sectors.empty:
        st.info("No industry board data.")
        return
    if ranked is None or ranked.empty:
        st.info("No ranked stock data — run scan again.")
        return

    board = sectors.reset_index(drop=True)
    first_group = safe_str(board.iloc[0].get("sector")) if len(board) else ""
    expanded_n = 0
    if first_group and industry_col in ranked.columns:
        expanded_n = int(
            (ranked[industry_col].astype(str).str.strip() == first_group).sum()
        )

    drill_html = build_headwind_drilldown_html(
        board,
        ranked,
        industry_col,
        min_mcap_cr=min_mcap_cr,
        title=title,
        standalone=True,
    )
    embed_html_iframe(
        drill_html,
        height=headwind_drilldown_iframe_height(
            len(board),
            expanded_stocks=max(expanded_n, 1),
        ),
    )

