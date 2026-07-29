from stocks.market.screener_profile import fetch_market_cap_cr


def test_fetch_market_cap_cr_yahoo_fallback(monkeypatch):
    monkeypatch.setattr(
        "stocks.market.screener_profile.fetch_screener_market_cap_cr",
        lambda _t, _m=None: None,
    )
    monkeypatch.setattr(
        "stocks.market.screener_profile._yahoo_market_cap_cr",
        lambda _t, _m=None: 2100.9,
    )
    assert fetch_market_cap_cr("KCP", "NSE") == 2100.9
