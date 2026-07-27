"""NSE mainboard EQUITY_L listings — CSV parse + merge into stocks universe."""

from __future__ import annotations

import pandas as pd

from stocks.market.nse_equity_listings import (
    NSE_MARKET,
    _parse_equity_csv,
    merge_nse_equity_into_stocks,
    stocks_need_nse_equity,
)


_SAMPLE_CSV = """SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE
RELIANCE,Reliance Industries Limited,EQ,06-Dec-1995,10,1,INE002A01018,10
BAJAJ-AUTO,Bajaj Auto Limited,EQ,26-May-2008,10,1,INE917I01010,10
TCS,Tata Consultancy Services Limited,BE,25-Aug-2004,1,1,INE467B01029,1
SKIPME,Some Bond,GB,01-Jan-2000,100,1,INE000000099,100
"""


def test_parse_equity_csv_keeps_equity_series():
    df = _parse_equity_csv(_SAMPLE_CSV)
    assert set(df["ticker"]) == {"RELIANCE", "BAJAJ-AUTO", "TCS"}
    assert (df["market"] == NSE_MARKET).all()
    assert "SKIPME" not in set(df["ticker"])
    assert "BAJAJ-AUTO" in set(df["ticker"])


def test_merge_nse_equity_replaces_mainboard_keeps_bse():
    base = pd.DataFrame(
        [
            {
                "ticker": "RELIANCE",
                "name": "Old Reliance",
                "market": "NSE",
                "sector": "Energy",
                "industry": "Oil",
                "sub_sector": "Oil",
                "source_sector": "Energy",
            },
            {
                "ticker": "STALE",
                "name": "Delisted",
                "market": "NSE",
                "sector": "",
                "industry": "",
                "sub_sector": "",
                "source_sector": "",
            },
            {
                "ticker": "500325",
                "name": "Reliance BSE",
                "market": "BSE",
                "sector": "Energy",
                "industry": "Oil",
                "sub_sector": "Oil",
                "source_sector": "",
            },
        ]
    )
    equity = _parse_equity_csv(_SAMPLE_CSV)
    import stocks.market.nse_equity_listings as mod

    original = mod.fetch_nse_equity_listings
    mod.fetch_nse_equity_listings = lambda force=False: equity  # noqa: ARG005
    try:
        out = merge_nse_equity_into_stocks(base, force_fetch=False)
    finally:
        mod.fetch_nse_equity_listings = original

    nse_rows = out[out["market"] == NSE_MARKET]
    bse_rows = out[out["market"] == "BSE"]
    assert set(nse_rows["ticker"]) == {"RELIANCE", "BAJAJ-AUTO", "TCS"}
    assert "STALE" not in set(nse_rows["ticker"])
    assert set(bse_rows["ticker"]) == {"500325"}
    reliance = nse_rows[nse_rows["ticker"] == "RELIANCE"].iloc[0]
    assert reliance["industry"] == "Oil"
    assert "Reliance Industries" in reliance["name"]


def test_stocks_need_nse_equity_low_count():
    empty = pd.DataFrame(columns=["ticker", "market"])
    assert stocks_need_nse_equity(empty) is True
    few = pd.DataFrame([{"ticker": f"T{i}", "market": NSE_MARKET} for i in range(10)])
    assert stocks_need_nse_equity(few, min_count=2000) is True
