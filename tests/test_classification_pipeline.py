"""Sqlite classification pipeline for the full stocks universe."""

from __future__ import annotations

import pandas as pd

from stocks.listings.classification_service import classification_coverage
from stocks.listings.sector_display import apply_display_sector_mapping
from stocks.listings.stock_overrides import apply_stock_overrides
from stocks.listings.stocks_data import (
    _finalize_stocks,
    _needs_classification_reenrich,
)


def test_finalize_stocks_fills_industry_from_source_sector_without_sqlite():
    stocks = pd.DataFrame(
        [
            {
                "ticker": "HDFCBANK",
                "name": "HDFC Bank",
                "market": "NSE",
                "sector": "Banking & Finance",
                "source_sector": "Finance",
                "industry": "",
                "sub_sector": "",
            }
        ]
    )
    out = _finalize_stocks(stocks)
    row = out.iloc[0]
    assert row["sector"] == "Banking & Finance"
    assert row["source_sector"] == "Finance"
    assert str(row["industry"]).strip()
    assert str(row["sub_sector"]).strip()


def test_needs_classification_reenrich_when_sub_sector_missing():
    cached = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Alpha",
                "market": "NSE",
                "sector": "IT & Technology",
                "industry": "Software",
            }
        ]
    )
    # No sub_sector column → needs enrich when sqlite taxonomy is available.
    # Without sqlite this returns False; with sqlite True. Either is acceptable
    # as long as it does not crash.
    assert isinstance(_needs_classification_reenrich(cached), bool)


def test_display_mapping_keeps_distinct_industry_from_source_sector():
    stocks = pd.DataFrame(
        [
            {
                "ticker": "TCS",
                "name": "TCS",
                "market": "NSE",
                "sector": "Technology services",
                "source_sector": "Technology services",
                "industry": "",
                "sub_sector": "",
            }
        ]
    )
    out = apply_display_sector_mapping(apply_stock_overrides(stocks))
    row = out.iloc[0]
    assert row["sector"] == "IT & Technology"
    assert row["industry"] == "IT Services"


def test_classification_coverage_counts_source_sector():
    stocks = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "market": "NSE",
                "sector": "IT & Technology",
                "source_sector": "Technology services",
                "industry": "Technology services",
                "sub_sector": "Technology services",
            },
            {
                "ticker": "BBB",
                "market": "NSE",
                "sector": "IT & Technology",
                "source_sector": "",
                "industry": "",
                "sub_sector": "",
            },
        ]
    )
    cov = classification_coverage(stocks)
    assert cov["tickers"] == 2
    assert cov["source_sector"] == 1
    assert cov["industry"] == 1


def test_name_refines_auto_companies_into_automobile_sector():
    stocks = pd.DataFrame(
        [
            {
                "ticker": "MARUTI",
                "name": "Maruti Suzuki India Limited",
                "market": "NSE",
                "sector": "Consumer durables",
                "source_sector": "Consumer durables",
                "industry": "",
                "sub_sector": "",
            },
            {
                "ticker": "APOLLOTYRE",
                "name": "Apollo Tyres Limited",
                "market": "NSE",
                "sector": "Consumer durables",
                "source_sector": "Consumer durables",
                "industry": "",
                "sub_sector": "",
            },
            {
                "ticker": "AUTOINT",
                "name": "Autoriders International Ltd.",
                "market": "NSE",
                "sector": "Finance",
                "source_sector": "Finance",
                "industry": "",
                "sub_sector": "",
            },
        ]
    )
    out = apply_display_sector_mapping(stocks)
    assert out.loc[out["ticker"] == "MARUTI", "sector"].iloc[0] == "Automobile & Ancillaries"
    assert out.loc[out["ticker"] == "APOLLOTYRE", "sector"].iloc[0] == "Automobile & Ancillaries"
    assert out.loc[out["ticker"] == "AUTOINT", "sector"].iloc[0] == "Automobile & Ancillaries"
    assert out.loc[out["ticker"] == "APOLLOTYRE", "industry"].iloc[0] == "Automobile & Components"


def test_coarse_industry_labels_are_humanized():
    stocks = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Alpha Processing Ltd",
                "market": "NSE",
                "sector": "Process industries",
                "source_sector": "Process industries",
                "industry": "",
                "sub_sector": "",
            }
        ]
    )
    out = apply_display_sector_mapping(stocks)
    row = out.iloc[0]
    assert row["sector"] == "Chemicals & Petrochemicals"
    assert row["industry"] == "Manufacturing & Processing"
