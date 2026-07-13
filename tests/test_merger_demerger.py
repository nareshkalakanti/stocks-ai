"""Tests for merger/demerger corporate action parsing."""

from __future__ import annotations

from stocks.market.merger_demerger import (
    is_merger_demerger_subject,
    normalize_action_type,
    parse_nse_action_date,
    _normalize_row,
)


def test_parse_nse_action_date():
    assert parse_nse_action_date("06-Jan-2022").isoformat() == "2022-01-06"
    assert parse_nse_action_date("-") is None


def test_normalize_action_type():
    assert normalize_action_type("Demerger") == "Demerger"
    assert normalize_action_type(" Scheme Of Demerger") == "Demerger"
    assert normalize_action_type("Merger") == "Merger"
    assert normalize_action_type(" Merger/Demerger") == "Merger/Demerger"


def test_is_merger_demerger_subject():
    assert is_merger_demerger_subject("Demerger") is True
    assert is_merger_demerger_subject("Final Dividend - Rs 2") is False


def test_normalize_row_filters_and_maps():
    row = {
        "symbol": "GMRAIRPORT",
        "comp": "GMR AIRPORTS LIMITED",
        "exDate": "11-Jan-2022",
        "recDate": "12-Jan-2022",
        "subject": "Demerger",
        "isin": "INE776C01039",
        "series": "EQ",
    }
    out = _normalize_row(row)
    assert out is not None
    assert out["ticker"] == "GMRAIRPORT"
    assert out["action_type"] == "Demerger"
    assert out["ex_date"] == "2022-01-11"
    assert out["record_date"] == "2022-01-12"
