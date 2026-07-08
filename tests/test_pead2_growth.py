"""PEAD growth caps and quarter-panel YoY helpers."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import EARNINGS_MAX_EPS_YOY_PCT
from stocks.strategies.earnings.quality import cap_growth_qoq_pct
from stocks.strategies.pead2.quarters import append_valuation_rows, yoy_pair_from_panel
from stocks.strategies.pead2.strategy import (
    PEAD_HIGH_SCORE_MIN,
    compute_forward_pe,
    compute_trailing_pe,
    eps_yoy_from_quarters,
    score_pead2_candidates,
)


def test_append_valuation_rows_option_a_b():
    panel = {
        "labels": ["Mar 2024", "Jun 2024", "Sep 2024", "Dec 2024"],
        "rows": [
            {
                "label": "EPS in Rs",
                "values": [0.30, 0.36, 4.47, 13.38],
                "good_up": True,
                "decimals": 2,
            }
        ],
    }
    out = append_valuation_rows(panel, 475.0)
    assert out is not None
    by_label = {row["label"]: row["values"] for row in out["rows"]}
    assert by_label["Forward EPS"][-1] == 53.52
    assert by_label["Forward PE"][-1] == 8.9
    assert by_label["Current PE"][-1] == 25.7


def test_trailing_and_forward_pe_option_a_b():
    eps = pd.Series(
        [0.30, 0.36, 4.47, 13.38],
        index=pd.to_datetime(["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"]),
    )
    assert compute_trailing_pe(475.0, eps) == 25.7
    assert compute_forward_pe(475.0, eps) == 8.9


def test_cap_growth_qoq_pct_symmetric():
    assert cap_growth_qoq_pct(13147.93) == EARNINGS_MAX_EPS_YOY_PCT
    assert cap_growth_qoq_pct(-500.0) == -EARNINGS_MAX_EPS_YOY_PCT
    assert cap_growth_qoq_pct(42.5) == 42.5


def test_yoy_pair_oldest_first_panel():
    values = [5.1, 6.2, 7.08, 5.56, 10.60]
    labels = ["Mar 2024", "Dec 2024", "Mar 2025", "Dec 2025", "Mar 2026"]
    latest, prior = yoy_pair_from_panel(values, labels)
    assert latest == 10.60
    assert prior == 5.1


def test_yoy_pair_newest_first_panel():
    values = [10.60, 5.56, 7.08, 6.2, 5.1]
    labels = ["Mar 2026", "Dec 2025", "Mar 2025", "Dec 2024", "Mar 2024"]
    latest, prior = yoy_pair_from_panel(values, labels)
    assert latest == 10.60
    assert prior == 5.1


def test_eps_yoy_from_quarters_matches_headline():
    quarters = {
        "labels": ["Mar 2024", "Dec 2024", "Mar 2025", "Dec 2025", "Mar 2026"],
        "rows": [
            {
                "label": "EPS in Rs",
                "values": [5.1, 6.2, 7.08, 5.56, 10.60],
            }
        ],
    }
    yoy = eps_yoy_from_quarters(quarters)
    assert yoy is not None
    assert abs(yoy - 107.84) < 0.1


def test_score_pead2_candidates_caps_extreme_np_qoq():
    df = pd.DataFrame(
        [
            {"ticker": "LOW", "np_qoq": 10.0, "sales_yoy": 10.0, "forward_pe": 15.0},
            {"ticker": "SPIKE", "np_qoq": 13147.0, "sales_yoy": 30.0, "forward_pe": 6.0},
        ]
    )
    scored = score_pead2_candidates(df)
    spike = scored.loc[scored["ticker"] == "SPIKE", "pead_score"].iloc[0]
    low = scored.loc[scored["ticker"] == "LOW", "pead_score"].iloc[0]
    assert spike <= 100.0
    assert spike < 100.0 or low <= spike


def test_demo_scan_result_uses_our_scores():
    from stocks.core.config import DB_PATH
    from stocks.strategies.pead2.demo_data import DEMO_TICKERS, pead2_demo_scan_result

    if not DB_PATH.exists():
        return
    demo = pead2_demo_scan_result()
    df = demo["candidates"]
    if df.empty:
        return
    assert set(df["ticker"].str.upper()) <= set(DEMO_TICKERS)
    assert (df["valuation_pass"] == (df["pead_score"] > PEAD_HIGH_SCORE_MIN)).all()
    assert df["pead_score"].notna().all()
