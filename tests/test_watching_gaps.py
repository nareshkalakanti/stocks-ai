"""Watching gap CSV helpers."""

from __future__ import annotations

import pandas as pd

from stocks.shared.early_edge import watching_gap_counts, watching_gap_rows


def test_watching_gap_rows_and_counts():
    view = pd.DataFrame(
        [
            {
                "ticker": "A",
                "name": "A Co",
                "market": "NSE SME",
                "sector": "",
                "sub_sector": "",
                "industry": "",
                "website": "",
                "price": 1.0,
                "market_cap_cr": None,
            },
            {
                "ticker": "B",
                "name": "B Co",
                "market": "NSE SME",
                "sector": "IT",
                "sub_sector": "Software",
                "industry": "Software",
                "website": "https://b.com",
                "price": 2.0,
                "market_cap_cr": 10.0,
            },
        ]
    )
    gaps = watching_gap_rows(view)
    assert list(gaps["ticker"]) == ["A"]
    assert gaps.iloc[0]["missing"] == "sector,sub_sector,mcap,web"
    counts = watching_gap_counts(view)
    assert counts["any_rows"] == 1
    assert counts["sector"] == 1
    assert counts["mcap"] == 1
    assert counts["web"] == 1
    assert counts["total"] == 2
