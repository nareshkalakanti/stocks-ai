from stocks.market.price_service import to_yfinance_symbol


def test_to_yfinance_symbol_bse_uses_numeric_scrip(monkeypatch):
    monkeypatch.setattr(
        "stocks.shared.links.bse_code_by_ticker",
        lambda: {"TRUECOLORS": "544531", "RAP": "524715"},
    )
    monkeypatch.setattr("stocks.shared.links.nse_listed_symbols", lambda: frozenset())

    assert to_yfinance_symbol("TRUECOLORS", "BSE") == "544531.BO"
    assert to_yfinance_symbol("RAP", "BSE") == "524715.BO"
    assert to_yfinance_symbol("544531", "BSE") == "544531.BO"


def test_to_yfinance_symbol_bse_only_without_market(monkeypatch):
    monkeypatch.setattr(
        "stocks.shared.links.bse_code_by_ticker",
        lambda: {"TRUECOLORS": "544531"},
    )
    monkeypatch.setattr("stocks.shared.links.nse_listed_symbols", lambda: frozenset())

    assert to_yfinance_symbol("TRUECOLORS", None) == "544531.BO"


def test_to_yfinance_symbol_nse_unchanged(monkeypatch):
    monkeypatch.setattr(
        "stocks.shared.links.bse_code_by_ticker",
        lambda: {"RELIANCE": "500325"},
    )
    monkeypatch.setattr(
        "stocks.shared.links.nse_listed_symbols",
        lambda: frozenset({"RELIANCE"}),
    )

    assert to_yfinance_symbol("RELIANCE", "NSE") == "RELIANCE.NS"
