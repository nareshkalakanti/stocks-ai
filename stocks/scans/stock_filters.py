"""Shared market / industry / sector filter bar for all scan pages."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from stocks.scans.scan_playlists import (
    format_market_option,
    is_scan_playlist,
    scan_playlist_listings,
)
from stocks.scans.ds_playlist import DS_PLAYLIST_LABEL
from stocks.listings.stocks_data import (
    filter_stocks,
    industry_options,
    market_options,
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


def _prune(key: str, options: list[str]) -> list[str]:
    current = st.session_state.get(key, [])
    if not isinstance(current, list):
        current = []
    pruned = sorted({v for v in current if v in options})
    if pruned != current:
        st.session_state[key] = pruned
    return pruned


def _multiselect(
    label: str,
    options: list[str],
    *,
    key: str,
    placeholder: str,
    help_text: str | None = None,
    disabled: bool = False,
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
    return st.multiselect(**kwargs)


def _market_frame(stocks: pd.DataFrame, market: str) -> pd.DataFrame:
    if market == "All":
        return stocks
    if is_scan_playlist(market):
        return scan_playlist_listings(stocks, market)
    return stocks[stocks["market"] == market]

def render_industry_selectbox(
    stocks: pd.DataFrame,
    market: str,
    *,
    key: str,
    market_frame: pd.DataFrame | None = None,
    disabled: bool = False,
) -> str:
    mframe = market_frame if market_frame is not None else _market_frame(stocks, market)
    return st.selectbox(
        "Industry",
        industry_options(stocks, mframe),
        key=key,
        disabled=disabled,
    )


def render_sector_selectbox(
    stocks: pd.DataFrame,
    market: str,
    industry: str,
    *,
    key: str,
    market_frame: pd.DataFrame | None = None,
    disabled: bool = False,
) -> str:
    mframe = market_frame if market_frame is not None else _market_frame(stocks, market)
    if industry != "All" and "industry" in mframe.columns:
        sector_scope = mframe[mframe["industry"] == industry]
    else:
        sector_scope = mframe
    return st.selectbox(
        "Sector",
        sector_options(stocks, sector_scope),
        key=key,
        disabled=disabled,
    )


def render_industry_sector_selectboxes(
    stocks: pd.DataFrame,
    market: str,
    *,
    industry_key: str,
    sector_key: str,
    market_frame: pd.DataFrame | None = None,
) -> tuple[str, str]:
    """Single-select Industry + Sector (both widgets in current Streamlit column)."""
    mframe = market_frame if market_frame is not None else _market_frame(stocks, market)
    industry = render_industry_selectbox(
        stocks, market, key=industry_key, market_frame=mframe
    )
    sector = render_sector_selectbox(
        stocks, market, industry, key=sector_key, market_frame=mframe
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
    """Render Market · Industry · Sector filter row."""
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
        )

    mframe = _market_frame(stocks, market)
    industry_opts = industry_options(stocks, mframe)[1:]

    with cols[1]:
        industries = _multiselect(
            "Industry",
            industry_opts,
            key=key_industries,
            placeholder="All industries",
            help_text="Fine-grained label (e.g. Building Products - Pipes)",
        )
    industries = _prune(key_industries, industry_opts)

    if industries and "industry" in mframe.columns:
        sector_scope = mframe[mframe["industry"].isin(industries)]
    else:
        sector_scope = mframe
    sector_opts = sector_options(stocks, sector_scope)[1:]

    with cols[2]:
        sectors = _multiselect(
            "Sector",
            sector_opts,
            key=key_sectors,
            placeholder="All sectors",
            help_text="Broad group (e.g. Real Estate & Construction)",
        )
    sectors = _prune(key_sectors, sector_opts)

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


def filter_caption_suffix(filters: StockFilters) -> str:
    """Short human-readable suffix for scan captions."""
    from stocks.listings.stocks_data import classifier_filter_label

    parts: list[str] = []
    if filters.market != "All":
        parts.append(filters.market)
    industry_lbl = classifier_filter_label("industries", filters.industries)
    if industry_lbl:
        parts.append(industry_lbl)
    sector_lbl = classifier_filter_label("sectors", filters.sectors)
    if sector_lbl:
        parts.append(sector_lbl)
    return " · ".join(parts)
