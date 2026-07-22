"""Alpha Hide (SARVADA-style) ingredient gates and ranking."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.alpha_hide.strategy import (
    ingredient_checks,
    recognition_phase,
    score_alpha_hide,
    ten_bagger_math_caption,
)


def test_recognition_phases():
    assert recognition_phase(120.0) == "I"
    assert recognition_phase(500.0) == "II"
    assert recognition_phase(40.0) is None
    assert recognition_phase(2000.0) == "III"


def test_ingredient_checks_valuation_and_growth():
    row = {
        "pe_ratio": 8.0,
        "ev_ebitda": 12.0,
        "drawdown_pct": 30.0,
        "sales_cagr": 25.0,
        "profit_positive": True,
        "sales_accel": True,
        "demerger_flag": False,
        "promoter_pct_delta": 0.5,
        "institutional_pct_delta": 0.0,
    }
    passed, failed, flags = ingredient_checks(row)
    assert flags["ing_valuation"]
    assert flags["ing_growth"]
    assert flags["ing_contrarian"]
    assert flags["ing_inflection"]
    assert flags["ing_promoter"]
    assert len(passed) == 5


def test_score_requires_valuation_and_growth():
    df = pd.DataFrame(
        [
            {
                "ticker": "GOOD",
                "phase": "I",
                "market_cap_cr": 150.0,
                "pe_ratio": 7.0,
                "ev_ebitda": 5.0,
                "price_to_sales": 0.8,
                "drawdown_pct": 28.0,
                "sales_cagr": 22.0,
                "profit_positive": True,
                "sales_accel": False,
                "demerger_flag": True,
                "promoter_pct_delta": None,
                "institutional_pct_delta": 0.4,
            },
            {
                "ticker": "CHEAP_ONLY",
                "phase": "I",
                "market_cap_cr": 180.0,
                "pe_ratio": 6.0,
                "ev_ebitda": 4.0,
                "price_to_sales": 0.5,
                "drawdown_pct": 10.0,
                "sales_cagr": 5.0,
                "profit_positive": True,
                "sales_accel": False,
                "demerger_flag": False,
                "promoter_pct_delta": None,
                "institutional_pct_delta": None,
            },
        ]
    )
    scored = score_alpha_hide(df)
    assert list(scored["ticker"]) == ["GOOD"]
    assert scored.iloc[0]["rank"] == 1


def test_ten_bagger_math_in_caption():
    text = ten_bagger_math_caption()
    assert "×" in text
