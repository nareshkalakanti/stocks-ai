"""Small + Cheap — mcap band, P/S, and debt-free filter."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.small_cheap.strategy import (
    in_small_cheap_mcap_band,
    is_low_debt,
    score_small_cheap,
)


def test_mcap_band():
    assert in_small_cheap_mcap_band(20.0)
    assert in_small_cheap_mcap_band(200.0)
    assert not in_small_cheap_mcap_band(19.9)
    assert not in_small_cheap_mcap_band(200.1)


def test_is_low_debt():
    assert is_low_debt({"totalDebt": 0}) is True
    assert is_low_debt({"debtToEquity": 0}) is True
    assert is_low_debt({"totalDebt": 1_000_000}) is False
    assert is_low_debt({}) is None


def test_score_small_cheap_filters_cheap_debt_free():
    df = pd.DataFrame(
        [
            {
                "ticker": "GOOD",
                "market_cap_cr": 80.0,
                "price_to_sales": 0.4,
                "sales_growth": 12.0,
                "debt_free": True,
            },
            {
                "ticker": "DEBT",
                "market_cap_cr": 90.0,
                "price_to_sales": 0.5,
                "sales_growth": 20.0,
                "debt_free": False,
            },
            {
                "ticker": "RICH",
                "market_cap_cr": 90.0,
                "price_to_sales": 1.5,
                "sales_growth": 40.0,
                "debt_free": True,
            },
        ]
    )
    scored = score_small_cheap(df, debt_free_only=True)
    assert list(scored["ticker"]) == ["GOOD"]


def test_score_small_cheap_allows_debt_when_filter_off():
    df = pd.DataFrame(
        [
            {
                "ticker": "DEBT",
                "market_cap_cr": 90.0,
                "price_to_sales": 0.5,
                "debt_free": False,
            },
        ]
    )
    scored = score_small_cheap(df, debt_free_only=False)
    assert list(scored["ticker"]) == ["DEBT"]
