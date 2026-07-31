"""Holdings + fund watchlists — used on the Watching page (not Strategy toolbar)."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str
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
from stocks.shared.early_edge import EARLY_EDGE_PLAYLIST_LABEL

WATCHING_LIST_LABELS = (
    EARLY_EDGE_PLAYLIST_LABEL,
    HOLDINGS_PLAYLIST_LABEL,
    *FUND_WATCHLIST_PLAYLIST_LABELS,
)

_LIST_SET = frozenset(WATCHING_LIST_LABELS)


def is_watching_list(label: str) -> bool:
    return safe_str(label) in _LIST_SET


def watching_list_option_count(label: str) -> int:
    if label == EARLY_EDGE_PLAYLIST_LABEL:
        from stocks.shared.early_edge import load_early_edge_df

        df = load_early_edge_df()
        return len(df) if df is not None and not df.empty else 0
    if is_holdings_playlist(label):
        return holdings_playlist_count()
    if is_fund_watchlist_playlist(label):
        return fund_watchlist_playlist_count(label)
    return 0


def format_watching_list_option(label: str) -> str:
    n = watching_list_option_count(label)
    return f"{label} ({n:,})" if n else label


def list_playlist_listings(
    stocks: pd.DataFrame,
    list_label: str,
    *,
    sector: str | list[str] = "All",
    search: str = "",
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    if is_holdings_playlist(list_label):
        return holdings_playlist_listings(
            stocks,
            sector=sector,
            search=search,
            industry=industry,
            sub_sector=sub_sector,
        )
    if is_fund_watchlist_playlist(list_label):
        return fund_watchlist_playlist_listings(
            stocks,
            list_label,
            sector=sector,
            search=search,
            industry=industry,
            sub_sector=sub_sector,
        )
    raise ValueError(f"Not a list playlist: {list_label!r}")
