"""Market-wide Headwind / Tailwind board with per-industry stock drill-down."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.config import (
    HEADWIND_IV_CACHE_HOURS,
    HEADWIND_SCAN_CACHE_HOURS,
    INDIA_STOCKS_DATASET,
    cap_tier_id_from_label,
)
from stocks.listings.stocks_data import load_india_stocks
from stocks.dashboards.report_html import embed_html_iframe
from stocks.market.fundamentals_service import apply_cap_tier_filter
from stocks.scans.results_utils import analysis_universe
from stocks.scans.scan_universe import cap_tier_min_mcap_cr, resolve_cap_tier_id
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
    _stocks_by_sector,
)
from stocks.strategies.intrinsic_value.service import (
    assemble_headwind_from_iv_cache,
    ensure_pcf_values,
    filter_universe_by_db_mcap,
    resolve_scan_group_col,
    run_intrinsic_value_scan,
    shrink_universe_by_mcap,
)
from stocks.core.text_utils import safe_str


def _as_df(value: pd.DataFrame | None) -> pd.DataFrame:
    return value if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _industry_column(ranked: pd.DataFrame) -> str:
    if "industry" in ranked.columns and ranked["industry"].astype(str).str.strip().ne("").any():
        return "industry"
    if "sub_sector" in ranked.columns and ranked["sub_sector"].astype(str).str.strip().ne("").any():
        return "sub_sector"
    return "sector"


def _apply_scan_result(result: dict, scan_market: str, *, filter_key: tuple) -> None:
    st.session_state.ht_ranked = result["ranked"]
    st.session_state.ht_sectors = result["sectors"]
    st.session_state.ht_scanned = result["scanned"]
    st.session_state.ht_with_data = result["with_data"]
    st.session_state.ht_scan_market = scan_market
    st.session_state.ht_filter_key = filter_key
    industry_col = safe_str(result.get("industry_col"))
    if not industry_col:
        industry_col = _industry_column(_as_df(result.get("ranked")))
    st.session_state.ht_industry_col = industry_col
    if isinstance(result.get("sectors"), pd.DataFrame) and not result["sectors"].empty:
        st.session_state.ht_selected_sector = str(result["sectors"].iloc[0]["sector"])


def _ht_filter_key(
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


def _resolve_ht_industry_col(ranked: pd.DataFrame, preferred: str = "") -> str:
    """H&T always groups the board by display sector."""
    if "sector" in ranked.columns:
        return "sector"
    pref = safe_str(preferred).strip()
    if pref and pref in ranked.columns:
        return pref
    return resolve_scan_group_col(ranked, force_display_sector=True)


def _narrow_ht_results(
    ranked: pd.DataFrame,
    sectors: pd.DataFrame | None,
    filtered: pd.DataFrame,
    industry_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Keep H&T results aligned with the current toolbar filters."""
    if ranked.empty or filtered.empty or "ticker" not in filtered.columns:
        return ranked, sectors
    tickers = set(filtered["ticker"].astype(str).str.upper())
    narrowed = ranked[ranked["ticker"].astype(str).str.upper().isin(tickers)].copy()
    if (
        sectors is None
        or sectors.empty
        or not industry_col
        or industry_col not in narrowed.columns
    ):
        return narrowed, sectors
    groups = set(narrowed[industry_col].astype(str).str.strip()) - {""}
    if not groups:
        return narrowed, sectors
    narrowed_sectors = sectors[
        sectors["sector"].astype(str).str.strip().isin(groups)
    ].copy()
    return narrowed, narrowed_sectors


def _resolve_mcap_floor(cap_tier_id: str) -> float:
    """All caps = no mcap floor; named tiers use their configured minimum."""
    if cap_tier_id in ("all", ""):
        return 0.0
    tier_min = cap_tier_min_mcap_cr(cap_tier_id)
    return 0.0 if tier_min is None else float(tier_min)


