"""Tests for 10Y sales valuation framework (Lenskart reference)."""

from __future__ import annotations

from stocks.strategies.valuation_framework.strategy import (
    LENSKART_ASSUMPTIONS,
    LENSKART_SALES_15PCT_YEARLY,
    discounted_terminal_value,
    lenskart_reference_result,
    project_sales_yearly,
    run_valuation_framework,
)


def test_lenskart_15pct_sales_trajectory():
    yearly = project_sales_yearly(8647.0, 15.0, years=10)
    assert len(yearly) == 10
    assert yearly[0] == 9944
    assert yearly[-1] == 34982
    assert yearly == list(LENSKART_SALES_15PCT_YEARLY)


def test_lenskart_15pct_valuation_and_discount():
    result = lenskart_reference_result()
    sc = result.scenario_at(15.0)
    assert sc is not None
    assert sc.year10_sales_cr == 34982
    assert sc.valuation_at_multiple_cr == 174910
    assert sc.discounted_value_cr == 43235
    assert sc.margin_of_safety_pct == round((43235 / 90979 - 1) * 100, 1)
    assert not sc.undervalued


def test_lenskart_25pct_discounted_value():
    result = lenskart_reference_result()
    sc = result.scenario_at(25.0)
    assert sc is not None
    assert sc.year10_sales_cr == 80531
    assert sc.valuation_at_multiple_cr == 402655
    assert sc.discounted_value_cr in (99530, 99531)


def test_discount_helper():
    assert discounted_terminal_value(174910, 15.0, years=10) == 43235


def test_framework_assumptions_roundtrip():
    result = run_valuation_framework(LENSKART_ASSUMPTIONS)
    assert len(result.scenarios) == 5
    assert result.best_undervalued_growth_pct == 35.0
