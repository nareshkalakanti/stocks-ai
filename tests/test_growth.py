"""Growth strategy metrics and scoring."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.growth.strategy import (
    compute_growth_metrics,
    gross_profit_margin,
    net_profit_margin,
    operating_margin,
    return_on_assets,
    return_on_equity,
    sales_cagr,
    sales_growth_yoy,
    score_growth,
)


def _sample_statements() -> tuple[pd.DataFrame, pd.DataFrame]:
    # Columns newest → oldest (yfinance style).
    cols = pd.to_datetime(["2024-03-31", "2023-03-31", "2022-03-31", "2021-03-31"])
    financials = pd.DataFrame(
        {
            cols[0]: [200.0, 80.0, 40.0, 50.0, 60.0],
            cols[1]: [160.0, 64.0, 28.0, 40.0, 45.0],
            cols[2]: [130.0, 52.0, 20.0, 32.0, 35.0],
            cols[3]: [100.0, 40.0, 14.0, 25.0, 28.0],
        },
        index=[
            "Total Revenue",
            "Cost Of Revenue",
            "Net Income",
            "Operating Income",
            "Gross Profit",
        ],
    )
    balance = pd.DataFrame(
        {
            cols[0]: [400.0, 200.0],
            cols[1]: [360.0, 180.0],
            cols[2]: [320.0, 160.0],
            cols[3]: [280.0, 140.0],
        },
        index=["Total Assets", "Stockholders Equity"],
    )
    return financials, balance


def test_sales_growth_and_margins():
    financials, balance = _sample_statements()
    assert sales_growth_yoy(financials) == 25.0  # (200-160)/160
    assert gross_profit_margin(financials) == 30.0  # 60/200
    assert net_profit_margin(financials) == 20.0  # 40/200
    assert operating_margin(financials) == 25.0  # 50/200
    # CAGR 3Y: (200/100)^(1/3)-1 ≈ 25.99%
    assert abs(sales_cagr(financials) - 25.99) < 0.1
    # ROA: 40 / ((400+360)/2) = 10.53
    assert abs(return_on_assets(financials, balance) - 10.53) < 0.05
    # ROE: 40 / ((200+180)/2) = 21.05
    assert abs(return_on_equity(financials, balance) - 21.05) < 0.05


def test_compute_growth_metrics_uses_info_fallbacks():
    metrics = compute_growth_metrics(
        None,
        None,
        {
            "revenueGrowth": 0.18,
            "grossMargins": 0.40,
            "profitMargins": 0.12,
            "operatingMargins": 0.16,
            "returnOnAssets": 0.08,
            "returnOnEquity": 0.20,
            "debtToEquity": 45.0,  # Yahoo percent → 0.45
            "trailingPE": 22.0,
        },
    )
    assert metrics["sales_growth"] == 18.0
    assert metrics["gross_margin"] == 40.0
    assert metrics["net_margin"] == 12.0
    assert metrics["operating_margin"] == 16.0
    assert metrics["roa"] == 8.0
    assert metrics["roe"] == 20.0
    assert metrics["debt_to_equity"] == 0.45
    assert metrics["pe_ratio"] == 22.0


def test_score_growth_keeps_passers():
    df = pd.DataFrame(
        [
            {
                "ticker": "GROW",
                "sales_cagr": 22.0,
                "profit_cagr": 20.0,
                "operating_margin": 18.0,
                "roe": 22.0,
                "debt_to_equity": 0.5,
                "pe_ok": True,
            },
            {
                "ticker": "WEAK",
                "sales_cagr": 5.0,
                "profit_cagr": 4.0,
                "operating_margin": 6.0,
                "roe": 8.0,
                "debt_to_equity": 3.5,
                "pe_ok": False,
            },
        ]
    )
    scored = score_growth(df)
    assert list(scored["ticker"]) == ["GROW"]
    assert scored.iloc[0]["growth_checks_pass"] >= 4
