"""Early Edge — scan playlist from Early Edge watchlist."""

from __future__ import annotations

from stocks.shared.early_edge import (
    EARLY_EDGE_PLAYLIST_LABEL,
    early_edge_count,
    early_edge_playlist_listings,
    is_early_edge_playlist,
)

__all__ = [
    "EARLY_EDGE_PLAYLIST_LABEL",
    "early_edge_playlist_count",
    "early_edge_playlist_listings",
    "is_early_edge_playlist",
]


def early_edge_playlist_count(market: str | None = None) -> int:
    _ = market
    return early_edge_count()
