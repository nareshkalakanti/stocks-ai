"""DCF math — LearnApp spreadsheet + reverse implied growth."""

from __future__ import annotations

from stocks.strategies.dcf.strategy import (
    gordon_terminal_value,
    implied_growth_rate,
    present_value_cash_flows,
    project_cash_flows,
    run_dcf,
    score_dcf,
)
import pandas as pd


def test_learnapp_flat_fcf_8_5pct():
    """₹5L flat for 10Y @ 8.5% → PV sum ≈ 32,80,674 (video)."""
    flows = project_cash_flows(500_000, years=10, growth=0.0)
    assert len(flows) == 10
    assert flows[0] == 500_000
    total, schedule = present_value_cash_flows(flows, discount_rate=0.085)
    assert abs(total - 3_280_674) < 5
    assert abs(schedule[0]["discount_factor"] - 0.9217) < 0.002
    assert abs(schedule[0]["present_value"] - 460_829) < 5
    assert abs(schedule[-1]["present_value"] - 221_143) < 5


def test_learnapp_with_zero_growth_terminal():
    """TV = CF/r, discounted 10Y — matches perpetual-machine slide totals."""
    out = run_dcf(
        500_000,
        discount_rate=0.085,
        forecast_years=10,
        growth=0.0,
        terminal_growth=0.0,
        net_debt=0.0,
        shares=1.0,
        market_price=5_882_353,
    )
    assert out is not None
    assert abs(out["pv_forecast"] - 3_280_674) < 5
    assert abs(out["terminal_value"] - 5_882_353) < 5
    assert abs(out["pv_terminal"] - 2_601_679) < 10
    assert abs(out["equity_value"] - 5_882_353) < 15
    assert out["verdict"] == "Fair"


def test_higher_discount_lowers_value():
    low_r = run_dcf(
        500_000,
        discount_rate=0.085,
        forecast_years=10,
        growth=0.0,
        terminal_growth=0.0,
        shares=1.0,
    )
    high_r = run_dcf(
        500_000,
        discount_rate=0.15,
        forecast_years=10,
        growth=0.0,
        terminal_growth=0.0,
        shares=1.0,
    )
    assert low_r and high_r
    assert high_r["pv_forecast"] < low_r["pv_forecast"]
    assert abs(high_r["pv_forecast"] - 2_509_384) < 50


def test_gordon_requires_r_gt_g():
    assert gordon_terminal_value(100, discount_rate=0.08, terminal_growth=0.08) is None
    tv = gordon_terminal_value(100, discount_rate=0.10, terminal_growth=0.03)
    assert tv is not None
    assert abs(tv - 100 * 1.03 / 0.07) < 1e-6


def test_implied_growth_roundtrip():
    base = 1_000_000.0
    shares = 100_000.0
    fwd = run_dcf(
        base,
        discount_rate=0.10,
        forecast_years=10,
        growth=0.08,
        terminal_growth=0.02,
        net_debt=0.0,
        shares=shares,
    )
    assert fwd and fwd["fair_price"]
    implied = implied_growth_rate(
        base,
        fwd["fair_price"],
        discount_rate=0.10,
        forecast_years=10,
        terminal_growth=0.02,
        net_debt=0.0,
        shares=shares,
    )
    assert implied is not None
    assert abs(implied - 0.08) < 0.005


def test_score_ranks_by_upside():
    df = pd.DataFrame(
        [
            {"ticker": "A", "fair_price": 100, "upside_pct": 10},
            {"ticker": "B", "fair_price": 80, "upside_pct": 40},
            {"ticker": "C", "fair_price": None, "upside_pct": None},
        ]
    )
    scored = score_dcf(df)
    assert list(scored["ticker"]) == ["B", "A"]
    assert scored.iloc[0]["rank"] == 1
