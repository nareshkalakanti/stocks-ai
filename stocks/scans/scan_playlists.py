"""Curated scan playlists available on all strategy pages."""

from __future__ import annotations

import pandas as pd

from stocks.scans.business_groups_playlist import (
    BUSINESS_GROUPS_PLAYLIST_LABEL,
    business_groups_playlist_count,
    business_groups_playlist_listings,
    is_business_groups_playlist,
)
from stocks.scans.holdings_playlist import (
    HOLDINGS_PLAYLIST_LABEL,
    holdings_playlist_count,
    holdings_playlist_listings,
    is_holdings_playlist,
)

SCAN_PLAYLIST_LABELS = (HOLDINGS_PLAYLIST_LABEL, BUSINESS_GROUPS_PLAYLIST_LABEL)


def is_scan_playlist(market: str) -> bool:
    return is_holdings_playlist(market) or is_business_groups_playlist(market)


def cap_tier_select_disabled(market: str) -> bool:
    """Holdings fixes the universe; Business Groups allows cap-tier filtering."""
    return is_holdings_playlist(market)


def insert_scan_playlist_markets(markets: list[str]) -> list[str]:
    """Insert playlist labels after 'All' in the market dropdown."""
    result = ["All"]
    for label in SCAN_PLAYLIST_LABELS:
        if label not in result:
            result.append(label)
    for market in markets:
        if market != "All" and market not in result:
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
    if is_business_groups_playlist(market):
        return business_groups_playlist_count()
    return 0


def scan_playlist_note(market: str) -> str:
    if not is_scan_playlist(market):
        return ""
    label = HOLDINGS_PLAYLIST_LABEL if is_holdings_playlist(market) else BUSINESS_GROUPS_PLAYLIST_LABEL
    return f" · **{label}** ({scan_playlist_count(market)} stocks)"
