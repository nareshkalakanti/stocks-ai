"""Scrape corporate websites for About Us / company-profile text.

Flow: normalize URL → fetch home → discover About/Company links → extract
candidate text blocks → validate + score → return best pass.

Uses requests + lxml (no browser). JS-only sites may fail; validation rejects
nav/cookie/legal boilerplate.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import asdict, dataclass, field
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from lxml import html as lhtml

from stocks.core.config import (
    WEB_ABOUT_MAX_CHARS,
    WEB_ABOUT_MAX_PAGES,
    WEB_ABOUT_MIN_CHARS,
    WEB_ABOUT_MIN_WORDS,
    WEB_ABOUT_PRODUCTS_MAX_CHARS,
    WEB_ABOUT_MARKETS_MAX_CHARS,
    WEB_ABOUT_REQUEST_DELAY,
    WEB_ABOUT_TIMEOUT,
)
from stocks.core.text_utils import safe_str, sanitize_website

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0

_ABOUT_HREF_RE = re.compile(
    r"(?:^|/)("
    r"about(?:[-_/]?us)?|aboutus|who[-_]?we[-_]?are|our[-_]?story|"
    r"company(?:[-_/]?profile)?|corporate[-_]?profile|overview|"
    r"what[-_]?we[-_]?do|our[-_]?company|profile|organisation|organization"
    r")(?:/|$|\.html?)",
    re.I,
)

_ABOUT_ANCHOR_RE = re.compile(
    r"\b("
    r"about\s*us|about\s*the\s*company|who\s*we\s*are|our\s*story|"
    r"company\s*profile|corporate\s*profile|what\s*we\s*do|our\s*company"
    r")\b",
    re.I,
)

_PRODUCT_HREF_RE = re.compile(
    r"(?:^|/)(products?|solutions?|offerings?|business(?:es)?|segments?|"
    r"what[-_]?we[-_]?do|capabilities)(?:/|$|\.html?)",
    re.I,
)
_PRODUCT_ANCHOR_RE = re.compile(
    r"\b(products?|solutions?|our\s+offerings?|business\s+segments?|what\s+we\s+do)\b",
    re.I,
)

_IR_HREF_RE = re.compile(
    r"(?:^|/)(investors?(?:[-_/]?relations)?|shareholders?|annual[-_]?report|"
    r"financial[-_]?results?|ir(?:/|$))(?:/|$|\.html?)",
    re.I,
)
_IR_ANCHOR_RE = re.compile(
    r"\b(investor\s+relations?|shareholders?|annual\s+report|financial\s+results?)\b",
    re.I,
)

# Investment theme tags inferred from site copy (pipe-stored in DB).
_THEME_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (tag, re.compile(pat, re.I))
    for tag, pat in (
        ("copper", r"\bcopper\b"),
        ("aluminium", r"\balumin(?:ium|um)\b"),
        ("cobalt", r"\bcobalt\b"),
        ("nickel", r"\bnickel\b"),
        ("zinc", r"\bzinc\b"),
        ("steel", r"\bsteel\b"),
        ("cdmo", r"\bcdmo\b|contract\s+development\s+and\s+manufactur"),
        ("api", r"\bactive\s+pharmaceutical\b|\bapis?\b"),
        ("formulation", r"\bformulation\b"),
        ("pharma", r"\bpharma(?:ceutical)?\b"),
        ("biotech", r"\bbiotech(?:nology)?\b"),
        ("defence", r"\bdefen[cs]e\b|\baerospace\b"),
        ("ev", r"\belectric\s+vehicle|\bev\b|\bbattery\b"),
        ("renewable", r"\brenewable\b|\bsolar\b|\bwind\s+power\b"),
        ("semiconductor", r"\bsemiconductor\b|\bwafers?\b"),
        ("specialty_chem", r"\bspecialt[y]?\s+chem"),
        ("packaging", r"\bpackaging\b|\bfoil\b"),
        ("auto", r"\bautomotive\b|\boe\s*ms?\b|\bauto\s+component"),
        ("railways", r"\brailways?\b|\bvande\s+bharat\b"),
        ("infra", r"\binfrastructure\b|\bconstruction\b"),
        ("fmcg", r"\bfmcg\b|\bconsumer\s+(?:goods|durables)\b"),
        ("it_services", r"\bit\s+services\b|\bsoftware\s+services\b|\bdigital\s+transformation\b"),
    )
)

_END_MARKET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pat, re.I))
    for label, pat in (
        ("Automotive", r"\bautomotive\b|\bauto\s+oem\b|\boe\s*ms?\b"),
        ("Aerospace & Defence", r"\baerospace\b|\bdefen[cs]e\b"),
        ("Pharma", r"\bpharma(?:ceutical)?\b|\bdrug\b"),
        ("Healthcare", r"\bhealthcare\b|\bhospital\b"),
        ("Electronics", r"\belectronics?\b|\bsemiconductor\b"),
        ("Energy & Power", r"\bpower\b|\benergy\b|\brenewable\b|\bsolar\b"),
        ("Construction", r"\bconstruction\b|\bbuilding\b|\binfrastructure\b"),
        ("Packaging", r"\bpackaging\b"),
        ("Railways", r"\brailways?\b|\brolling\s+stock\b"),
        ("Consumer", r"\bconsumer\b|\bfmcg\b|\bretail\b"),
        ("Industrial", r"\bindustrial\b|\bmanufactur"),
        ("Oil & Gas", r"\boil\s*(?:&|and)\s*gas\b|\bpetrochemical\b"),
        ("Telecom", r"\btelecom(?:munication)?s?\b"),
        ("Agriculture", r"\bagri(?:culture)?\b|\bagro\b"),
    )
)

_BUSINESS_RE = re.compile(
    r"\b("
    r"manufactur|produc|engage|provid|develop|operat|speciali[sz]|"
    r"supplier|distrib|service|solution|business|industri|pharma|"
    r"chemical|engine|technolog|retail|export|import|facility|"
    r"customer|client|product|segment|market"
    r")\w*\b",
    re.I,
)

_REJECT_RE = re.compile(
    r"("
    r"cookie|consent|privacy\s+policy|terms\s+of\s+(use|service)|"
    r"all\s+rights\s+reserved|sign\s+in|log\s+in|subscribe\s+to\s+our|"
    r"enable\s+javascript|cloudflare|captcha|access\s+denied"
    r")",
    re.I,
)

_DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "nav",
    "footer",
    "header",
    "form",
    "aside",
)


@dataclass
class AboutValidation:
    ok: bool
    score: float
    chars: int = 0
    words: int = 0
    business_hits: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class AboutScrapeResult:
    ok: bool
    text: str = ""
    source_url: str = ""
    page_kind: str = ""
    score: float = 0.0
    validation: AboutValidation | None = None
    candidates_tried: list[str] = field(default_factory=list)
    error: str | None = None
    products: str = ""
    end_markets: str = ""
    ir_url: str = ""
    theme_tags: str = ""
    products_url: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        return d

    @property
    def has_investment_fields(self) -> bool:
        return bool(self.products or self.end_markets or self.ir_url or self.theme_tags)


def _throttle() -> None:
    global _LAST_REQUEST_AT
    delay = max(0.0, float(WEB_ABOUT_REQUEST_DELAY))
    with _LOCK:
        now = time.monotonic()
        wait = delay - (now - _LAST_REQUEST_AT)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_AT = time.monotonic()


def normalize_website_url(url: str | None) -> str | None:
    """Canonical https homepage suitable for scraping."""
    site = sanitize_website(url)
    if not site:
        return None
    parsed = urlparse(site)
    if not parsed.netloc:
        return None
    # Drop query/fragment for homepage crawl; keep path if deep link given.
    clean = urlunparse((parsed.scheme or "https", parsed.netloc.lower(), parsed.path or "/", "", "", ""))
    if clean.endswith("://"):
        return None
    return clean


def verify_corporate_website(url: str | None) -> tuple[str | None, str | None]:
    """
    Confirm URL is a reachable corporate site (not a dead link / portal).

    Returns (normalized_url, error). error is None when OK.
    """
    home = normalize_website_url(url)
    if not home:
        return None, "invalid_or_junk_url"
    html, err = _fetch_html(home)
    if not html:
        return None, err or "unreachable"
    low = html.lower()
    if "enable javascript" in low and len(html) < 500:
        return None, "js_shell_only"
    # Reject if the page is clearly a search/portal interstitial.
    if "did not match any documents" in low or "captcha" in low:
        return None, "blocked_or_empty"
    return home, None


def _same_site(base: str, href: str) -> bool:
    try:
        b = urlparse(base)
        h = urlparse(href)
    except Exception:
        return False
    if not h.netloc:
        return True
    return h.netloc.lower().removeprefix("www.") == b.netloc.lower().removeprefix("www.")


def _fetch_html(url: str) -> tuple[str | None, str | None]:
    """Return (html, error)."""
    _throttle()
    try:
        resp = requests.get(
            url,
            timeout=WEB_ABOUT_TIMEOUT,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9",
            },
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            return None, f"HTTP {resp.status_code}"
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "html" not in ctype and "text/" not in ctype and ctype:
            return None, f"non-html content-type: {ctype}"
        text = resp.text or ""
        if len(text) < 80:
            return None, "empty response"
        return text, None
    except requests.Timeout:
        return None, "timeout"
    except requests.RequestException as exc:
        return None, str(exc)[:160]


def _drop_noise(doc: lhtml.HtmlElement) -> None:
    for tag in _DROP_TAGS:
        for node in doc.xpath(f"//{tag}"):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)


def _visible_text(node: lhtml.HtmlElement | None) -> str:
    if node is None:
        return ""
    parts = node.xpath("string(.)")
    raw = parts if isinstance(parts, str) else " ".join(str(p) for p in parts)
    text = unescape(raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _paragraph_blocks(doc: lhtml.HtmlElement) -> list[str]:
    blocks: list[str] = []
    for el in doc.xpath(
        "//main//p|//article//p|//*[@role='main']//p|"
        "//*[contains(translate(@class,'ABOUT','about'),'about')]//p|"
        "//*[contains(translate(@id,'ABOUT','about'),'about')]//p|"
        "//p"
    ):
        t = _visible_text(el)
        if len(t) >= 40:
            blocks.append(t)
    # Dedupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for b in blocks:
        key = b[:120].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return out


def extract_page_text(html: str) -> str:
    """Pull the best company-description prose from an HTML page."""
    try:
        doc = lhtml.fromstring(html)
    except Exception:
        return ""
    _drop_noise(doc)

    # Prefer dedicated about containers.
    preferred: list[str] = []
    for xp in (
        "//main",
        "//article",
        "//*[@role='main']",
        "//*[contains(translate(@id,'ABOUTCOMPANYPROFILE','aboutcompanyprofile'),'about')]",
        "//*[contains(translate(@class,'ABOUTCOMPANYPROFILE','aboutcompanyprofile'),'about')]",
        "//*[contains(translate(@class,'ABOUTCOMPANYPROFILE','aboutcompanyprofile'),'company')]",
    ):
        for node in doc.xpath(xp)[:3]:
            t = _visible_text(node)
            if len(t) >= WEB_ABOUT_MIN_CHARS:
                preferred.append(t)

    paras = _paragraph_blocks(doc)
    joined_paras = " ".join(paras[:12]).strip()

    candidates = [*preferred]
    if joined_paras:
        candidates.append(joined_paras)
    body = doc.find("body")
    body_text = _visible_text(body)
    if body_text:
        candidates.append(body_text)

    best = ""
    best_score = -1.0
    for c in candidates:
        cleaned = _normalize_about_text(c)
        v = validate_about_text(cleaned)
        if v.score > best_score:
            best_score = v.score
            best = cleaned
    return best


def _normalize_about_text(text: str) -> str:
    t = safe_str(text)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > WEB_ABOUT_MAX_CHARS:
        cut = t[:WEB_ABOUT_MAX_CHARS]
        # Prefer ending on a sentence boundary.
        dot = cut.rfind(". ")
        if dot > WEB_ABOUT_MAX_CHARS * 0.6:
            cut = cut[: dot + 1]
        t = cut.strip()
    return t


def validate_about_text(text: str) -> AboutValidation:
    """Score extracted prose; ok=True only when it looks like a real company blurb."""
    t = safe_str(text)
    reasons: list[str] = []
    words = [w for w in re.findall(r"[A-Za-z]{2,}", t)]
    n_chars = len(t)
    n_words = len(words)
    business_hits = len(_BUSINESS_RE.findall(t))

    if n_chars < WEB_ABOUT_MIN_CHARS:
        reasons.append(f"too_short_chars<{WEB_ABOUT_MIN_CHARS}")
    if n_words < WEB_ABOUT_MIN_WORDS:
        reasons.append(f"too_short_words<{WEB_ABOUT_MIN_WORDS}")
    if _REJECT_RE.search(t) and business_hits < 3:
        reasons.append("boilerplate_or_gate")
    if business_hits < 2:
        reasons.append("few_business_keywords")
    # Menu-like: many tiny comma-separated fragments.
    if t.count("|") + t.count("»") > 8 and business_hits < 4:
        reasons.append("looks_like_navigation")

    score = 0.0
    score += min(n_words / 80.0, 1.0) * 35
    score += min(business_hits / 8.0, 1.0) * 45
    score += 10 if ". " in t else 0
    score += 10 if n_chars >= 400 else 0
    score -= 25 * len(reasons)

    ok = not reasons and score >= 40
    # Soft pass: strong business language even if slightly short.
    if not ok and business_hits >= 5 and n_words >= max(20, WEB_ABOUT_MIN_WORDS - 10):
        if "boilerplate_or_gate" not in reasons and "looks_like_navigation" not in reasons:
            ok = True
            score = max(score, 45)
            reasons = [r for r in reasons if not r.startswith("too_short")]

    return AboutValidation(
        ok=ok,
        score=round(score, 1),
        chars=n_chars,
        words=n_words,
        business_hits=business_hits,
        reasons=reasons,
    )


def discover_about_urls(home_url: str, html: str, *, limit: int = 8) -> list[tuple[str, str]]:
    """Return ranked (url, kind) About/Company candidates from homepage anchors."""
    return _discover_urls(
        home_url,
        html,
        limit=limit,
        href_re=_ABOUT_HREF_RE,
        anchor_re=_ABOUT_ANCHOR_RE,
        path_bonus_re=re.compile(r"company|profile|overview", re.I),
        default_kind="about",
        company_kind="company",
    )


def discover_product_urls(home_url: str, html: str, *, limit: int = 6) -> list[tuple[str, str]]:
    return _discover_urls(
        home_url,
        html,
        limit=limit,
        href_re=_PRODUCT_HREF_RE,
        anchor_re=_PRODUCT_ANCHOR_RE,
        path_bonus_re=re.compile(r"product|solution|segment|business", re.I),
        default_kind="products",
        company_kind="products",
    )


def discover_ir_urls(home_url: str, html: str, *, limit: int = 4) -> list[tuple[str, str]]:
    return _discover_urls(
        home_url,
        html,
        limit=limit,
        href_re=_IR_HREF_RE,
        anchor_re=_IR_ANCHOR_RE,
        path_bonus_re=re.compile(r"investor|shareholder|annual|financial", re.I),
        default_kind="ir",
        company_kind="ir",
    )


def _discover_urls(
    home_url: str,
    html: str,
    *,
    limit: int,
    href_re: re.Pattern[str],
    anchor_re: re.Pattern[str],
    path_bonus_re: re.Pattern[str],
    default_kind: str,
    company_kind: str,
) -> list[tuple[str, str]]:
    try:
        doc = lhtml.fromstring(html)
    except Exception:
        return []

    scored: list[tuple[float, str, str]] = []
    seen: set[str] = set()
    for a in doc.xpath("//a[@href]"):
        href = safe_str(a.get("href"))
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        abs_url = urljoin(home_url, href)
        if not _same_site(home_url, abs_url):
            continue
        parsed = urlparse(abs_url)
        path = (parsed.path or "/").lower()
        label = safe_str(a.text_content())
        kind = ""
        pts = 0.0
        if href_re.search(path):
            kind = default_kind
            pts += 50
        if anchor_re.search(label):
            kind = kind or default_kind
            pts += 40
        if path_bonus_re.search(path):
            kind = kind or company_kind
            pts += 25
        if not pts:
            continue
        pts -= min(len(path) / 20.0, 8)
        key = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        scored.append((pts, abs_url, kind or default_kind))

    scored.sort(key=lambda x: -x[0])
    return [(u, k) for _, u, k in scored[:limit]]


def extract_products_text(html: str) -> str:
    """Compact products / solutions blurb from a products page."""
    try:
        doc = lhtml.fromstring(html)
    except Exception:
        return ""
    _drop_noise(doc)
    bits: list[str] = []
    for el in doc.xpath(
        "//main//h1|//main//h2|//main//h3|//article//h2|//article//h3|"
        "//main//li|//article//li|//main//p|//article//p"
    )[:40]:
        t = _visible_text(el)
        if 18 <= len(t) <= 220 and not _REJECT_RE.search(t):
            bits.append(t)
    # Fallback paragraphs.
    if len(bits) < 3:
        for p in _paragraph_blocks(doc)[:8]:
            if not _REJECT_RE.search(p):
                bits.append(p)
    seen: set[str] = set()
    out: list[str] = []
    for b in bits:
        key = b[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
        joined = "; ".join(out)
        if len(joined) >= WEB_ABOUT_PRODUCTS_MAX_CHARS:
            break
    text = "; ".join(out)
    if len(text) > WEB_ABOUT_PRODUCTS_MAX_CHARS:
        text = text[:WEB_ABOUT_PRODUCTS_MAX_CHARS].rsplit(";", 1)[0].strip()
    # Reject nav/cookie leftovers.
    if _REJECT_RE.search(text) and len(_BUSINESS_RE.findall(text)) < 2:
        return ""
    if len(re.findall(r"[A-Za-z]{2,}", text)) < 12:
        return ""
    return text


def extract_end_markets(*texts: str) -> str:
    blob = " ".join(safe_str(t) for t in texts if t)
    if not blob:
        return ""
    hits: list[str] = []
    for label, pat in _END_MARKET_PATTERNS:
        if pat.search(blob):
            hits.append(label)
    text = ", ".join(hits)
    if len(text) > WEB_ABOUT_MARKETS_MAX_CHARS:
        text = text[:WEB_ABOUT_MARKETS_MAX_CHARS].rsplit(",", 1)[0].strip()
    return text


def extract_theme_tags(*texts: str) -> str:
    blob = " ".join(safe_str(t) for t in texts if t)
    if not blob:
        return ""
    tags: list[str] = []
    for tag, pat in _THEME_PATTERNS:
        if pat.search(blob):
            tags.append(tag)
    return "|".join(tags)


def pick_ir_url(home_url: str, html: str) -> str:
    urls = discover_ir_urls(home_url, html, limit=3)
    return urls[0][0] if urls else ""


def _page_kind_for_url(url: str) -> str:
    path = (urlparse(url).path or "").lower()
    if _ABOUT_HREF_RE.search(path):
        return "about"
    if re.search(r"company|profile|overview", path, re.I):
        return "company"
    return "home"


def _is_better(candidate: AboutScrapeResult, current: AboutScrapeResult) -> bool:
    """Rank validated about/company pages above homepage marketing copy."""
    if candidate.ok != current.ok:
        return candidate.ok
    cand_about = candidate.page_kind in {"about", "company"}
    cur_about = current.page_kind in {"about", "company"}
    if cand_about != cur_about:
        return cand_about
    return candidate.score > current.score


def scrape_website_about(
    website: str,
    *,
    max_pages: int | None = None,
) -> AboutScrapeResult:
    """Open a corporate site and return About + investment fields (products/markets/IR/tags)."""
    home = normalize_website_url(website)
    if not home:
        return AboutScrapeResult(ok=False, error="invalid_website")

    page_cap = max_pages if max_pages is not None else WEB_ABOUT_MAX_PAGES
    page_cap = max(1, int(page_cap))

    home_html, err = _fetch_html(home)
    tried = [home]
    if not home_html:
        return AboutScrapeResult(
            ok=False,
            source_url=home,
            candidates_tried=tried,
            error=err or "home_fetch_failed",
        )

    ir_url = pick_ir_url(home, home_html)

    candidates: list[tuple[str, str]] = [(home, "home")]
    for url, kind in discover_about_urls(home, home_html, limit=page_cap):
        if url.rstrip("/") != home.rstrip("/"):
            candidates.append((url, kind))
    candidates = candidates[: page_cap + 1]

    best: AboutScrapeResult | None = None
    page_html_by_url: dict[str, str] = {home: home_html}
    for url, kind in candidates:
        if url not in tried:
            tried.append(url)
        if url.rstrip("/") == home.rstrip("/") and kind == "home":
            html = home_html
        else:
            html, fetch_err = _fetch_html(url)
            if not html:
                continue
            del fetch_err
            page_html_by_url[url] = html
        text = extract_page_text(html)
        validation = validate_about_text(text)
        kind_boost = 12.0 if kind in {"about", "company"} else 0.0
        result = AboutScrapeResult(
            ok=validation.ok,
            text=text if validation.ok else text,
            source_url=url,
            page_kind=kind or _page_kind_for_url(url),
            score=round(validation.score + kind_boost, 1),
            validation=validation,
            candidates_tried=list(tried),
            ir_url=ir_url,
        )
        if best is None or _is_better(result, best):
            best = result
        if result.ok and kind in {"about", "company"} and validation.score >= 45:
            best = result
            break

    if best is None:
        return AboutScrapeResult(
            ok=False,
            source_url=home,
            candidates_tried=tried,
            error="no_content",
            ir_url=ir_url,
        )

    # Products / solutions page (best investment add-on after About).
    products = ""
    products_url = ""
    for url, _kind in discover_product_urls(home, home_html, limit=3):
        if url not in tried:
            tried.append(url)
        html = page_html_by_url.get(url)
        if html is None:
            html, _ = _fetch_html(url)
            if html:
                page_html_by_url[url] = html
        if not html:
            continue
        products = extract_products_text(html)
        if products:
            products_url = url
            break
    if not products:
        # Fallback: product-ish lines from about/home text.
        products = extract_products_text(page_html_by_url.get(best.source_url) or home_html)

    end_markets = extract_end_markets(best.text, products)
    theme_tags = extract_theme_tags(best.text, products, end_markets)

    best.products = products
    best.products_url = products_url
    best.end_markets = end_markets
    best.ir_url = ir_url or best.ir_url
    best.theme_tags = theme_tags
    best.candidates_tried = list(tried)

    if not best.ok:
        best.error = "validation_failed"
        if best.validation and best.validation.reasons:
            best.error = "validation_failed:" + ",".join(best.validation.reasons)
        best.text = ""
        # Still useful if we got real products / IR / tags (not cookie leftovers).
        if best.products or best.end_markets or best.ir_url or best.theme_tags:
            best.ok = True
            best.error = None
            best.page_kind = best.page_kind or "products"
    return best


def scrape_about_for_ticker(ticker: str, market: str | None = None) -> AboutScrapeResult:
    """Resolve website from profile cache / screener / Yahoo, then scrape About."""
    from stocks.core.database import load_company_profiles_from_db
    from stocks.market.company_profile import _fetch_yfinance_profile
    from stocks.market.screener_profile import fetch_screener_profile

    key = safe_str(ticker).upper()
    if not key:
        return AboutScrapeResult(ok=False, error="missing_ticker")

    website = None
    stored = load_company_profiles_from_db([key]).get(key) or {}
    website = sanitize_website(stored.get("website"))
    if not website:
        scraped = fetch_screener_profile(key, market)
        website = sanitize_website((scraped or {}).get("website"))
    if not website:
        yf_prof = _fetch_yfinance_profile(key, market)
        website = sanitize_website((yf_prof or {}).get("website"))
    if not website:
        return AboutScrapeResult(ok=False, error="no_website")

    result = scrape_website_about(website)
    return result
