"""Corp tags — Holding / SME / demerger badges for scan reports."""

from __future__ import annotations

from stocks.shared.corp_tags import clear_corp_tags_cache, corp_tags_dict_for_ticker, corp_tags_html


def test_corp_tags_html_sme_explicit():
    html = corp_tags_html("HAPPY", is_sme=True, is_holding=False)
    assert "corp-tag-sme" in html
    assert ">SME<" in html
    assert "NSE Emerge" in html


def test_corp_tags_dict_includes_is_sme(monkeypatch):
    clear_corp_tags_cache()
    monkeypatch.setattr(
        "stocks.shared.corp_tags.nse_sme_ticker_set",
        lambda: frozenset({"SPUNWEB"}),
    )
    monkeypatch.setattr(
        "stocks.shared.corp_tags.holdings_ticker_set",
        lambda: frozenset(),
    )
    monkeypatch.setattr(
        "stocks.shared.corp_tags.business_group_map",
        lambda: {},
    )
    monkeypatch.setattr(
        "stocks.shared.corp_tags.parents_ticker_set",
        lambda: frozenset(),
    )
    monkeypatch.setattr(
        "stocks.shared.corp_tags.spinoffs_ticker_set",
        lambda: frozenset(),
    )
    tags = corp_tags_dict_for_ticker("SPUNWEB")
    assert tags.get("is_sme") is True
    assert "corp-tag-sme" in corp_tags_html("SPUNWEB")


def test_governance_html_includes_sme_tag_markup():
    from stocks.governance.html import build_governance_map_html
    import pandas as pd

    rows = pd.DataFrame(
        [
            {
                "person_id": "x",
                "din": "123",
                "name": "Test Dir",
                "director": "Test Dir",
                "board_count": 2,
                "dir_score": 50,
                "din_backed": True,
                "name_collision": False,
                "big_n": 0,
                "small_n": 2,
                "bridge": False,
                "tickers": "HAPPY, TCS",
                "companies": [
                    {
                        "ticker": "HAPPY",
                        "name": "Happy",
                        "market": "NSE SME",
                        "cap_code": "MIC",
                        "is_holding": False,
                        "is_sme": True,
                    },
                    {
                        "ticker": "TCS",
                        "name": "TCS",
                        "market": "NSE",
                        "cap_code": "LC",
                        "is_holding": False,
                        "is_sme": False,
                    },
                ],
                "score_breakdown": {},
            }
        ]
    )
    html = build_governance_map_html(rows, standalone=False)
    assert "gov-tag-sme" in html
    assert "is_sme" in html
