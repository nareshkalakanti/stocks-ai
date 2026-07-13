"""Tests for NSE announcement demerger enrichment."""

from __future__ import annotations

import pandas as pd

from stocks.market.merger_demerger_enrich import (
    _parse_resulting_companies,
    build_name_ticker_map,
    enrich_demerger_dataframe,
    match_company_to_ticker,
)


def test_parse_resulting_companies_patterns():
    text = (
        "Scheme of Arrangement between Borosil Limited and "
        "Borosil Renewables Limited (Resulting Company)"
    )
    names = _parse_resulting_companies(text)
    assert "Borosil Renewables Limited" in names

    text2 = "Demerger between Foo Ltd and Bar Industries Ltd (Resulting Company)"
    assert "Bar Industries Ltd" in _parse_resulting_companies(text2)

    text3 = "transfer from Baz Corp, the Resulting Company to parent"
    assert "Baz Corp" in _parse_resulting_companies(text3)

    text4 = (
        "Arrangement between Aarti Industries Limited and "
        "Aarti Pharmalabs Limited and their Shareholders"
    )
    assert "Aarti Pharmalabs Limited" in _parse_resulting_companies(text4)


def test_match_company_to_ticker_prefix():
    stocks = pd.DataFrame(
        [
            {"ticker": "BORORENEW", "name": "Borosil Renewables Limited"},
            {"ticker": "BOROLTD", "name": "Borosil Limited"},
        ]
    )
    name_map = build_name_ticker_map(stocks)
    assert match_company_to_ticker("Borosil Renewables Limited", name_map) == "BORORENEW"


def test_enrich_demerger_dataframe_from_cache(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "ticker": "FOO",
                "company": "Foo Limited",
                "action_type": "Demerger",
                "ex_date": "2024-01-01",
            }
        ]
    )
    stocks = pd.DataFrame([{"ticker": "BAR", "name": "Bar Ventures Limited"}])

    monkeypatch.setattr(
        "stocks.market.merger_demerger_enrich.load_merger_demerger_enrich_cache",
        lambda tickers, max_hours: {
            "FOO": {
                "resulting_companies": ["Bar Ventures Limited"],
                "resulting_tickers": ["BAR"],
                "demerged_company": "Bar Ventures Limited",
                "demerged_ticker": "BAR",
            }
        },
    )
    monkeypatch.setattr(
        "stocks.market.merger_demerger_enrich.save_merger_demerger_enrich_cache",
        lambda rows: None,
    )

    out = enrich_demerger_dataframe(df, stocks, refresh=False)
    parent = out[out["ticker"] == "FOO"].iloc[0]
    assert parent["counterparty_company"] == "Bar Ventures Limited"
    assert parent["counterparty_ticker"] == "BAR"
    assert (out["ticker"] == "BAR").any()
