import pandas as pd

from stocks.listings.stocks_data import (
    NSE_FAMILY_LABEL,
    apply_market_column_filter,
    market_filter_labels,
    market_options,
)
from stocks.scans.scan_playlists import format_market_option, market_option_count


def _mini_stocks() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"],
            "market": ["NSE", "NSE SME", "BSE"],
        }
    )


def test_market_filter_nse_mainboard_only():
    stocks = _mini_stocks()
    nse = apply_market_column_filter(stocks, "NSE")
    assert list(nse["ticker"]) == ["AAA"]


def test_market_filter_nse_family_label():
    stocks = _mini_stocks()
    both = apply_market_column_filter(stocks, NSE_FAMILY_LABEL)
    assert set(both["ticker"]) == {"AAA", "BBB"}


def test_market_options_include_family_and_plain_nse():
    stocks = _mini_stocks()
    opts = market_options(stocks, include_scan_playlists=False)
    assert NSE_FAMILY_LABEL in opts
    assert "NSE" in opts
    assert "NSE SME" in opts


def test_format_market_option_labels():
    stocks = _mini_stocks()
    assert "NSE + SME" in format_market_option(stocks, NSE_FAMILY_LABEL)
    assert format_market_option(stocks, "NSE").startswith("NSE (")
    assert market_option_count(stocks, "NSE") == 1
    assert market_option_count(stocks, NSE_FAMILY_LABEL) == 2
