from stocks.shared import links


def test_nse_sme_uses_nse_not_bse(monkeypatch):
    monkeypatch.setattr(
        links,
        "nse_listed_symbols",
        lambda: frozenset({"HAPPY", "ICELCO"}),
    )
    monkeypatch.setattr(
        links,
        "bse_code_by_ticker",
        lambda: {"HAPPY": "543456", "ICELCO": "543457"},
    )

    assert links._prefer_bse("HAPPY", "NSE SME") is False
    assert links.tradingview_chart_symbol("HAPPY", "NSE SME") == "NSE:HAPPY"
    assert links.tradingview_url("HAPPY", "NSE SME").endswith("symbol=NSE:HAPPY")
    assert links.screener_url("HAPPY", "NSE SME") == "https://www.screener.in/company/HAPPY/"


def test_bse_only_still_uses_bse(monkeypatch):
    monkeypatch.setattr(links, "nse_listed_symbols", lambda: frozenset())
    monkeypatch.setattr(links, "bse_code_by_ticker", lambda: {"RAP": "524715"})

    assert links._prefer_bse("RAP", "BSE") is True
    assert links.tradingview_chart_symbol("RAP", "BSE") == "BSE:RAP"
    assert links.screener_url("RAP", "BSE") == "https://www.screener.in/company/524715/"


def test_research_links_ignore_stale_bse_tv(monkeypatch):
    monkeypatch.setattr(
        links,
        "ticker_market_lookup",
        lambda: {"CMRSL": "NSE SME"},
    )
    sc, tv = links.research_links("CMRSL", None)
    assert sc == "https://www.screener.in/company/CMRSL/"
    assert tv.endswith("symbol=NSE:CMRSL")
