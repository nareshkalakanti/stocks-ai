"""NSE SME / Emerge listings — CSV parse + merge into stocks universe."""

from __future__ import annotations

import pandas as pd

from stocks.market.nse_sme_listings import (
    NSE_SME_MARKET,
    _parse_sme_csv,
    merge_nse_sme_into_stocks,
    stocks_need_nse_sme,
)


_SAMPLE_CSV = """SYMBOL,NAME_OF_COMPANY,SERIES,DATE_OF_LISTING,PAID_UP_VALUE,ISIN_NUMBER,FACE_VALUE,
HAPPY,Happy Steels Limited,ST,16-Jul-26,10,INE1GFG01011,10,
ICELCO,IC Electricals Company Limited,SM,10-Jul-26,10,INE0XE501015,10,
IGNOREME,Debt Thing,N1,01-Jan-20,10,INE000000001,10,
"""


def test_parse_sme_csv_keeps_equity_series():
    df = _parse_sme_csv(_SAMPLE_CSV)
    assert set(df["ticker"]) == {"HAPPY", "ICELCO"}
    assert (df["market"] == NSE_SME_MARKET).all()
    assert "IGNOREME" not in set(df["ticker"])


def test_merge_nse_sme_relocates_hf_nse_tags():
    base = pd.DataFrame(
        [
            {
                "ticker": "ICELCO",
                "name": "IC Electricals (HF)",
                "market": "NSE",
                "sector": "Industrials",
                "industry": "Engineering",
                "sub_sector": "Engineering",
                "source_sector": "Industrials",
            },
            {
                "ticker": "TCS",
                "name": "TCS",
                "market": "NSE",
                "sector": "IT",
                "industry": "IT",
                "sub_sector": "IT",
                "source_sector": "",
            },
        ]
    )
    sme = _parse_sme_csv(_SAMPLE_CSV)
    import stocks.market.nse_sme_listings as mod

    original = mod.fetch_nse_sme_listings
    mod.fetch_nse_sme_listings = lambda force=False: sme  # noqa: ARG005
    try:
        out = merge_nse_sme_into_stocks(base, force_fetch=False)
    finally:
        mod.fetch_nse_sme_listings = original

    sme_rows = out[out["market"] == NSE_SME_MARKET]
    nse_rows = out[out["market"] == "NSE"]
    assert set(sme_rows["ticker"]) >= {"HAPPY", "ICELCO"}
    assert "ICELCO" not in set(nse_rows["ticker"])
    assert "TCS" in set(nse_rows["ticker"])
    icelco = sme_rows[sme_rows["ticker"] == "ICELCO"].iloc[0]
    assert icelco["industry"] == "Engineering"


def test_stocks_need_nse_sme():
    empty = pd.DataFrame(columns=["ticker", "market"])
    assert stocks_need_nse_sme(empty) is True
    few = pd.DataFrame(
        [{"ticker": f"T{i}", "market": NSE_SME_MARKET} for i in range(10)]
    )
    assert stocks_need_nse_sme(few, min_count=50) is True
    many = pd.DataFrame(
        [{"ticker": f"T{i}", "market": NSE_SME_MARKET} for i in range(80)]
    )
    assert stocks_need_nse_sme(many, min_count=50) is False
