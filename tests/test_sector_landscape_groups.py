"""Sector landscape grouping — avoid duplicate sector/industry keys."""

from collections import defaultdict

from stocks.strategies.sector_landscape.strategy import group_key


def test_industry_key_differs_when_industry_equals_sector():
    sector = "Engineering & Capital Goods"
    industry = sector
    assert group_key(sector, industry, kind="sector") == sector
    assert group_key(sector, industry, kind="industry") == sector
    assert (
        group_key(sector, industry, kind="sector")
        == group_key(sector, industry, kind="industry")
    )


def test_industry_key_uses_short_prefix():
    sector = "Engineering & Capital Goods"
    industry = "Heavy Electrical Equipment"
    assert group_key(sector, industry, kind="industry") == "Engineering - Heavy Electrical Equipment"


def test_build_groups_skips_industry_when_key_matches_sector():
    """Industry rows where industry==sector must not create a duplicate group."""
    rows = [
        {"ticker": "A", "close": None, "return_pct": 1.0, "price": 1.0},
        {"ticker": "B", "close": None, "return_pct": 2.0, "price": 2.0},
    ]
    meta = {
        "A": {"sector": "Engineering & Capital Goods", "industry": "Engineering & Capital Goods"},
        "B": {
            "sector": "Engineering & Capital Goods",
            "industry": "Heavy Electrical Equipment",
        },
    }
    sector_members: dict[str, list] = defaultdict(list)
    industry_members: dict[str, list] = defaultdict(list)
    for row in rows:
        info = meta[row["ticker"]]
        sector = info["sector"]
        industry = info["industry"]
        sector_members[group_key(sector, industry, kind="sector")].append(row)
        ikey = group_key(sector, industry, kind="industry")
        skey = group_key(sector, industry, kind="sector")
        if ikey != skey:
            industry_members[ikey].append(row)

    assert len(sector_members["Engineering & Capital Goods"]) == 2
    assert "Engineering & Capital Goods" not in industry_members
    assert len(industry_members["Engineering - Heavy Electrical Equipment"]) == 1
