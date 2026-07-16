"""NSE result-date parsing and quarter matching (offline)."""

from __future__ import annotations

import pandas as pd

from stocks.market.nse_result_dates import (
    is_financial_result_announcement,
    normalize_nse_announcement,
    nse_result_date_for_quarter,
    parse_nse_announcement_timestamp,
    parse_period_end_from_text,
)


def test_parse_nse_announcement_timestamp():
    ts = parse_nse_announcement_timestamp("17-Apr-2026 13:05:12")
    assert ts is not None
    assert ts.date().isoformat() == "2026-04-17"


def test_parse_period_end_from_text():
    text = (
        "Bajaj Consumer Care Limited has submitted to the Exchange, "
        "the financial results for the period ended March 31, 2026."
    )
    pe = parse_period_end_from_text(text)
    assert pe is not None
    assert pe.date().isoformat() == "2026-03-31"


def test_is_financial_result_announcement():
    item = {
        "desc": "Outcome of Board Meeting",
        "attchmntText": "financial results for the period ended March 31, 2026",
    }
    assert is_financial_result_announcement(item)
    assert not is_financial_result_announcement({"desc": "General Updates"})


def test_normalize_nse_announcement():
    item = {
        "an_dt": "17-Apr-2026 13:05:12",
        "desc": "Outcome of Board Meeting",
        "attchmntText": "financial results for the period ended March 31, 2026",
    }
    row = normalize_nse_announcement(item)
    assert row is not None
    assert row["result_date"] == "2026-04-17"
    assert row["period_end"] == "2026-03-31"


def test_nse_result_date_for_quarter_uses_period_end(monkeypatch):
    announcements = [
        {
            "result_date": "2026-04-17",
            "period_end": "2026-03-31",
            "desc": "Outcome of Board Meeting",
        },
        {
            "result_date": "2026-07-13",
            "period_end": "2026-06-30",
            "desc": "Outcome of Board Meeting",
        },
    ]

    def _fake_load(ticker, *, market=None, refresh=False):
        return announcements

    monkeypatch.setattr(
        "stocks.market.nse_result_dates.load_result_announcements",
        _fake_load,
    )
    rd = nse_result_date_for_quarter(
        "BAJAJCON",
        pd.Timestamp("2026-03-31"),
        market="NSE",
        as_of=pd.Timestamp("2026-07-10"),
    )
    assert rd is not None
    assert rd.date().isoformat() == "2026-04-17"
