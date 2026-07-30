"""Positive Surprise Quant scoring + NSE XBRL helpers."""

from __future__ import annotations

import pandas as pd

from stocks.market.nse_financials_xbrl import parse_indas_quarter_xbrl
from stocks.strategies.positive_surprise.strategy import (
    compute_peg,
    score_positive_surprise,
    seasonal_surprise_growth,
)


def test_seasonal_surprise_prefers_eps_yoy():
    row = pd.Series({"eps_yoy": 40.0, "sales_yoy": 10.0, "np_yoy": 20.0})
    assert seasonal_surprise_growth(row) == 40.0


def test_compute_peg_floors_growth():
    peg = compute_peg(20.0, 2.0, growth_floor=5.0)
    assert peg == 4.0  # 20 / max(2, 5)


def test_score_positive_surprise_keeps_positive_only():
    df = pd.DataFrame(
        [
            {
                "ticker": "GOOD",
                "eps_yoy": 50.0,
                "forward_pe": 25.0,
                "sales_yoy": 30.0,
            },
            {
                "ticker": "BAD",
                "eps_yoy": -10.0,
                "forward_pe": 10.0,
                "sales_yoy": -5.0,
            },
        ]
    )
    scored = score_positive_surprise(df)
    assert list(scored["ticker"]) == ["GOOD"]
    assert scored.iloc[0]["peg"] is not None
    assert scored.iloc[0]["pead_score"] > 0


def test_parse_indas_quarter_xbrl_oned():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <xbrl xmlns="http://www.xbrl.org/2003/instance">
      <context id="OneD">
        <entity><identifier scheme="x">X</identifier></entity>
        <period><startDate>2026-04-01</startDate><endDate>2026-06-30</endDate></period>
      </context>
      <RevenueFromOperations contextRef="OneD" unitRef="INR" decimals="INF">100</RevenueFromOperations>
      <ProfitLossForPeriod contextRef="OneD" unitRef="INR" decimals="INF">40</ProfitLossForPeriod>
      <BasicEarningsLossPerShareFromContinuingOperations contextRef="OneD" unitRef="Pure" decimals="INF">2.5</BasicEarningsLossPerShareFromContinuingOperations>
    </xbrl>
    """
    parsed = parse_indas_quarter_xbrl(xml)
    assert parsed is not None
    assert parsed["rev_actual"] == 100.0
    assert parsed["np_actual"] == 40.0
    assert parsed["eps_actual"] == 2.5
    assert parsed["period_end"] == "2026-06-30"
