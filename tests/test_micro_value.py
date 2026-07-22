"""Micro Value — mcap band + Mcap/Sales screen."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.micro_value.strategy import (
    in_micro_value_mcap_band,
    price_to_sales,
    score_micro_value,
)


def test_price_to_sales_from_info():
    assert price_to_sales({"priceToSalesTrailing12Months": 0.72}) == 0.72
    assert price_to_sales(
        {"marketCap": 50e7, "totalRevenue": 80e7}  # 50 Cr / 80 Cr = 0.625
    ) == 0.625


def test_mcap_band():
    assert in_micro_value_mcap_band(20.0)
    assert in_micro_value_mcap_band(200.0)
    assert in_micro_value_mcap_band(100.0)
    assert not in_micro_value_mcap_band(19.9)
    assert not in_micro_value_mcap_band(200.1)
    assert not in_micro_value_mcap_band(None)


def test_score_micro_value_keeps_cheap_in_band():
    df = pd.DataFrame(
        [
            {
                "ticker": "CHEAP",
                "market_cap_cr": 80.0,
                "price_to_sales": 0.4,
                "sales_growth": 12.0,
            },
            {
                "ticker": "RICH",
                "market_cap_cr": 90.0,
                "price_to_sales": 1.5,
                "sales_growth": 40.0,
            },
            {
                "ticker": "BIG",
                "market_cap_cr": 500.0,
                "price_to_sales": 0.3,
                "sales_growth": 20.0,
            },
        ]
    )
    scored = score_micro_value(df)
    assert list(scored["ticker"]) == ["CHEAP"]
    assert scored.iloc[0]["rank"] == 1
    assert scored.iloc[0]["mv_score"] is not None
