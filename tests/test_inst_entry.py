"""Inst Entry quant gates + institutional trigger ranking."""

from __future__ import annotations

import pandas as pd

from stocks.core.database import init_db, save_shareholding_qtr
from stocks.market.shareholding import institutional_entry_signal
from stocks.strategies.inst_entry.strategy import (
    passes_quant_gates,
    score_inst_entry,
)


def test_passes_quant_gates():
    good = {
        "market_cap_cr": 55.0,
        "price_to_sales": 0.9,
        "debt_to_equity": 0.05,
        "sales_cagr": 15.0,
        "profit_positive": True,
        "avg_volume": 12000,
        "years_listed": 5.0,
    }
    ok, passed, failed = passes_quant_gates(good)
    assert ok
    assert not failed

    bad = dict(good)
    bad["price_to_sales"] = 2.5
    ok2, _, failed2 = passes_quant_gates(bad)
    assert not ok2
    assert "P/S" in failed2

    # Yahoo often omits listing date / D/E for NSE — do not fail those.
    sparse = dict(good)
    sparse["years_listed"] = None
    sparse["debt_to_equity"] = None
    ok3, _, failed3 = passes_quant_gates(sparse)
    assert ok3
    assert not failed3


def test_parse_nse_xbrl_and_fetch(monkeypatch):
    from stocks.market import shareholding as sh

    sample_xml = """
    <xbrli:context id="FII_ContextI">
      <xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:InstitutionsForeignMember</xbrldi:explicitMember>
    </xbrli:context>
    <xbrli:context id="DII_ContextI">
      <xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:InstitutionsDomesticMember</xbrldi:explicitMember>
    </xbrli:context>
    <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="FII_ContextI">0.0125</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
    <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DII_ContextI">0.0040</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
    """
    pcts = sh._parse_xbrl_shareholding_pcts(sample_xml)
    assert pcts["InstitutionsForeignMember"] == 1.25
    assert pcts["InstitutionsDomesticMember"] == 0.4
    assert sh._nse_quarter_end("30-JUN-2026") == "2026-06-30"


def test_institutional_entry_signal_first_time(tmp_path=None):
    init_db()
    save_shareholding_qtr(
        [
            {
                "ticker": "TESTIE",
                "quarter_end": "2025-12-31",
                "promoter_pct": 60.0,
                "fii_pct": 0.0,
                "dii_pct": 0.0,
                "public_pct": 40.0,
                "source": "test",
            },
            {
                "ticker": "TESTIE",
                "quarter_end": "2026-03-31",
                "promoter_pct": 59.0,
                "fii_pct": 0.0,
                "dii_pct": 1.5,
                "public_pct": 39.5,
                "source": "test",
            },
        ]
    )
    sig = institutional_entry_signal("TESTIE", min_delta=0.3)
    assert sig is not None
    assert sig["first_time_entry"] is True
    assert sig["institutional_pct_delta"] == 1.5


def test_score_ranks_by_inst_delta_not_blend():
    df = pd.DataFrame(
        [
            {
                "ticker": "A",
                "market_cap_cr": 40.0,
                "price_to_sales": 0.8,
                "debt_to_equity": 0.05,
                "sales_cagr": 12.0,
                "profit_positive": True,
                "avg_volume": 8000,
                "years_listed": 4.0,
                "institutional_pct_delta": 0.5,
                "first_time_entry": False,
            },
            {
                "ticker": "B",
                "market_cap_cr": 60.0,
                "price_to_sales": 1.2,
                "debt_to_equity": 0.02,
                "sales_cagr": 20.0,
                "profit_positive": True,
                "avg_volume": 9000,
                "years_listed": 6.0,
                "institutional_pct_delta": 2.0,
                "first_time_entry": True,
            },
            {
                "ticker": "C",
                "market_cap_cr": 50.0,
                "price_to_sales": 0.5,
                "debt_to_equity": 0.01,
                "sales_cagr": 30.0,
                "profit_positive": True,
                "avg_volume": 20000,
                "years_listed": 8.0,
                "institutional_pct_delta": None,
                "first_time_entry": False,
            },
        ]
    )
    scored = score_inst_entry(df, require_signal=True)
    assert list(scored["ticker"]) == ["B", "A"]
    assert scored.iloc[0]["rank"] == 1