def _filtered_universe(stocks: pd.DataFrame, market: str) -> pd.DataFrame:
    universe = analysis_universe(stocks, limit=0)
    market = safe_str(market).upper()
    if market in ("NSE", "BSE") and "market" in universe.columns:
        universe = universe[universe["market"].astype(str).str.upper() == market]
    return universe.reset_index(drop=True)


def _scan_universe(
    stocks: pd.DataFrame,
    market: str,
    *,
    min_cr: float,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Listings for cache restore — DB mcap filter only when a floor is set."""
    universe = _filtered_universe(stocks, market)
    if universe.empty or min_cr <= 0:
        return universe, {
            "total": len(universe),
            "cached": 0,
            "eligible": len(universe),
            "missing": 0,
            "below_floor": 0,
        }
    return filter_universe_by_db_mcap(universe, min_cr=min_cr)


def _resolve_scan_market(market: str) -> str:
    m = safe_str(market).upper()
    if m in ("NSE", "BSE"):
        return m
    return "All"


def _try_restore_results(
    filtered: pd.DataFrame,
    scan_market: str,
    *,
    mcap_floor: float,
    filter_key: tuple,
    allow_disk_cache: bool,
) -> bool:
    sectors_state = st.session_state.get("ht_sectors")
    if (
        isinstance(sectors_state, pd.DataFrame)
        and not sectors_state.empty
        and safe_str(st.session_state.get("ht_scan_market")) == scan_market
        and st.session_state.get("ht_filter_key") == filter_key
    ):
        return True

    if allow_disk_cache:
        cached = load_cached_headwind_scan(
            max_hours=HEADWIND_SCAN_CACHE_HOURS,
            scan_market=scan_market,
            min_mcap_cr=mcap_floor,
        )
        if cached:
            _apply_scan_result(cached, scan_market, filter_key=filter_key)
            return True

    built = assemble_headwind_from_iv_cache(
        _scan_universe(filtered, scan_market, min_cr=mcap_floor)[0],
        min_mcap_cr=mcap_floor,
        min_sector_companies=1,
        max_hours=HEADWIND_IV_CACHE_HOURS,
    )
    if built:
        _apply_scan_result(built, scan_market, filter_key=filter_key)
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
        filters, cap_tier_label_ui = render_base_scan_filters(
            stocks,
            row,
            key_prefix="htf",
            cap_tier_key="ht_cap_tier",
        )
        with row[4]:
            run_clicked = st.button("Run scan", type="primary", width="stretch")

    filtered = apply_stock_filters(stocks, filters)

    scan_market = _resolve_scan_market(filters.market)
    cap_tier_id = resolve_cap_tier_id(
        filters.market, cap_tier_id_from_label(cap_tier_label_ui)
    )
    mcap_floor = _resolve_mcap_floor(cap_tier_id)
    filter_key = _ht_filter_key(
        filters,
        cap_tier_id=cap_tier_id,
    )
    wide_open = (
        filters.market == "All"
        and not filters.sectors
        and not filters.industries
        and not filters.search.strip()
    )

    if not run_clicked:
        _try_restore_results(
            filtered,
            scan_market,
            mcap_floor=mcap_floor,
            filter_key=filter_key,
            allow_disk_cache=wide_open,
        )

    if run_clicked:
        universe = _filtered_universe(filtered, scan_market)
        if universe.empty:
            st.warning("No stocks match the current filters.")
            return

        progress = st.progress(0, text="Fetching market caps...")

        def _mcap_progress(done: int, total: int, _phase: str) -> None:
            progress.progress(
                done / max(total, 1),
                text=f"Market cap {done}/{total}...",
            )

        try:
            universe, _mcap_excluded = shrink_universe_by_mcap(
                universe,
                min_cr=mcap_floor,
                progress_callback=_mcap_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Market-cap fetch failed: {exc}")
            return

        if cap_tier_id not in ("all", ""):
            universe, _tier_excluded = apply_cap_tier_filter(universe, cap_tier_id)

        if universe.empty:
            progress.empty()
            if mcap_floor > 0:
                st.warning(
                    f"No listings with market cap ≥ ₹{mcap_floor:.0f} Cr "
                    f"in the current selection."
                )
            else:
                st.warning("No stocks match the current filters.")
            return

        progress.progress(0, text=f"Fetching fundamentals (0/{len(universe)})...")

        def _progress(done: int, total: int) -> None:
            progress.progress(
                done / max(total, 1),
                text=f"Fundamentals {done}/{total}...",
            )

        try:
            result = run_intrinsic_value_scan(
                universe,
                min_mcap_cr=mcap_floor,
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
                universe,
                min_mcap_cr=mcap_floor,
                min_sector_companies=1,
                max_hours=HEADWIND_IV_CACHE_HOURS,
            )
            if partial:
                if wide_open:
                    save_cached_headwind_scan(
                        partial, scan_market=scan_market, min_mcap_cr=mcap_floor
                    )
                _apply_scan_result(partial, scan_market, filter_key=filter_key)
                st.rerun()
            scanned = int(result.get("scanned") or len(universe))
            with_data = int(result.get("with_data") or 0)
            st.error(
                f"No fundamentals returned ({with_data}/{scanned} stocks). "
                "Try narrowing sector/industry filters, or run again in a few minutes "
                "if Yahoo is rate-limiting."
            )
            return

        if wide_open:
            save_cached_headwind_scan(
                result, scan_market=scan_market, min_mcap_cr=mcap_floor
            )
        _apply_scan_result(result, scan_market, filter_key=filter_key)
        st.rerun()

    if st.session_state.get("ht_filter_key") not in (None, filter_key):
        hint = filter_caption_suffix(filters, extra="")
        if hint:
            st.info(f"Filters changed — click **Run scan** — {hint}.")
        else:
            st.info("Filters changed — click **Run scan** to refresh the board.")
        return

    ranked = _as_df(st.session_state.get("ht_ranked"))
    ranked = ensure_pe_ratios(ranked, max_hours=HEADWIND_IV_CACHE_HOURS)
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
        hint = filter_caption_suffix(filters, extra="")
        if hint:
            st.info(f"Click **Run scan** — {hint}.")
        else:
            st.info("Click **Run scan** to build the headwind / tailwind board.")
        return

    industry_col = _resolve_ht_industry_col(
        ranked, safe_str(st.session_state.get("ht_industry_col"))
    )
    ranked, sectors = _narrow_ht_results(ranked, sectors, filtered, industry_col)
    if sectors is None or sectors.empty or ranked.empty:
        hint = filter_caption_suffix(filters, extra="")
        st.warning(
            f"No H&T results for the current filters{(' — ' + hint) if hint else ''}."
        )
        return

    universe_n = len(filtered)
    shown_n = len(ranked)
    suffix = filter_caption_suffix(filters, extra="")
    extra = f" · {suffix}" if suffix else ""
    st.caption(
        f"**{shown_n:,}** stocks with fundamentals · **{universe_n:,}** in filter · "
        f"cache ≤ **{HEADWIND_IV_CACHE_HOURS}h**{extra} · "
        f"**Run scan** to refresh missing names"
    )

    tab_all, tab_trend = st.tabs(["All", "Trend bars"])

    market_label = result_market or scan_market

    with tab_all:
        render_all_drilldown(
            sectors,
            ranked,
            industry_col,
            min_mcap_cr=mcap_floor,
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

    ranked = ensure_pcf_values(
        ranked,
        max_hours=HEADWIND_IV_CACHE_HOURS,
        fetch_missing=False,
    )

    board = sectors.reset_index(drop=True)
    stocks_map = _stocks_by_sector(board, ranked, industry_col)
    max_stocks = max((len(v) for v in stocks_map.values()), default=0)
    drill_html = build_headwind_drilldown_html(
        board,
        ranked,
        industry_col,
        min_mcap_cr=min_mcap_cr,
        title=title,
        standalone=True,
        stocks_map=stocks_map,
    )
    embed_html_iframe(
        drill_html,
        height=headwind_drilldown_iframe_height(
            len(board),
            max_sector_stocks=max_stocks,
        ),
    )

