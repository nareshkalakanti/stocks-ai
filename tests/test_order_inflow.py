"""Tests for order inflow parsing and aggregation."""

from __future__ import annotations

import pandas as pd

from stocks.market.order_inflow import (
    aggregate_company_orders,
    fy_label,
    inr_to_cr,
    normalize_order_announcement,
    parse_duration_months,
    parse_inr_from_text,
)


def test_inr_crore_and_lakh():
    assert parse_inr_from_text("order worth Rs. 271.80 crore") == 2_718_000_000
    assert parse_inr_from_text("Rs 50 lakh") == 5_000_000
    assert inr_to_cr(2_718_000_000) == 271.8
    assert inr_to_cr(5_000_000) == 0.5


def test_duration_and_annual():
    text = "contract over a period of 18 months valued at Rs 271.8 crore"
    assert parse_duration_months(text) == 18
    row = normalize_order_announcement(
        {
            "desc": "Bagging/Receiving of orders/contracts",
            "attchmntText": text,
            "an_dt": "12-Nov-2025 10:00:00",
        }
    )
    assert row is not None
    assert row["value_inr"] == 2_718_000_000
    assert row["duration_months"] == 18
    assert row["annual_value_inr"] == int(round(2_718_000_000 * 12 / 18))


def test_fy_label():
    assert fy_label("2025-11-12") == "FY2026"
    assert fy_label("2025-02-01") == "FY2025"


def test_aggregate_growth():
    orders = [
        {"value_inr": 100_000_000, "fy": "FY2026", "announced_at": "2025-06-01"},
        {"value_inr": 50_000_000, "fy": "FY2025", "announced_at": "2024-06-01"},
    ]
    summary = aggregate_company_orders(
        "TEST",
        "Test Co",
        "NSE",
        orders,
        ttm_revenue_inr=500_000_000,
        current_fy="FY2026",
    )
    assert summary is not None
    assert summary["order_count"] == 2
    assert summary["total_cr"] == 15.0
    assert summary["growth_pct"] == 100.0
