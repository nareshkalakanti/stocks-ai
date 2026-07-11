"""Google News RSS headlines for scan expand panels — cached in SQLite."""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from stocks.core.config import (
    GOOGLE_NEWS_CACHE_HOURS,
    GOOGLE_NEWS_MAX_FETCH,
    GOOGLE_NEWS_MAX_WORKERS,
    GOOGLE_NEWS_PER_TICKER,
)
from stocks.core.database import load_google_news_cache, save_google_news_cache
from stocks.core.log_service import NEWS_ERROR, log_error
from stocks.core.text_utils import safe_str

_USER_AGENT = "Mozilla/5.0 (compatible; stocks-ai/1.0)"
_TIMEOUT_SEC = 12
_NAME_SUFFIX_RE = re.compile(
    r"\b(limited|ltd\.?|inc\.?|corp\.?|corporation|plc)\b\.?$",
    re.IGNORECASE,
)


def _format_news_when(raw: str) -> str:
    s = safe_str(raw).strip()
    if not s:
        return "—"
    try:
        if len(s) >= 16 and s[4] == "-":
            dt = datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
            return dt.strftime("%d %b · %H:%M")
    except ValueError:
        pass
    return s[:16] if len(s) > 16 else s


def google_news_search_url(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def google_news_rss_url(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def build_news_query(ticker: str, name: str | None = None) -> str:
    company = safe_str(name).strip()
    if company:
        short = _NAME_SUFFIX_RE.sub("", company).strip(" ,")
        if short:
            return f'"{short}" stock India'
    sym = safe_str(ticker).upper()
    return f"{sym} NSE stock India" if sym else "India stock market"


def parse_google_news_rss(xml_text: str, *, limit: int = GOOGLE_NEWS_PER_TICKER) -> list[dict]:
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[dict] = []
    for item in channel.findall("item"):
        title = safe_str(item.findtext("title")).strip()
        url = safe_str(item.findtext("link")).strip()
        if not title or not url:
            continue
        published = ""
        pub_raw = safe_str(item.findtext("pubDate")).strip()
        if pub_raw:
            try:
                dt = parsedate_to_datetime(pub_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                published = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError, OverflowError):
                published = pub_raw[:16]
        source_el = item.find("source")
        source = safe_str(source_el.text if source_el is not None else "").strip()
        entry = {
            "title": title,
            "url": url,
            "published": published or None,
            "when": _format_news_when(published),
            "source": source or None,
        }
        items.append(entry)
        if len(items) >= max(1, limit):
            break
    return items


def fetch_google_news(ticker: str, name: str | None = None) -> list[dict]:
    query = build_news_query(ticker, name)
    url = google_news_rss_url(query)
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return parse_google_news_rss(resp.text)
    except Exception as exc:
        log_error(
            NEWS_ERROR,
            "Google News fetch failed",
            ticker=ticker,
            query=query,
            error=str(exc),
        )
        return []


def load_google_news_for_tickers(
    specs: list[tuple[str, str | None]],
    *,
    max_hours: int | None = None,
    max_fetch: int | None = None,
    max_per_ticker: int = GOOGLE_NEWS_PER_TICKER,
) -> dict[str, list[dict]]:
    """Return headline lists keyed by ticker; uses SQLite cache then RSS for missing rows."""
    if not specs:
        return {}

    hours = GOOGLE_NEWS_CACHE_HOURS if max_hours is None else max_hours
    fetch_cap = GOOGLE_NEWS_MAX_FETCH if max_fetch is None else max(0, max_fetch)

    ordered: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for ticker, name in specs:
        key = safe_str(ticker).upper()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append((key, safe_str(name) or None))

    cached = load_google_news_cache([t for t, _ in ordered], max_hours=hours)
    out: dict[str, list[dict]] = dict(cached)

    pending: list[tuple[str, str | None]] = [
        (ticker, name) for ticker, name in ordered if ticker not in cached
    ]
    if fetch_cap:
        pending = pending[:fetch_cap]
    if not pending:
        return out

    workers = min(GOOGLE_NEWS_MAX_WORKERS, max(1, len(pending)))
    fresh_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_google_news, ticker, name): (ticker, name)
            for ticker, name in pending
        }
        for future in as_completed(futures):
            ticker, name = futures[future]
            try:
                items = future.result()
            except Exception:
                items = []
            trimmed = items[:max_per_ticker] if items else []
            out[ticker] = trimmed
            fresh_rows.append(
                {
                    "ticker": ticker,
                    "query": build_news_query(ticker, name),
                    "items": trimmed,
                }
            )
    if fresh_rows:
        save_google_news_cache(fresh_rows)
    return out


def attach_google_news_to_rows(rows: list[dict]) -> list[dict]:
    """Add a ``news`` list to each row dict (for expand-panel JSON)."""
    if not rows:
        return rows
    specs = [
        (safe_str(row.get("ticker")), safe_str(row.get("name")) or None)
        for row in rows
        if safe_str(row.get("ticker"))
    ]
    news_map = load_google_news_for_tickers(specs)
    if not news_map:
        return rows
    for row in rows:
        ticker = safe_str(row.get("ticker")).upper()
        items = news_map.get(ticker)
        if items:
            row["news"] = items
            row["news_search_url"] = google_news_search_url(
                build_news_query(ticker, safe_str(row.get("name")) or None)
            )
    return rows
