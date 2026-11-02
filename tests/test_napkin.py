"""Lotusdew Napkin Framework — rate-adjusted required CAGR sanity checks."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.napkin.napkin_framework import (
    adj_tv_weight,
    near_term_weight,
    required_cagr,
    napkin_score,
    verdict,
    revenue_cagr_from_annual,
)
from stocks.strategies.napkin.strategy import (
    fair_pe_from_growth,
    near_term_pe,
    required_cagr_pct,
    score_napkin,
)


def test_nelco_rate_framework_sanity():
    """
    Blog NELCO example (PE 34.5):
    - current_rate 8% → required CAGR ~58–60%
    - current_rate 6% → required CAGR ~35% (exact math ≈ 38.9%)
    """
    pe = 34.5
    # At 8%: rate_shift=0 → near_weight=0.30 → ~59.6%
    req_8 = required_cagr(pe, base_rate=8.0, current_rate=8.0, base_tv_weight=0.70)
    assert 0.58 <= req_8 <= 0.60

    # At 6%: near_weight=0.15 → ~38.9% (article rounds to ~35%)
    assert abs(near_term_weight(8.0, 6.0, 0.70) - 0.15) < 1e-9
    assert abs(adj_tv_weight(8.0, 6.0, 0.70) - 0.85) < 1e-9
    req_6 = required_cagr(pe, base_rate=8.0, current_rate=6.0, base_tv_weight=0.70)
    assert 0.35 <= req_6 <= 0.40


def test_verdict_bands():
    assert verdict(20.0, 0.06, 0.20) == "Napkin Buy"
    assert verdict(20.0, 0.0, 0.20) == "Fair Value"
    assert verdict(20.0, -0.06, 0.10) == "Overvalued"
    assert verdict(-1.0, 0.1, 0.2) == "Unprofitable"
    assert verdict(20.0, 0.1, float("nan")) == "Insufficient Data"


def test_revenue_cagr_three_year():
    # 100 → 133.1 over 3 years ≈ 10% CAGR
    cagr = revenue_cagr_from_annual([133.1, 121.0, 110.0, 100.0])
    assert abs(cagr - 0.10) < 0.001


def test_napkin_score():
    assert abs(napkin_score(0.40, 0.30) - 0.10) < 1e-9


# --- legacy PEAD-based napkin helpers (still used by PEAD dashboards) ---


def test_nelco_style_required_cagr_matches_article():
    pe = 34.5
    near = near_term_pe(pe, near_weight=0.30)
    assert abs(near - 10.35) < 0.01
    req = required_cagr_pct(pe, near_weight=0.30, horizon_years=5)
    assert req is not None
    assert 58.0 <= req <= 62.0


def test_fair_pe_inverts_required_cagr():
    fair = fair_pe_from_growth(60.0, near_weight=0.30, horizon_years=5)
    assert fair is not None
    assert 33.0 <= fair <= 37.0


def test_score_napkin_ranks_coverage():
    df = pd.DataFrame(
        [
            {"ticker": "CHEAP", "forward_pe": 15.0, "eps_yoy": 40.0},
            {"ticker": "RICH", "forward_pe": 40.0, "eps_yoy": 10.0},
            {"ticker": "NOPE", "forward_pe": None, "pe_ratio": None, "eps_yoy": 50.0},
        ]
    )
    scored = score_napkin(df)
    assert list(scored["ticker"]) == ["CHEAP", "RICH"]
    assert scored.iloc[0]["pead_score"] > scored.iloc[1]["pead_score"]
