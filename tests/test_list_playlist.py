"""List dropdown — Holdings + fund watchlists (not Market)."""

from __future__ import annotations

import pandas as pd

from stocks.scans.list_playlist import LIST_ALL_LABEL, list_options
from stocks.scans.scan_playlists import SCAN_PLAYLIST_LABELS, insert_scan_playlist_markets
from stocks.scans.holdings_playlist import HOLDINGS_PLAYLIST_LABEL
from stocks.shared.fund_watchlists import FUND_WATCHLIST_PLAYLIST_LABELS
from stocks.listings.stocks_data import filter_stocks, market_options


def test_list_options_include_holdings_and_funds():
    opts = list_options()
    assert opts[0] == LIST_ALL_LABEL
    assert HOLDINGS_PLAYLIST_LABEL in opts
    for label in FUND_WATCHLIST_PLAYLIST_LABELS:
        assert label in opts


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
    assert HOLDINGS_PLAYLIST_LABEL not in opts
    for label in FUND_WATCHLIST_PLAYLIST_LABELS:
        assert label not in opts
    for label in SCAN_PLAYLIST_LABELS:
        assert label in opts


def test_insert_scan_playlist_markets_skips_list_playlists():
    out = insert_scan_playlist_markets(["All", "NSE"])
    assert HOLDINGS_PLAYLIST_LABEL not in out
    assert "NSE" in out
