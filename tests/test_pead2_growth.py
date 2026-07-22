"""PEAD growth caps and quarter-panel YoY helpers."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import EARNINGS_MAX_EPS_YOY_PCT
from stocks.strategies.earnings.quality import cap_growth_qoq_pct
from stocks.strategies.pead2.service import _pead2_row_for_lag
from stocks.strategies.pead2.quarters import append_valuation_rows, sanitize_quarter_panel, yoy_pair_from_panel
from stocks.strategies.pead2.strategy import (
    PEAD_HIGH_SCORE_MIN,
    compute_forward_pe,
    compute_growth_metrics,
    compute_trailing_pe,
    eps_yoy_from_quarters,
    score_pead2_candidates,
    score_pead2_ff,
    trim_reported_quarters,
    result_quarter_end,
)


def test_compute_growth_metrics_uses_calendar_yoy():
    idx = pd.to_datetime(
        ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]
    )
    revenue = pd.Series([100, 110, 120, 130, 150], index=idx)
    net_profit = revenue * 0.1
    ebidt = revenue * 0.2
    eps = net_profit / 10
    growth = compute_growth_metrics(revenue, net_profit, ebidt, eps)
    assert growth["sales_yoy"] == 50.0


def test_trim_reported_quarters_drops_future_columns():
    idx = pd.to_datetime(
        ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]
    )
    s = pd.Series([1, 2, 3, 4, 5], index=idx)
    out = trim_reported_quarters(s, as_of=pd.Timestamp("2025-07-10"))
    assert list(out.index) == list(idx[:2])
    assert out.iloc[-1] == 2


def test_result_quarter_end_skips_phantom_leading_column():
    import yfinance as yf
    from stocks.strategies.pead2.strategy import result_quarter_end

    idx = pd.to_datetime(
        ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]
    )
    s = pd.Series([1, 2, 3, 4, 5], index=idx)
    yt = yf.Ticker("TBZ.NS")
    q_end = result_quarter_end(s, yt, as_of=pd.Timestamp("2026-07-10"))
    assert pd.Timestamp(q_end).date() == pd.Timestamp("2025-03-31").date()


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


def test_sanitize_quarter_panel_strips_pe_rows():
    panel = {
        "labels": ["Mar 2025", "Jun 2025"],
        "rows": [
            {"label": "Sales", "values": [100, 110]},
            {"label": "Current PE", "values": [12, 14]},
            {"label": "Forward PE", "values": [3, 4]},
            {"label": "Forward EPS", "values": [1.0, 1.1]},
        ],
    }
    out = sanitize_quarter_panel(panel)
    labels = {row["label"] for row in out["rows"]}
    assert labels == {"Sales"}
    assert out is not panel


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


def test_build_quarter_panel_includes_other_income_when_material():
    idx = pd.to_datetime(
        ["2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    )
    revenue = pd.Series([0, 0, 0, 0, 0], index=idx)
    ebit = pd.Series([-4_000_000, -4_000_000, -4_000_000, -4_000_000, -4_000_000], index=idx)
    net_profit = pd.Series([-2_000_000, -2_000_000, -2_000_000, 50_000_000, -2_000_000], index=idx)
    eps = pd.Series([-0.2, -0.2, -0.2, 7.1, -0.2], index=idx)
    other_income = pd.Series([1_000_000, 1_000_000, 1_000_000, 74_000_000, 1_000_000], index=idx)

    from stocks.strategies.pead2.quarters import build_quarter_panel

    panel = build_quarter_panel(revenue, ebit, net_profit, eps, other_income=other_income)
    labels = [row["label"] for row in panel["rows"]]
    assert labels == ["Sales", "Operating Profit", "Other Income", "Net Profit", "EPS in Rs"]
    oi = next(row for row in panel["rows"] if row["label"] == "Other Income")
    assert oi["values"][-2] == 7


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


def test_pead2_row_for_lag_builds_without_name_error(monkeypatch):
    import yfinance as yf

    monkeypatch.setattr(
        "stocks.market.nse_result_dates.nse_announced_dates",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "stocks.market.nse_result_dates.nse_result_date_for_quarter",
        lambda *args, **kwargs: None,
    )

    idx = pd.to_datetime(
        ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]
    )
    revenue = pd.Series([100, 110, 120, 130, 140], index=idx)
    ebidt = revenue * 0.2
    net_profit = revenue * 0.1
    eps = net_profit / 10
    hist = pd.DataFrame(
        {"Close": [100.0] * 200},
        index=pd.date_range("2024-01-01", periods=200),
    )
    yt = yf.Ticker("TBZ.NS")
    row = _pead2_row_for_lag(
        ticker="TBZ",
        market="NSE",
        market_cap_cr=1.0,
        price_val=100.0,
        revenue=revenue,
        ebidt=ebidt,
        net_profit=net_profit,
        eps=eps,
        cfo=None,
        other_income=None,
        yt=yt,
        info={},
        hist=hist,
        lag=0,
    )
    assert row is not None
    assert row.get("quarters", {}).get("labels")


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
