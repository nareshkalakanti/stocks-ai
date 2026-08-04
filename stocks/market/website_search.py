"""Find a corporate website via public web search when Yahoo/screener miss it."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import requests
from lxml import html as lhtml

from stocks.core.config import WEB_ABOUT_REQUEST_DELAY, WEB_ABOUT_TIMEOUT
from stocks.core.text_utils import safe_str, sanitize_website
from stocks.market.website_about import _throttle, verify_corporate_website

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_JUNK_HOST_BITS = (
    "duckduckgo.com",
    "google.",
    "bing.com",
    "yahoo.com",
    "wikipedia.org",
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "youtube.com",
    "instagram.com",
    "moneycontrol.com",
    "screener.in",
    "nseindia.com",
    "bseindia.com",
    "trendlyne.com",
    "tickertape.in",
    "reuters.com",
    "bloomberg.com",
)


def _ddg_unwrap(href: str) -> str:
    """DuckDuckGo result links are often /l/?uddg=<encoded>."""
    raw = safe_str(href)
    if not raw:
        return ""
    if "uddg=" in raw:
        try:
            qs = parse_qs(urlparse(raw).query)
            enc = (qs.get("uddg") or [""])[0]
            if enc:
                return unquote(enc)
        except Exception:
            pass
    if raw.startswith("//"):
        return "https:" + raw
    return raw


def _host_looks_junk(url: str) -> bool:
    low = url.lower()
    return any(h in low for h in _JUNK_HOST_BITS)


def _search_duckduckgo(query: str) -> list[str]:
    _throttle()
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            timeout=WEB_ABOUT_TIMEOUT,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if resp.status_code >= 400:
            return []
        doc = lhtml.fromstring(resp.text)
    except Exception:
        return []

    urls: list[str] = []
    seen: set[str] = set()
    for a in doc.xpath("//a[contains(@class,'result__a')]/@href|//a[@href]"):
        href = a if isinstance(a, str) else safe_str(a)
        href = _ddg_unwrap(href)
        site = sanitize_website(href)
        if not site or _host_looks_junk(site):
            continue
        host = urlparse(site).netloc.lower().removeprefix("www.")
        if not host or host in seen:
            continue
        seen.add(host)
        # Prefer homepage root for discovery.
        root = f"{urlparse(site).scheme}://{urlparse(site).netloc}/"
        urls.append(root)
        if len(urls) >= 8:
            break
    return urls


def search_corporate_website(
    company_name: str,
    *,
    ticker: str = "",
) -> tuple[str | None, str]:
    """
    Search the public web for an official company site; verify it loads.

    Returns (website, source) where source is ``web_search`` or (None, reason).
    """
    name = safe_str(company_name)
    sym = safe_str(ticker).upper()
    if not name and not sym:
        return None, "no_query"

    queries = []
    if name:
        queries.append(f"{name} official website")
        queries.append(f"{name} India investor relations")
    if sym:
        queries.append(f"{sym} NSE official website")

    tried: list[str] = []
    for q in queries:
        for url in _search_duckduckgo(q):
            if url in tried:
                continue
            tried.append(url)
            ok, err = verify_corporate_website(url)
            if ok:
                return ok, "web_search"
            del err
    return None, "web_search_miss"
