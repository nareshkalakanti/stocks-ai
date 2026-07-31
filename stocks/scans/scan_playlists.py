"""Curated scan playlists available on all strategy pages."""

from __future__ import annotations

import pandas as pd

from stocks.scans.business_groups_playlist import (
    BUSINESS_GROUPS_PLAYLIST_LABEL,
    business_groups_playlist_count,
    business_groups_playlist_listings,
    is_business_groups_playlist,
)
from stocks.scans.ds_playlist import (
    DS_PLAYLIST_LABEL,
    ds_playlist_count,
    ds_playlist_listings,
    is_ds_playlist,
)
from stocks.scans.early_edge_playlist import (
    EARLY_EDGE_PLAYLIST_LABEL,
    early_edge_playlist_count,
    early_edge_playlist_listings,
    is_early_edge_playlist,
)
from stocks.scans.fund_watchlist_playlist import (
    FUND_WATCHLIST_PLAYLIST_LABELS,
    fund_watchlist_playlist_count,
    fund_watchlist_playlist_listings,
    is_fund_watchlist_playlist,
)
from stocks.scans.holdings_playlist import (
    HOLDINGS_PLAYLIST_LABEL,
    holdings_playlist_count,
    holdings_playlist_listings,
    is_holdings_playlist,
)
from stocks.scans.nifty_index_playlist import (
    NIFTY_PLAYLIST_LABELS,
    is_nifty_index_playlist,
    nifty_playlist_count,
    nifty_playlist_listings,
)
from stocks.core.text_utils import safe_str

# Personal / fund lists — Watching page only (not Quant Market dropdown).
WATCHING_ONLY_PLAYLIST_LABELS = (
    HOLDINGS_PLAYLIST_LABEL,
    *FUND_WATCHLIST_PLAYLIST_LABELS,
)

# Index / curated universes still available on Strategy scans.
SCAN_MARKET_PLAYLIST_LABELS = (
    EARLY_EDGE_PLAYLIST_LABEL,
    *NIFTY_PLAYLIST_LABELS,
    DS_PLAYLIST_LABEL,
    BUSINESS_GROUPS_PLAYLIST_LABEL,
)

SCAN_PLAYLIST_LABELS = WATCHING_ONLY_PLAYLIST_LABELS + SCAN_MARKET_PLAYLIST_LABELS

_LEGACY_PLAYLIST_LABELS = frozenset({"Parents", "Spinoffs"})
_WATCHING_ONLY_SET = frozenset(WATCHING_ONLY_PLAYLIST_LABELS)


def is_scan_playlist(market: str) -> bool:
    return (
        is_holdings_playlist(market)
        or is_early_edge_playlist(market)
        or is_fund_watchlist_playlist(market)
        or is_ds_playlist(market)
        or is_business_groups_playlist(market)
        or is_nifty_index_playlist(market)
    )


def cap_tier_select_disabled(market: str) -> bool:
    """D&S fixes the universe; index playlists keep optional cap-tier narrowing."""
    return is_ds_playlist(market)


def insert_scan_playlist_markets(markets: list[str]) -> list[str]:
    """Insert scan playlist labels after 'All' in the market dropdown."""
    result = ["All"]
    for label in SCAN_MARKET_PLAYLIST_LABELS:
        if label not in result:
            result.append(label)
    for market in markets:
        if (
            market != "All"
            and market not in result
            and market not in _LEGACY_PLAYLIST_LABELS
            and market not in _WATCHING_ONLY_SET
        ):
            result.append(market)
    return result


def scan_playlist_listings(
    stocks: pd.DataFrame,
    market: str,
    *,
    sector: str | list[str] = "All",
    search: str = "",
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    if is_holdings_playlist(market):
        return holdings_playlist_listings(
            stocks,
            sector=sector,
            search=search,
            industry=industry,
            sub_sector=sub_sector,
        )
    if is_early_edge_playlist(market):
        return early_edge_playlist_listings(
            stocks,
            sector=sector,
            search=search,
            industry=industry,
            sub_sector=sub_sector,
        )
    if is_fund_watchlist_playlist(market):
        return fund_watchlist_playlist_listings(
            stocks,
            market,
            sector=sector,
            search=search,
            industry=industry,
            sub_sector=sub_sector,
        )
    if is_nifty_index_playlist(market):
        return nifty_playlist_listings(
            stocks,
            market,
            sector=sector,
            search=search,
            industry=industry,
            sub_sector=sub_sector,
        )
    if is_ds_playlist(market):
        return ds_playlist_listings(
            stocks,
            sector=sector,
            search=search,
            industry=industry,
            sub_sector=sub_sector,
        )
    if is_business_groups_playlist(market):
        return business_groups_playlist_listings(
            stocks,
            sector=sector,
            search=search,
            industry=industry,
            sub_sector=sub_sector,
        )
    raise ValueError(f"Not a scan playlist: {market}")


def scan_playlist_count(market: str) -> int:
    if is_holdings_playlist(market):
        return holdings_playlist_count()
    if is_early_edge_playlist(market):
        return early_edge_playlist_count(market)
    if is_fund_watchlist_playlist(market):
        return fund_watchlist_playlist_count(market)
    if is_nifty_index_playlist(market):
        # Cache-only — avoid live NSE fetches while building Market dropdowns.
        return nifty_playlist_count(market, seed_if_empty=False)
    if is_ds_playlist(market):
        return ds_playlist_count()
    if is_business_groups_playlist(market):
        return business_groups_playlist_count(seed_if_empty=True)
    return 0


def market_option_count(stocks: pd.DataFrame, market: str) -> int:
    """Stock count shown beside each Market dropdown option."""
    if market == "All":
        return len(stocks)
    if is_scan_playlist(market):
        return scan_playlist_count(market)
    if not stocks.empty and "market" in stocks.columns:
        from stocks.listings.stocks_data import market_filter_labels

        labels = market_filter_labels(market)
        if labels is None:
            return len(stocks)
        return int(stocks["market"].astype(str).isin(labels).sum())
    return 0


def format_market_option(stocks: pd.DataFrame, market: str) -> str:
    from stocks.listings.stocks_data import NSE_FAMILY_LABEL

    if market == NSE_FAMILY_LABEL:
        return f"NSE + SME ({market_option_count(stocks, market):,})"
    return f"{market} ({market_option_count(stocks, market):,})"


def scan_playlist_note(market: str) -> str:
    if not is_scan_playlist(market):
        return ""
    if is_holdings_playlist(market):
        label = HOLDINGS_PLAYLIST_LABEL
    elif is_early_edge_playlist(market):
        label = EARLY_EDGE_PLAYLIST_LABEL
    elif is_fund_watchlist_playlist(market):
        label = market
    elif is_nifty_index_playlist(market):
        label = market
    elif is_ds_playlist(market):
        label = DS_PLAYLIST_LABEL
    else:
        label = BUSINESS_GROUPS_PLAYLIST_LABEL
    return f" · **{label}** ({scan_playlist_count(market)} stocks)"
