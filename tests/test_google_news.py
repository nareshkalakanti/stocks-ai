from unittest.mock import patch

from stocks.market.google_news import (
    attach_google_news_to_rows,
    build_news_query,
    parse_google_news_rss,
)

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>Plastiblends wins new order</title>
      <link>https://news.example.com/a</link>
      <pubDate>Thu, 10 Jul 2025 08:30:00 GMT</pubDate>
      <source url="https://example.com">Economic Times</source>
    </item>
    <item>
      <title>Masterbatch demand rises</title>
      <link>https://news.example.com/b</link>
      <pubDate>Wed, 09 Jul 2025 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_build_news_query_uses_company_name():
    q = build_news_query("PLASTIBLENDS", "Plastiblends India Limited")
    assert "Plastiblends India" in q
    assert "stock India" in q


def test_parse_google_news_rss():
    items = parse_google_news_rss(_SAMPLE_RSS, limit=5)
    assert len(items) == 2
    assert items[0]["title"] == "Plastiblends wins new order"
    assert items[0]["url"].startswith("https://")
    assert items[0]["when"]
    assert items[0]["source"] == "Economic Times"


def test_attach_google_news_to_rows_uses_cache():
    rows = [{"ticker": "PLASTIBLENDS", "name": "Plastiblends India Limited"}]
    cached = {
        "PLASTIBLENDS": [
            {
                "title": "Cached headline",
                "url": "https://news.example.com/c",
                "published": "2025-07-10 08:30",
                "when": "10 Jul · 08:30",
            }
        ]
    }
    with patch(
        "stocks.market.google_news.load_google_news_for_tickers",
        return_value=cached,
    ):
        out = attach_google_news_to_rows(rows)
    assert out[0]["news"][0]["title"] == "Cached headline"
    assert "news_search_url" in out[0]
