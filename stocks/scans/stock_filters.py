"""Shared market / industry / sector filter bar for all scan pages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import pandas as pd
import streamlit as st

from stocks.core.text_utils import safe_str

from stocks.scans.scan_playlists import (
    format_market_option,
    is_scan_playlist,
    scan_playlist_listings,
)
from stocks.scans.ds_playlist import DS_PLAYLIST_LABEL
from stocks.listings.stocks_data import (
    filter_stocks,
    format_option_with_count,
    industry_option_counts,
    industry_options,
    market_options,
    sector_option_counts,
    sector_options,
)

# Default session key prefix — filters persist when switching sidebar pages.
_DEFAULT_KEY_PREFIX = "sf"


def _filter_session_keys(prefix: str) -> tuple[str, str, str, str]:
    p = prefix.strip() or _DEFAULT_KEY_PREFIX
    return (
        f"{p}_market",
        f"{p}_industries",
        f"{p}_sectors",
        f"{p}_search",
    )


@dataclass(frozen=True)
class StockFilters:
    market: str
    sectors: list[str]
    industries: list[str]
    search: str = ""

    @property
    def nse_mode(self) -> bool:
        """Kept for callers that gate NSE-specific UI; filters apply to all markets."""
        return self.market == "NSE"


def _clear_keys(*keys: str) -> None:
    """Reset widget keys from an ``on_change`` callback (safe outside widget body)."""
    for key in keys:
        st.session_state[key] = []


def _multiselect(
    label: str,
    options: list[str],
    *,
    key: str,
    placeholder: str,
    help_text: str | None = None,
    disabled: bool = False,
    format_func: Callable[[str], str] | None = None,
    on_change: Callable[[], None] | None = None,
) -> list[str]:
    kwargs: dict = {
        "label": label,
        "options": options,
        "key": key,
        "placeholder": placeholder,
        "disabled": disabled,
    }
    if help_text:
        kwargs["help"] = help_text
    if format_func is not None:
        kwargs["format_func"] = format_func
    if on_change is not None:
        kwargs["on_change"] = on_change
    selected = st.multiselect(**kwargs)
    # Drop stale values if options shrank (do not write back to session_state).
    if not isinstance(selected, list):
        return []
    return [v for v in selected if v in options]


def _market_frame(stocks: pd.DataFrame, market: str) -> pd.DataFrame:
    if market == "All":
        return stocks
    if is_scan_playlist(market):
        return scan_playlist_listings(stocks, market)
    return stocks[stocks["market"] == market]

def render_sector_selectbox(
    stocks: pd.DataFrame,
    market: str,
    *,
    key: str,
    market_frame: pd.DataFrame | None = None,
    disabled: bool = False,
) -> str:
    mframe = market_frame if market_frame is not None else _market_frame(stocks, market)
    opts = sector_options(stocks, mframe)
    counts = sector_option_counts(mframe, opts[1:])
    return st.selectbox(
        "Sector",
        opts,
        key=key,
        disabled=disabled,
        format_func=lambda label: (
            f"All ({len(mframe):,})"
            if label == "All"
            else format_option_with_count(label, counts.get(label, 0))
        ),
    )


def render_industry_selectbox(
    stocks: pd.DataFrame,
    market: str,
    sector: str,
    *,
    key: str,
    market_frame: pd.DataFrame | None = None,
    disabled: bool = False,
) -> str:
    mframe = market_frame if market_frame is not None else _market_frame(stocks, market)
    if sector != "All" and "sector" in mframe.columns:
        industry_scope = mframe[mframe["sector"].astype(str).str.strip() == sector]
    else:
        industry_scope = mframe
    opts = industry_options(stocks, industry_scope)
    counts = industry_option_counts(industry_scope, opts[1:])
    return st.selectbox(
        "Sub sector",
        opts,
        key=key,
        disabled=disabled,
        format_func=lambda label: (
            f"All ({len(industry_scope):,})"
            if label == "All"
            else format_option_with_count(label, counts.get(label, 0))
        ),
    )


def render_industry_sector_selectboxes(
    stocks: pd.DataFrame,
    market: str,
    *,
    industry_key: str,
    sector_key: str,
    market_frame: pd.DataFrame | None = None,
) -> tuple[str, str]:
    """Single-select Sector + Sub sector (both widgets in current Streamlit column)."""
    mframe = market_frame if market_frame is not None else _market_frame(stocks, market)
    sector = render_sector_selectbox(
        stocks, market, key=sector_key, market_frame=mframe
    )
    industry = render_industry_selectbox(
        stocks, market, sector, key=industry_key, market_frame=mframe
    )
    return industry, sector


def render_stock_filters(
    stocks: pd.DataFrame,
    *,
    include_search: bool = False,
    include_scan_playlists: bool = True,
    cols: tuple | None = None,
    key_prefix: str = _DEFAULT_KEY_PREFIX,
) -> StockFilters:
    """Render Market · Sector · Sub sector filter row.

    Sector is the parent: Sub sector options come only from stocks in the
    selected display sector(s), so options stay aligned and nothing in that
    sector is hidden from the parent filter.
    """
    key_market, key_industries, key_sectors, key_search = _filter_session_keys(key_prefix)

    if key_market not in st.session_state:
        st.session_state[key_market] = "All"
    elif st.session_state[key_market] in {"Parents", "Spinoffs"}:
        st.session_state[key_market] = DS_PLAYLIST_LABEL
    for key in (key_industries, key_sectors):
        if key not in st.session_state:
            st.session_state[key] = []
    if key_search not in st.session_state:
        st.session_state[key_search] = ""
    # Drop legacy sub-sector session state (same values as industry for NSE).
    st.session_state.pop("sf_sub_sectors", None)

    if cols is None:
        widths = [0.9, 1.2, 1.2, 1.6] if include_search else [0.9, 1.2, 1.2]
        cols = tuple(st.columns(widths))
    else:
        need = 4 if include_search else 3
        if len(cols) < need:
            raise ValueError(f"render_stock_filters cols needs {need} columns, got {len(cols)}")

    with cols[0]:
        market_opts = market_options(stocks, include_scan_playlists=include_scan_playlists)
        if st.session_state[key_market] not in market_opts:
            st.session_state[key_market] = "All"
        market = st.selectbox(
            "Market",
            market_opts,
            key=key_market,
            format_func=lambda m: format_market_option(stocks, m),
            on_change=partial(_clear_keys, key_sectors, key_industries),
        )

    mframe = _market_frame(stocks, market)
    sector_opts = sector_options(stocks, mframe)[1:]
    sector_counts = sector_option_counts(mframe, sector_opts)

    with cols[1]:
        sectors = _multiselect(
            "Sector",
            sector_opts,
            key=key_sectors,
            placeholder="All sectors",
            help_text="Broad display group (e.g. Agriculture & Agro)",
            format_func=lambda label: format_option_with_count(
                label, sector_counts.get(label, 0)
            ),
            on_change=partial(_clear_keys, key_industries),
        )

    if sectors and "sector" in mframe.columns:
        industry_scope = mframe[mframe["sector"].astype(str).str.strip().isin(sectors)]
    else:
        industry_scope = mframe
    industry_opts = industry_options(stocks, industry_scope)[1:]
    industry_counts = industry_option_counts(industry_scope, industry_opts)

    with cols[2]:
        industries = _multiselect(
            "Sub sector",
            industry_opts,
            key=key_industries,
            placeholder="All sub sectors",
            help_text=(
                "Fine tags inside the selected sector "
                "(e.g. Agro Products, Seeds under Agriculture & Agro)"
            ),
            format_func=lambda label: format_option_with_count(
                label, industry_counts.get(label, 0)
            ),
        )

    search = ""
    if include_search:
        with cols[3]:
            search = st.text_input(
                "Search",
                placeholder="Ticker or company name",
                key=key_search,
            )

    return StockFilters(
        market=market,
        sectors=sectors,
        industries=industries,
        search=search,
    )


def apply_stock_filters(stocks: pd.DataFrame, filters: StockFilters) -> pd.DataFrame:
    return filter_stocks(
        stocks,
        filters.market,
        filters.sectors or "All",
        filters.search,
        industry=filters.industries or "All",
    )


def filter_caption_suffix(
    filters: StockFilters,
    *,
    extra: str = "",
) -> str:
    """Short human-readable suffix for scan captions."""
    from stocks.listings.stocks_data import classifier_filter_label

    parts: list[str] = []
    if filters.market != "All":
        parts.append(filters.market)
    sector_lbl = classifier_filter_label("sectors", filters.sectors)
    if sector_lbl:
        parts.append(sector_lbl)
    industry_lbl = classifier_filter_label("sub sectors", filters.industries)
    if industry_lbl:
        parts.append(industry_lbl)
    extra = safe_str(extra).strip()
    if extra:
        parts.append(extra.strip(" ·"))
    return " · ".join(parts)
