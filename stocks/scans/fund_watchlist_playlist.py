"""Negen / Niveshaay — scan playlists from fund_watchlists (separate from Holdings)."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.shared.fund_watchlists import (
    FUND_WATCHLIST_PLAYLIST_LABELS,
    NEGEN_PLAYLIST_LABEL,
    NIVESHAAY_PLAYLIST_LABEL,
    fund_watchlist_count,
    fund_watchlist_playlist_listings,
    is_fund_watchlist_playlist,
    list_key_for_playlist,
)

__all__ = [
    "FUND_WATCHLIST_PLAYLIST_LABELS",
    "NEGEN_PLAYLIST_LABEL",
    "NIVESHAAY_PLAYLIST_LABEL",
    "fund_watchlist_playlist_count",
    "fund_watchlist_playlist_listings",
    "is_fund_watchlist_playlist",
]


def fund_watchlist_playlist_count(market: str) -> int:
    key = list_key_for_playlist(market)
    if not key:
        return 0
    return fund_watchlist_count(key)
