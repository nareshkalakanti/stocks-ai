"""Watching list — Early Edge, Holdings, fund watchlists."""

from __future__ import annotations

import pandas as pd

from stocks.scans.list_playlist import (
    WATCHING_LIST_LABELS,
    format_watching_list_option,
    is_watching_list,
)
from stocks.scans.holdings_playlist import HOLDINGS_PLAYLIST_LABEL
from stocks.scans.scan_playlists import WATCHING_ONLY_PLAYLIST_LABELS
from stocks.shared.early_edge import EARLY_EDGE_PLAYLIST_LABEL
from stocks.shared.fund_watchlists import FUND_WATCHLIST_PLAYLIST_LABELS
from stocks.listings.stocks_data import market_options


def test_watching_list_labels():
    assert WATCHING_LIST_LABELS[0] == EARLY_EDGE_PLAYLIST_LABEL
    assert HOLDINGS_PLAYLIST_LABEL in WATCHING_LIST_LABELS
    for label in FUND_WATCHLIST_PLAYLIST_LABELS:
        assert label in WATCHING_LIST_LABELS


def test_is_watching_list():
    assert is_watching_list(EARLY_EDGE_PLAYLIST_LABEL)
    assert is_watching_list(HOLDINGS_PLAYLIST_LABEL)
    for label in FUND_WATCHLIST_PLAYLIST_LABELS:
        assert is_watching_list(label)
    assert not is_watching_list("NSE")
    assert not is_watching_list("All")


def test_format_watching_list_option_returns_label():
    text = format_watching_list_option(EARLY_EDGE_PLAYLIST_LABEL)
    assert EARLY_EDGE_PLAYLIST_LABEL in text


def test_market_dropdown_excludes_holdings_and_funds():
    stocks = pd.DataFrame(
        {
            "ticker": ["A", "B"],
            "market": ["NSE", "NSE"],
            "name": ["A Ltd", "B Ltd"],
            "sector": ["IT & Technology", "Banking"],
        }
    )
    opts = market_options(stocks, include_scan_playlists=True)
    for label in WATCHING_ONLY_PLAYLIST_LABELS:
        assert label not in opts
