"""Tests for merger/demerger supplements."""

from __future__ import annotations

import pandas as pd

from stocks.market.merger_demerger_supplements import apply_merger_demerger_supplements


def test_supplements_add_kamopaints_and_epackpeb():
    base = pd.DataFrame(
        [
            {
                "ticker": "KAMDHENU",
                "company": "Kamdhenu Limited",
                "action_type": "Demerger",
                "ex_date": "2022-09-06",
                "record_date": "2022-09-06",
                "subject": "Demerger",
                "source": "NSE",
            }
        ]
    )
    out = apply_merger_demerger_supplements(base)
    tickers = set(out["ticker"].astype(str))
    assert "KAMDHENU" in tickers
    assert "KAMOPAINTS" in tickers
    assert "EPACKPEB" in tickers
    kam = out[out["ticker"] == "KAMDHENU"].iloc[0]
    assert kam["ratio"] == "1:1"
    assert kam["demerged_ticker"] == "KAMOPAINTS"
    assert kam["counterparty_company"] == "Kamdhenu Ventures Limited"
    assert kam["counterparty_ticker"] == "KAMOPAINTS"


def test_supplements_work_on_empty_base():
    out = apply_merger_demerger_supplements(pd.DataFrame())
    assert len(out) >= 3
    assert "EPACKPEB" in set(out["ticker"].astype(str))


def test_spinoff_row_shows_parent_as_counterparty():
    out = apply_merger_demerger_supplements(pd.DataFrame())
    paints = out[out["ticker"] == "KAMOPAINTS"].iloc[0]
    assert paints["counterparty_company"] == "Kamdhenu Limited"
    assert paints["counterparty_ticker"] == "KAMDHENU"
    assert paints["row_role"] == "Spin-off"


def test_parent_and_spinoff_are_adjacent():
    out = apply_merger_demerger_supplements(pd.DataFrame())
    kam_idx = out.index[out["ticker"] == "KAMDHENU"].tolist()
    paints_idx = out.index[out["ticker"] == "KAMOPAINTS"].tolist()
    assert kam_idx and paints_idx
    assert abs(kam_idx[0] - paints_idx[0]) == 1
    assert out.loc[kam_idx[0], "row_role"] == "Parent"
