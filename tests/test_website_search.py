"""Corporate website web-search helpers (offline)."""

from stocks.market.website_search import _ddg_unwrap, _host_looks_junk


def test_ddg_unwrap_uddg():
    href = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example.com%2Fabout&rut=abc"
    assert _ddg_unwrap(href) == "https://www.example.com/about"


def test_ddg_unwrap_protocol_relative():
    assert _ddg_unwrap("//www.example.com/") == "https://www.example.com/"


def test_host_looks_junk():
    assert _host_looks_junk("https://moneycontrol.com/stock")
    assert not _host_looks_junk("https://www.example.com/")
