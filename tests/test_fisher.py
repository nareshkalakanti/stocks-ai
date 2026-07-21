"""Philip Fisher multibagger scorecard."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.fisher.strategy import score_fisher


def test_score_fisher_ranks_quality_compounder():
    df = pd.DataFrame(
        [
            {
                "ticker": "GOOD",
                "sales_yoy": 25.0,
                "sales_qoq": 8.0,
                "np_yoy": 30.0,
                "eps_yoy": 28.0,
                "ebidt_yoy": 22.0,
                "cf_profit": 1.1,
                "forward_pe": 22.0,
                "market_cap_cr": 2500.0,
                "sales_bust": False,
            },
            {
                "ticker": "WEAK",
                "sales_yoy": 3.0,
                "sales_qoq": -2.0,
                "np_yoy": -5.0,
                "eps_yoy": -8.0,
                "cf_profit": 0.3,
                "forward_pe": 80.0,
                "market_cap_cr": 800.0,
                "sales_bust": True,
            },
        ]
    )
    scored = score_fisher(df)
    assert list(scored["ticker"]) == ["GOOD"]
    assert scored.iloc[0]["fisher_score"] >= 55
    assert scored.iloc[0]["fisher_checks_pass"] >= 7


def test_score_fisher_drops_insufficient_checks():
    df = pd.DataFrame(
        [
            {
                "ticker": "WEAK",
                "sales_yoy": 4.0,
                "sales_qoq": -1.0,
                "np_yoy": -2.0,
                "eps_yoy": -3.0,
                "cf_profit": 0.2,
                "forward_pe": 90.0,
                "market_cap_cr": 25000.0,
                "sales_bust": True,
            }
        ]
    )
    scored = score_fisher(df)
    assert scored.empty
