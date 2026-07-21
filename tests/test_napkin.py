"""LotusDew Napkin Investing scoring."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.napkin.strategy import (
    fair_pe_from_growth,
    near_term_pe,
    required_cagr_pct,
    score_napkin,
)


def test_nelco_style_required_cagr_matches_article():
    # Moneycontrol NELCO example: PE 34.5 → near ~10.4 → ~60% CAGR over 5Y.
    pe = 34.5
    near = near_term_pe(pe, near_weight=0.30)
    assert abs(near - 10.35) < 0.01
    req = required_cagr_pct(pe, near_weight=0.30, horizon_years=5)
    assert req is not None
    assert 58.0 <= req <= 62.0


def test_rate_adjusted_near_weight_lowers_required_cagr():
    # Article: near weight 15% → ~35% required (they used ~4.5 near PE).
    req = required_cagr_pct(34.5, near_weight=0.15, horizon_years=5)
    assert req is not None
    assert 35.0 <= req <= 42.0


def test_fair_pe_inverts_required_cagr():
    fair = fair_pe_from_growth(60.0, near_weight=0.30, horizon_years=5)
    assert fair is not None
    # (1.6^5) / 0.3 ≈ 34.9
    assert 33.0 <= fair <= 37.0


def test_score_napkin_ranks_coverage():
    df = pd.DataFrame(
        [
            {
                "ticker": "CHEAP",
                "forward_pe": 15.0,
                "eps_yoy": 40.0,
            },
            {
                "ticker": "RICH",
                "forward_pe": 40.0,
                "eps_yoy": 10.0,
            },
            {
                "ticker": "NOPE",
                "forward_pe": None,
                "pe_ratio": None,
                "eps_yoy": 50.0,
            },
        ]
    )
    scored = score_napkin(df)
    assert list(scored["ticker"]) == ["CHEAP", "RICH"]
    assert scored.iloc[0]["pead_score"] > scored.iloc[1]["pead_score"]
    assert scored.iloc[0]["napkin_gap"] > scored.iloc[1]["napkin_gap"]
