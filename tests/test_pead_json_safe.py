"""JSON safety for PEAD dashboard and session state."""

from __future__ import annotations

import json

import pandas as pd

from stocks.core.json_utils import json_safe_obj, json_safe_scalar
from stocks.strategies.pead2.html import _rows_for_json, build_pead2_dashboard_html


def test_json_safe_scalar_handles_pd_na():
    assert json_safe_scalar(pd.NA) is None
    assert json_safe_scalar(float("nan")) is None


def test_rows_for_json_serializes_tq_na():
    df = pd.DataFrame(
        [
            {
                "ticker": "TEST",
                "name": "Test Co",
                "market": "NSE",
                "pead_score": 42.0,
                "returns_pct": 10.0,
                "tq_score": pd.NA,
                "has_tq": False,
                "has_bb": False,
                "calculation_date": "2026-07-10T00:00:00+00:00",
            }
        ]
    )
    payload = _rows_for_json(df)
    json.dumps(payload)


def test_rows_for_json_serializes_quarter_panel_na_values():
    df = pd.DataFrame(
        [
            {
                "ticker": "TEST",
                "name": "Test Co",
                "market": "NSE",
                "pead_score": 42.0,
                "returns_pct": 10.0,
                "forward_pe": pd.NA,
                "price": 100.0,
                "valuation_pass": pd.NA,
                "has_tq": False,
                "has_bb": False,
                "calculation_date": "2026-07-10T00:00:00+00:00",
                "quarters": {
                    "labels": ["Mar 2026"],
                    "rows": [
                        {
                            "label": "Sales",
                            "values": [pd.NA, 12.5],
                            "good_up": True,
                            "decimals": 1,
                        }
                    ],
                },
                "snapshot": {
                    "price": 100.0,
                    "forward_pe": pd.NA,
                    "pe_ratio": pd.NA,
                    "market_cap_cr": pd.NA,
                },
            }
        ]
    )
    payload = _rows_for_json(df)
    assert payload[0]["forward_pe"] is None
    assert payload[0]["snapshot"]["forward_pe"] is None
    assert payload[0]["quarters"]["rows"][0]["values"][0] is None
    json.dumps(payload)


def test_build_pead2_dashboard_html_with_na_fields():
    df = pd.DataFrame(
        [
            {
                "ticker": "TEST",
                "name": "Test Co",
                "market": "NSE",
                "pead_score": 42.0,
                "returns_pct": 10.0,
                "daily_ret_pct": pd.NA,
                "forward_pe": pd.NA,
                "price": 50.0,
                "result_date": "2026-05-12",
                "has_tq": False,
                "has_bb": False,
                "calculation_date": "2026-07-10T00:00:00+00:00",
            }
        ]
    )
    html_out = build_pead2_dashboard_html(df, standalone=False)
    assert "DATA_CURRENT" in html_out
