"""Cash Quality metrics and scoring."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.cash_quality.strategy import (
    cash_conversion_cycle_years,
    cash_to_tax_ratio,
    compute_cash_quality_metrics,
    croic_ratio,
    ocf_vs_ebitda_growth,
    score_cash_quality,
)


def _sample_statements() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cols = pd.to_datetime(
        [
            "2024-03-31",
            "2023-03-31",
            "2022-03-31",
            "2021-03-31",
            "2020-03-31",
            "2019-03-31",
        ]
    )
    financials = pd.DataFrame(
        {
            cols[0]: [500.0, 200.0, 120.0, 40.0],
            cols[1]: [450.0, 180.0, 100.0, 35.0],
            cols[2]: [400.0, 160.0, 85.0, 30.0],
            cols[3]: [350.0, 140.0, 70.0, 28.0],
            cols[4]: [300.0, 120.0, 55.0, 25.0],
            cols[5]: [250.0, 100.0, 45.0, 22.0],
        },
        index=["Total Revenue", "Cost Of Revenue", "EBITDA", "Tax Provision"],
    )
    balance = pd.DataFrame(
        {
            cols[0]: [80.0, 50.0, 40.0, 30.0, 300.0, 500.0],
            cols[1]: [70.0, 45.0, 38.0, 28.0, 280.0, 470.0],
            cols[2]: [60.0, 40.0, 35.0, 25.0, 260.0, 440.0],
            cols[3]: [55.0, 35.0, 32.0, 22.0, 240.0, 410.0],
            cols[4]: [50.0, 30.0, 30.0, 20.0, 220.0, 380.0],
            cols[5]: [45.0, 28.0, 28.0, 18.0, 200.0, 350.0],
        },
        index=[
            "Cash And Cash Equivalents",
            "Inventory",
            "Accounts Receivable",
            "Accounts Payable",
            "Stockholders Equity",
            "Invested Capital",
        ],
    )
    cashflow = pd.DataFrame(
        {
            cols[0]: [100.0, -20.0],
            cols[1]: [90.0, -18.0],
            cols[2]: [80.0, -16.0],
            cols[3]: [70.0, -14.0],
            cols[4]: [60.0, -12.0],
            cols[5]: [50.0, -10.0],
        },
        index=["Operating Cash Flow", "Capital Expenditure"],
    )
    return financials, balance, cashflow


def test_cash_to_tax_and_croic():
    financials, balance, cashflow = _sample_statements()
    # Cash 5Y ago (2019) = 45, tax that year = 22 → 45/22 ≈ 2.045
    assert abs(cash_to_tax_ratio(balance, financials, years=5) - 2.045) < 0.01
    # CROIC = (100 - 20) / 500 = 0.16
    assert croic_ratio(cashflow, balance) == 0.16


def test_ccc_and_ocf_ebitda_growth():
    financials, balance, cashflow = _sample_statements()
    years, days = cash_conversion_cycle_years(financials, balance)
    assert years is not None and years < 1
    assert days is not None and days > 0
    # OCF CAGR 5Y and EBITDA CAGR 5Y both positive → ratio ~1
    ratio = ocf_vs_ebitda_growth(cashflow, financials, years=5)
    assert ratio is not None and ratio > 0.6


def test_score_cash_quality_keeps_passers():
    df = pd.DataFrame(
        [
            {
                "ticker": "GOOD",
                "cash_to_tax": 1.2,
                "croic": 0.25,
                "ccc_years": 0.4,
                "ocf_ebitda_growth": 0.9,
            },
            {
                "ticker": "WEAK",
                "cash_to_tax": 0.2,
                "croic": 0.05,
                "ccc_years": 1.5,
                "ocf_ebitda_growth": 0.3,
            },
        ]
    )
    scored = score_cash_quality(df)
    assert list(scored["ticker"]) == ["GOOD"]
    assert scored.iloc[0]["cq_checks_pass"] >= 3


def test_compute_metrics_bundle():
    financials, balance, cashflow = _sample_statements()
    metrics = compute_cash_quality_metrics(financials, balance, cashflow, years=5)
    assert metrics["cash_to_tax"] is not None
    assert metrics["croic"] == 0.16
    assert metrics["ccc_years"] is not None
    assert metrics["contingent_liab_equity"] is None
