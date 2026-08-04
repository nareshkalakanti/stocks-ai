"""yfinance profile enrich helpers."""

from __future__ import annotations

from stocks.market.company_profile import _fetch_yfinance_profile


def test_fetch_yfinance_profile_parses_summary(monkeypatch):
    monkeypatch.setattr(
        "stocks.market.company_profile.to_yfinance_symbol",
        lambda t, m=None: f"{t}.NS",
    )
    monkeypatch.setattr(
        "stocks.market.company_profile.call_throttled",
        lambda fn, delay=0: {
            "longBusinessSummary": (
                "Acme manufactures copper rods and aluminium products for automotive "
                "and defence customers across India."
            ),
            "website": "https://acme.example/",
            "sector": "Basic Materials",
            "industry": "Aluminum",
            "fullTimeEmployees": 1200,
            "city": "Mumbai",
            "country": "India",
            "address1": "One Street",
            "marketCap": 1e10,
        },
    )
    out = _fetch_yfinance_profile("ACME", "NSE")
    assert out["website"].startswith("https://")
    assert "copper" in out["long_description"].lower()
    assert out["company_sector"] == "Basic Materials"
    assert out["company_industry"] == "Aluminum"
    assert out["employees"] == 1200
    assert "Mumbai" in out["headquarters"]
    assert "copper" in (out.get("theme_tags") or "")
    assert "Automotive" in (out.get("end_markets") or "")
    assert out["market_cap_cr"] == 1000.0
