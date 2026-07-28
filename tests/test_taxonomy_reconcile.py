"""Local taxonomy conflict reconciliation (no Screener)."""

from __future__ import annotations

import pandas as pd

from stocks.listings.sector_display import (
    reconcile_taxonomy_conflicts,
    apply_display_sector_mapping,
)


def test_reconcile_drops_finance_industry_for_industrial_name():
    df = pd.DataFrame(
        [
            {
                "ticker": "KIRLOSIND",
                "name": "Kirloskar Industries Limited",
                "sector": "Banking & Finance",
                "industry": "Investment Banking & Brokerage",
                "sub_sector": "Investment Banking & Brokerage",
                "source_sector": "Non-energy minerals",
            },
            {
                "ticker": "ABSLAMC",
                "name": "Aditya Birla Sun Life AMC Limited",
                "sector": "Banking & Finance",
                "industry": "Asset Management",
                "sub_sector": "Asset Management",
                "source_sector": "Technology services",
            },
        ]
    )
    out = reconcile_taxonomy_conflicts(df)
    kir = out.loc[out["ticker"] == "KIRLOSIND"].iloc[0]
    amc = out.loc[out["ticker"] == "ABSLAMC"].iloc[0]
    assert "Investment Banking" not in str(kir["industry"])
    assert amc["industry"] == "Asset Management"


def test_apply_display_maps_kirlosind_away_from_banking():
    df = pd.DataFrame(
        [
            {
                "ticker": "KIRLOSIND",
                "name": "Kirloskar Industries Limited",
                "sector": "Banking & Finance",
                "industry": "Investment Banking & Brokerage",
                "sub_sector": "Investment Banking & Brokerage",
                "source_sector": "Non-energy minerals",
            }
        ]
    )
    out = apply_display_sector_mapping(df)
    assert out.iloc[0]["sector"] != "Banking & Finance"
