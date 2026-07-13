"""Tests for 100X Formula scoring."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.formula_100x.strategy import compute_100x_cfo_checks, evaluate_100x_formula


def _make_frames(
    cfo_vals: list[float],
    ebit_vals: list[float],
    ebt_vals: list[float],
    *,
    assets: float = 1000.0,
    liabilities: float = 200.0,
):
    years = pd.date_range("2021-12-31", periods=len(cfo_vals), freq="YE")
    cashflow = pd.DataFrame(
        [cfo_vals],
        index=["Operating Cash Flow"],
        columns=years,
    )
    financials = pd.DataFrame(
        [ebit_vals, ebt_vals],
        index=["EBIT", "Income Before Tax"],
        columns=years,
    )
    balance_sheet = pd.DataFrame(
        [[assets], [liabilities]],
        index=["Total Assets", "Current Liabilities"],
        columns=[years[-1]],
    )
    return cashflow, financials, balance_sheet


def test_compute_100x_cfo_checks():
    cashflow, financials, _ = _make_frames(
        [80e7, 90e7, 100e7, 110e7],
        [50e7, 55e7, 60e7, 65e7],
        [40e7, 44e7, 48e7, 52e7],
    )
    out = compute_100x_cfo_checks(cashflow=cashflow, financials=financials)
    assert out is not None
    assert out["pass_rising_cfo"] is True
    assert out["pass_cfo_ebit"] is True
    assert out["cfo_ebit_pct"] > 60


def test_evaluate_100x_all_pass():
    cashflow, financials, balance_sheet = _make_frames(
        [80e7, 90e7, 100e7, 110e7],
        [50e7, 55e7, 60e7, 65e7],
        [40e7, 44e7, 48e7, 52e7],
    )
    out = evaluate_100x_formula(
        cashflow=cashflow,
        financials=financials,
        balance_sheet=balance_sheet,
        info={"marketCap": 500e7},
        market_cap_cr=50.0,
    )
    assert out is not None
    assert out["criteria_score"] == 4
    assert out["pass_rising_cfo"] is True
    assert out["cfo_ebit_pct"] > 60


def test_evaluate_100x_fails_rising_cfo():
    cashflow, financials, balance_sheet = _make_frames(
        [110e7, 100e7, 90e7, 80e7],
        [50e7, 55e7, 60e7, 65e7],
        [40e7, 44e7, 48e7, 52e7],
    )
    out = evaluate_100x_formula(
        cashflow=cashflow,
        financials=financials,
        balance_sheet=balance_sheet,
        info={"marketCap": 500e7},
        market_cap_cr=50.0,
    )
    assert out is not None
    assert out["pass_rising_cfo"] is False
