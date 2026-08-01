"""Fetch and parse superstar investor portfolios from Trendlyne shareholding filings."""

from __future__ import annotations

import re
import sqlite3
import threading
from html import unescape
from typing import Any

import pandas as pd
import requests
import yfinance as yf

from stocks.core.config import DB_PATH
from stocks.market.price_service import to_yfinance_symbol
from stocks.shared.links import bse_code_by_ticker
from stocks.listings.stocks_data import load_india_stocks
from stocks.core.text_utils import safe_str

TRENDLYNE_SEARCH_URL = (
    "https://trendlyne.com/portfolio/superstar-shareholders/custom/?query={query}"
)
TRENDLYNE_PORTFOLIO_URL = (
    "https://trendlyne.com/portfolio/superstar-shareholders/"
    "{portfolio_id}/latest/{portfolio_slug}/"
)

# NOTE: do not use a DOTALL `<tr>.*?stockrow.*?</tr>` regex on full pages —
# Trendlyne HTML is ~1MB and that pattern hangs on catastrophic backtracking.
_STOCKROW_ANCHOR_RE = re.compile(
    r'<a[^>]*class="[^"]*stockrow[^"]*"[^>]*>(.*?)</a>',
    re.I | re.S,
)
_STOCKROW_TITLE_RE = re.compile(
    r'title="([^"]+?)\s+Share Price',
    re.I,
)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


SUPERSTAR_INVESTORS = [
    {
        "name": 'Radhakishan Damani',
        "portfolio_id": '178317',
        "portfolio_slug": 'radhakishan-damani-portfolio',
        "query": 'RADHAKISHAN DAMANI',
        "funds": [
            {"label": 'Bright Star Investments', "query": 'bright star investments'},
        ],
    },
    {
        "name": 'Rakesh Jhunjhunwala and Associates',
        "portfolio_id": '53781',
        "portfolio_slug": 'rakesh-jhunjhunwala-and-associates-portfolio',
        "query": 'RAKESH JHUNJHUNWALA AND ASSOCIATES',
        "funds": [
            {"label": 'RARE Enterprises', "query": 'RARE ENTERPRISES'},
            {
                "label": 'Rekha Jhunjhunwala',
                "portfolio_id": '53782',
                "portfolio_slug": 'rekha-jhunjhunwala-portfolio',
                "query": 'REKHA JHUNJHUNWALA',
            },
        ],
    },
    {
        "name": 'Mukul Agrawal',
        "portfolio_id": '53774',
        "portfolio_slug": 'mukul-agrawal-portfolio',
        "query": 'MUKUL AGRAWAL',
        "funds": [],
    },
    {
        "name": 'Akash Bhanshali',
        "portfolio_id": '53740',
        "portfolio_slug": 'akash-bhanshali-portfolio',
        "query": 'AKASH BHANSHALI',
        "funds": [],
    },
    {
        "name": 'Nemish S Shah',
        "portfolio_id": '53776',
        "portfolio_slug": 'nemish-s-shah-portfolio',
        "query": 'NEMISH S SHAH',
        "funds": [],
    },
    {
        "name": 'Ashish Kacholia',
        "portfolio_id": '53746',
        "portfolio_slug": 'ashish-kacholia-portfolio',
        "query": 'ASHISH KACHOLIA',
        "funds": [],
    },
    {
        "name": 'Sunil Singhania',
        "portfolio_id": '182955',
        "portfolio_slug": 'sunil-singhania-portfolio',
        "query": 'SUNIL SINGHANIA',
        "funds": [
            {"label": 'Abakkus Fund', "portfolio_id": '584233', "portfolio_slug": 'abakkus-fund-portfolio'},
            {"label": 'Abakkus Growth Fund -1', "query": 'ABAKKUS GROWTH FUND -1'},
            {"label": 'Abakkus Emerging Opportunities Fund-1', "query": 'ABAKKUS EMERGING OPPORTUNITIES FUND-1'},
            {"label": 'Abakkus Diversified Alpha Fund', "query": 'abakkus diversified alpha fund'},
        ],
    },
    {
        "name": 'Madhusudan Kela',
        "portfolio_id": '584325',
        "portfolio_slug": 'madhusudan-kela-portfolio',
        "query": 'MADHUSUDAN KELA',
        "funds": [],
    },
    {
        "name": 'Anil Kumar Goel and Associates',
        "portfolio_id": '53743',
        "portfolio_slug": 'anil-kumar-goel-and-associates-portfolio',
        "query": 'ANIL KUMAR GOEL AND ASSOCIATES',
        "funds": [],
    },
    {
        "name": 'Ashish Dhawan',
        "portfolio_id": '53745',
        "portfolio_slug": 'ashish-dhawan-portfolio',
        "query": 'ASHISH DHAWAN',
        "funds": [],
    },
    {
        "name": 'Porinju V Veliyath',
        "portfolio_id": '53777',
        "portfolio_slug": 'porinju-v-veliyath-portfolio',
        "query": 'PORINJU V VELIYATH',
        "funds": [
            {"label": 'Equity Intelligence India Pvt Ltd', "query": 'equity intelligence india private limited'},
        ],
    },
    {
        "name": 'Vijay Kishanlal Kedia',
        "portfolio_id": '53805',
        "portfolio_slug": 'vijay-kishanlal-kedia-portfolio',
        "query": 'VIJAY KISHANLAL KEDIA',
        "funds": [],
    },
    {
        "name": 'Dolly Khanna',
        "portfolio_id": '53757',
        "portfolio_slug": 'dolly-khanna-portfolio',
        "query": 'DOLLY KHANNA',
        "funds": [],
    },
    {
        "name": 'Ramesh Damani',
        "portfolio_id": '62728',
        "portfolio_slug": 'ramesh-damani-portfolio',
        "query": 'RAMESH DAMANI',
        "funds": [],
    },
    {
        "name": 'Sunil Kumar',
        "portfolio_id": '53800',
        "portfolio_slug": 'sunil-kumar-portfolio',
        "query": 'SUNIL KUMAR',
        "funds": [],
    },
    {
        "name": 'Ajay Upadhyaya',
        "portfolio_id": '53739',
        "portfolio_slug": 'ajay-upadhyaya-portfolio',
        "query": 'AJAY UPADHYAYA',
        "funds": [],
    },
    {
        "name": 'Hitesh Ramji Javeri and Associates',
        "portfolio_id": '53762',
        "portfolio_slug": 'hitesh-ramji-javeri-and-associates-portfolio',
        "query": 'HITESH RAMJI JAVERI AND ASSOCIATES',
        "funds": [],
    },
    {
        "name": 'Vanaja Sundar Iyer',
        "portfolio_id": '53804',
        "portfolio_slug": 'vanaja-sundar-iyer-portfolio',
        "query": 'VANAJA SUNDAR IYER',
        "funds": [],
    },
    {
        "name": 'Sanjay Gupta',
        "portfolio_id": '53787',
        "portfolio_slug": 'sanjay-gupta-portfolio',
        "query": 'SANJAY GUPTA',
        "funds": [],
    },
    {
        "name": 'Nikhil Vora',
        "portfolio_id": '584329',
        "portfolio_slug": 'nikhil-vora-portfolio',
        "query": 'NIKHIL VORA',
        "funds": [],
    },
    {
        "name": 'Shankar Sharma',
        "portfolio_id": '584326',
        "portfolio_slug": 'shankar-sharma-portfolio',
        "query": 'SHANKAR SHARMA',
        "funds": [],
    },
    {
        "name": 'Manohar Devabhaktuni',
        "query": 'MANOHAR DEVABHAKTUNI',
        "funds": [],
    },
    {
        "name": 'Basava Sankara Rao Kolli',
        "query": 'BASAVA SANKARA RAO KOLLI',
        "funds": [],
    },
    {
        "name": 'Negen Capital / Negen Undiscovered Value Fund',
        "query": 'NEGEN',
        "funds": [
            {
                "label": 'Negen Undiscovered Value Fund',
                "query": 'NEGEN UNDISCOVERED VALUE FUND',
                "screener_people_id": "187659",
                "screener_slug": "negen-undiscovered-value-fund",
            },
            {
                "label": 'Negen Negen Undiscovered Value Fund',
                "query": 'NEGEN NEGEN UNDISCOVERED VALUE FUND',
                "screener_people_id": "144524",
                "screener_slug": "negen-negen-undiscovered-value-fund",
            },
        ],
    },
    {
        "name": 'Niveshaay',
        "query": 'niveshaay',
        "funds": [
            {"label": 'Niveshaay Hedgehogs Fund', "query": 'niveshaay hedgehogs fund'},
            {"label": 'Niveshaay Sambhav Fund', "query": 'niveshaay sambhav fund'},
        ],
    },
]

# Fast path for names yfinance may not return cleanly
COMPANY_OVERRIDES: dict[str, dict[str, str]] = {
    "subam papers": {
        "symbol": "SUBAM",
        "exchange": "BSE",
        "screener_slug": "544267",
    },
    # Trendlyne "Indiabulls Ltd." is the parent (IBULLSLTD), not Enterprises (IEL)
    "indiabulls": {
        "symbol": "IBULLSLTD",
        "exchange": "NSE",
        "screener_slug": "IBULLSLTD",
    },
    # BSE / recently listed — not always in NSE equity+SME CSV yet
    "digilogic systems": {
        "symbol": "DIGILOGIC",
        "exchange": "BSE",
        "screener_slug": "DIGILOGIC",
    },
    "hannah joseph hospital": {
        "symbol": "HANNAH",
        "exchange": "BSE",
        "screener_slug": "HANNAH",
    },
    "jd cables": {
        "symbol": "JDCABLES",
        "exchange": "BSE",
        "screener_slug": "JDCABLES",
    },
    "apollo techno industries": {
        "symbol": "ATIL",
        "exchange": "BSE",
        "screener_slug": "ATIL",
    },
    "true colors": {
        "symbol": "TRUECOLORS",
        "exchange": "BSE",
        "screener_slug": "TRUECOLORS",
    },
}

_NAME_ABBREVS = (
    (r"\bmfg\b", "manufacturing"),
    (r"\bco\b", "company"),
    (r"\bcorp\b", "corporation"),
    (r"\bfin\b", "finance"),
    (r"\bintl\b", "international"),
    (r"\bind\b", "industries"),
    (r"\bcomms\b", "communications"),
    (r"\binfra\b", "infrastructure"),
    (r"\bengg\b", "engineering"),
    (r"\bltd\b", ""),
    (r"\blimited\b", ""),
    (r"\bprivate\b", ""),
    (r"\bpublic\b", ""),
)

_STOP_TOKENS = frozenset(
    {"and", "the", "of", "for", "in", "on", "at", "to", "a", "an", "plc", "inc"}
)

_ROW_RE = re.compile(
    r'<tr>\s*<td class="alphanum[^"]*"[^>]*>\s*<a[^>]*title="([^"]+?)\s+Share Price[^"]*"[^>]*'
    r'(?:\s*class="nolb stockrow")?[^>]*>'
    r"\s*([^<]+?)\s*</a>.*?<td class=\"pr10\">([^<]+)</td>\s*"
    r'<td class="rightAlgn">([^<]+)</td>\s*<td class="rightAlgn">([^<]+)</td>\s*'
    r'<td class="rightAlgn"[^>]*>([^<]+)</td>\s*'
    r'<td class="rightAlgn[^"]*"[^>]*>\s*(.*?)\s*</td>\s*'
    r'<td class="rightAlgn"[^>]*>\s*(.*?)\s*</td>',
    re.S,
)

_ROW_RE_V2 = re.compile(
    r'<tr>\s*<td class="alphanum[^"]*"[^>]*>\s*<a[^>]*title="([^"]+?)\s+Share Price[^"]*"[^>]*'
    r'\s*class="nolb stockrow"[^>]*>\s*'
    r"([^<]+?)\s*</a>.*?"
    r'<td class="pr10">([^<]*)</td>\s*'
    r'<td class="rightAlgn">([^<]+)</td>\s*'
    r'<td class="rightAlgn">([^<]+)</td>\s*'
    r'<td class="[^"]*minorchange[^"]*"[^>]*>(.*?)</td>\s*'
    r'<td class="">([^<]*)</td>\s*'
    r'<td class="rightAlgn"[^>]*>([^<]+)</td>',
    re.S,
)

RESOLVER_VERSION = 6  # NSE SME: strip -SM, keep NSE SME exchange, abbrev expand

_symbol_cache: dict[str, dict[str, str]] = {}
_price_cache: dict[str, float | None] = {}
_symbol_cache_lock = threading.Lock()


def _sme_ticker_set() -> frozenset[str]:
    try:
        from stocks.shared.corp_tags import nse_sme_ticker_set

        return nse_sme_ticker_set()
    except Exception:
        return frozenset()


def _normalize_listing_meta(meta: dict[str, str] | None) -> dict[str, str]:
    """Map Trendlyne ``TICKER-SM`` → listing ticker + ``NSE SME`` when known."""
    empty = {"symbol": "", "exchange": "", "screener_slug": ""}
    if not meta:
        return empty
    symbol = safe_str(meta.get("symbol")).upper()
    exchange = safe_str(meta.get("exchange")).upper() or "NSE"
    slug = safe_str(meta.get("screener_slug")) or symbol
    if not symbol:
        return empty
    base = symbol[:-3] if symbol.endswith("-SM") else symbol
    sme = _sme_ticker_set()
    if base in sme or symbol in sme:
        return {
            "symbol": base,
            "exchange": "NSE SME",
            "screener_slug": slug if slug.endswith("-SM") else f"{base}-SM",
        }
    if symbol.endswith("-SM"):
        # Unknown to SME CSV — still drop suffix; treat as NSE for Yahoo/links.
        return {
            "symbol": base,
            "exchange": "NSE" if exchange in {"", "NSE", "NSE SME"} else exchange,
            "screener_slug": slug or f"{base}-SM",
        }
    if exchange == "NSE SME":
        return {
            "symbol": base,
            "exchange": "NSE SME",
            "screener_slug": slug if "-SM" in slug else (f"{base}-SM" if base else slug),
        }
    return {"symbol": symbol, "exchange": exchange, "screener_slug": slug or symbol}


def _expand_abbreviations(text: str) -> str:
    out = str(text or "").lower()
    for pattern, repl in _NAME_ABBREVS:
        out = re.sub(pattern, repl, out)
    out = out.replace("&", " and ")
    return re.sub(r"\s+", " ", out).strip()


def _norm_name(value: str) -> str:
    text = unescape(str(value or ""))
    text = _expand_abbreviations(text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _name_tokens(value: str) -> set[str]:
    return {
        tok
        for tok in _norm_name(value).split()
        if len(tok) > 2 and tok not in _STOP_TOKENS
    }


def _init_symbol_cache_table() -> None:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS superstar_symbol_cache (
                norm_name TEXT PRIMARY KEY,
                symbol TEXT,
                exchange TEXT,
                screener_slug TEXT,
                resolver_version INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            conn.execute(
                "ALTER TABLE superstar_symbol_cache "
                "ADD COLUMN resolver_version INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
    except Exception:
        pass


def _purge_stale_symbol_cache() -> None:
    """Drop cached mappings from older resolver logic or known bad rows."""
    global _symbol_cache
    _init_symbol_cache_table()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "DELETE FROM superstar_symbol_cache WHERE resolver_version IS NULL "
            "OR resolver_version < ?",
            (RESOLVER_VERSION,),
        )
        conn.execute(
            "DELETE FROM superstar_symbol_cache WHERE norm_name = ? AND symbol = ?",
            ("indiabulls", "IEL"),
        )
        # Stale Trendlyne SME suffixes break mcap / listings joins.
        conn.execute(
            "DELETE FROM superstar_symbol_cache WHERE symbol LIKE '%-SM'"
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    _symbol_cache = {}


def _load_symbol_cache_from_db() -> None:
    global _symbol_cache
    if _symbol_cache:
        return
    _purge_stale_symbol_cache()
    _init_symbol_cache_table()
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT norm_name, symbol, exchange, screener_slug FROM superstar_symbol_cache"
        ).fetchall()
        conn.close()
        for norm, sym, exch, slug in rows:
            if sym:
                _symbol_cache[norm] = _normalize_listing_meta(
                    {
                        "symbol": sym,
                        "exchange": exch or "NSE",
                        "screener_slug": slug or sym,
                    }
                )
    except Exception:
        pass


def _save_symbol_cache_to_db(norm_name: str, meta: dict[str, str]) -> None:
    if not meta.get("symbol"):
        return
    _init_symbol_cache_table()
    try:
        with _symbol_cache_lock:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.execute(
                """
                INSERT INTO superstar_symbol_cache (
                    norm_name, symbol, exchange, screener_slug, resolver_version, updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(norm_name) DO UPDATE SET
                    symbol = excluded.symbol,
                    exchange = excluded.exchange,
                    screener_slug = excluded.screener_slug,
                    resolver_version = excluded.resolver_version,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    norm_name,
                    meta["symbol"],
                    meta.get("exchange", "NSE"),
                    meta.get("screener_slug", meta["symbol"]),
                    RESOLVER_VERSION,
                ),
            )
            conn.commit()
            conn.close()
    except Exception:
        pass


def _build_company_lookup() -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    bse_map = bse_code_by_ticker()

    try:
        stocks = load_india_stocks()
    except Exception:
        stocks = pd.DataFrame()

    if not stocks.empty:
        # Prefer mainboard NSE over SME/BSE when the same normalized name appears.
        market_rank = {"NSE": 0, "NSE SME": 1, "BSE": 2}
        ranked = stocks.copy()
        ranked["_mrank"] = ranked["market"].map(
            lambda m: market_rank.get(safe_str(m).upper(), 9)
        )
        ranked = ranked.sort_values("_mrank", kind="mergesort")
        for _, row in ranked.iterrows():
            name = safe_str(row.get("name"))
            ticker = safe_str(row.get("ticker")).upper()
            market = safe_str(row.get("market")).upper()
            if not name or not ticker:
                continue
            key = _norm_name(name)
            if not key or key in lookup:
                continue
            if market == "BSE":
                bse = bse_map.get(ticker, "")
                lookup[key] = {
                    "symbol": ticker,
                    "exchange": "BSE",
                    "screener_slug": bse or ticker,
                }
            elif market == "NSE SME":
                lookup[key] = {
                    "symbol": ticker,
                    "exchange": "NSE SME",
                    "screener_slug": f"{ticker}-SM",
                }
            else:
                lookup[key] = {
                    "symbol": ticker,
                    "exchange": "NSE",
                    "screener_slug": ticker,
                }

    for key, meta in COMPANY_OVERRIDES.items():
        lookup[_norm_name(key)] = meta

    return lookup


def _token_match_score(
    query: str, candidate: str, *, min_overlap: int | None = None
) -> float:
    q_tokens = _name_tokens(query)
    c_tokens = _name_tokens(candidate)
    if not q_tokens or not c_tokens:
        return 0.0
    overlap = len(q_tokens & c_tokens)
    required = min_overlap if min_overlap is not None else (2 if len(q_tokens) > 1 else 1)
    if overlap < required:
        return 0.0
    score = overlap / len(q_tokens | c_tokens)
    if overlap >= len(q_tokens) and len(q_tokens) >= 2:
        # Trendlyne short names ("Gala Precision") vs full listing names.
        score = max(score, 0.72)
    elif overlap < len(q_tokens):
        # Incomplete query coverage (avoid Apollo Techno → Gujarat Apollo).
        score *= overlap / len(q_tokens)
    return score


def _meta_from_yfinance_symbol(symbol: str) -> dict[str, str]:
    if symbol.endswith(".NS"):
        base = symbol[:-3]
        return {"symbol": base, "exchange": "NSE", "screener_slug": base}
    if symbol.endswith(".BO"):
        base = symbol[:-3]
        return {"symbol": base, "exchange": "BSE", "screener_slug": base}
    return {"symbol": "", "exchange": "", "screener_slug": ""}


def _fetch_market_price(symbol: str, exchange: str) -> float | None:
    cache_key = f"{exchange}:{symbol}"
    if cache_key in _price_cache:
        return _price_cache[cache_key]
    price: float | None = None
    try:
        market = "BSE" if safe_str(exchange).upper() == "BSE" else "NSE"
        yf_sym = to_yfinance_symbol(symbol, market)
        ticker = yf.Ticker(yf_sym)
        fast = getattr(ticker, "fast_info", None)
        if fast is not None:
            raw = getattr(fast, "last_price", None)
            if raw:
                price = float(raw)
        if price is None:
            hist = ticker.history(period="5d", auto_adjust=True)
            if hist is not None and not hist.empty:
                price = float(hist["Close"].iloc[-1])
    except Exception:
        pass
    _price_cache[cache_key] = price
    return price


def _price_fit_score(
    reference_price: float | None, symbol: str, exchange: str
) -> float:
    if reference_price is None or reference_price <= 0:
        return 0.0
    market_price = _fetch_market_price(symbol, exchange)
    if market_price is None or market_price <= 0:
        return -0.15
    rel_err = abs(market_price - reference_price) / reference_price
    if rel_err <= 0.08:
        return 1.0
    if rel_err <= 0.18:
        return 0.55
    if rel_err <= 0.30:
        return 0.0
    return -2.0


def _candidate_key(meta: dict[str, str]) -> str:
    return f"{meta.get('exchange', 'NSE')}:{meta.get('symbol', '')}"


def _collect_resolution_candidates(
    company_name: str,
    lookup: dict[str, dict[str, str]],
    *,
    allow_web_search: bool = True,
) -> list[tuple[dict[str, str], float, str]]:
    key = _norm_name(company_name)
    seen: set[str] = set()
    candidates: list[tuple[dict[str, str], float, str]] = []

    def _add(meta: dict[str, str], name_score: float, source: str) -> None:
        if not meta.get("symbol"):
            return
        ck = _candidate_key(meta)
        if ck in seen:
            return
        seen.add(ck)
        candidates.append((meta, name_score, source))

    if key in lookup:
        _add(lookup[key], 1.0, "exact")
        # Exact DB hit is enough for fast/bulk refresh — skip Yahoo + fuzzy.
        if not allow_web_search:
            return candidates

    for db_key, meta in lookup.items():
        if db_key == key:
            continue
        name_score = _token_match_score(company_name, db_key)
        if name_score >= 0.55:
            _add(meta, name_score, "fuzzy")

    # Strong fuzzy match (≥0.85) is good enough without Yahoo when web search disabled.
    if not allow_web_search:
        return candidates

    try:
        quotes: list[dict] = []
        for query in _yfinance_search_queries(company_name):
            quotes = yf.Search(query, max_results=10).quotes or []
            if quotes:
                break
        for quote in quotes:
            symbol = str(quote.get("symbol") or "")
            label = str(
                quote.get("shortname")
                or quote.get("longname")
                or quote.get("name")
                or ""
            )
            if not symbol or not label:
                continue
            name_score = _token_match_score(company_name, label)
            if symbol.endswith(".NS"):
                name_score += 0.03
            if name_score < 0.45:
                continue
            _add(_meta_from_yfinance_symbol(symbol), name_score, "yfinance")
    except Exception:
        pass

    return candidates


def _pick_best_candidate(
    candidates: list[tuple[dict[str, str], float, str]],
    reference_price: float | None,
    *,
    verify_price: bool = True,
) -> dict[str, str]:
    empty = {"symbol": "", "exchange": "", "screener_slug": ""}
    if not candidates:
        return empty

    best_meta = empty
    best_score = float("-inf")
    for meta, name_score, source in candidates:
        if verify_price and reference_price is not None:
            price_score = _price_fit_score(
                reference_price, meta["symbol"], meta["exchange"]
            )
            if price_score <= -1.0:
                continue
            total = name_score * 0.5 + price_score * 0.5
        else:
            total = name_score
        if source == "exact":
            total += 0.08
        if total > best_score:
            best_score = total
            best_meta = meta
    return best_meta


def _yfinance_search_queries(company_name: str) -> list[str]:
    tokens = _name_tokens(company_name)
    queries = []
    if tokens:
        queries.append(" ".join(sorted(tokens)))
    stripped = re.sub(
        r"\b(ltd|limited|pvt|private|plc|inc)\b\.?",
        "",
        str(company_name or ""),
        flags=re.I,
    )
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped and stripped not in queries:
        queries.append(stripped)
    if company_name and company_name not in queries:
        queries.append(company_name)
    return queries


def _resolve_company(
    company_name: str,
    lookup: dict[str, dict[str, str]],
    reference_price: float | None = None,
    *,
    fast: bool = False,
) -> dict[str, str]:
    """
    Resolve company name → ticker.

    ``fast=True`` (Refresh all): trust symbol cache + local listing lookup; skip
    Yahoo price checks and skip Yahoo search when an exact listing hit exists.
    """
    norm = _norm_name(company_name)
    with _symbol_cache_lock:
        cached = _symbol_cache.get(norm)
    if cached and cached.get("symbol"):
        cached = _normalize_listing_meta(cached)
        if fast:
            return cached
        price_ok = _price_fit_score(
            reference_price, cached["symbol"], cached.get("exchange", "NSE")
        )
        if reference_price is None or price_ok >= 0.0:
            return cached

    # Fast path: local listing + symbol cache only — never call Yahoo during Refresh all.
    allow_web = not fast
    verify_price = not fast
    if fast:
        key = _norm_name(company_name)
        if key in lookup:
            allow_web = False
        candidates = _collect_resolution_candidates(
            company_name, lookup, allow_web_search=False
        )
        meta = _normalize_listing_meta(
            _pick_best_candidate(candidates, reference_price, verify_price=False)
        )
        if meta.get("symbol"):
            with _symbol_cache_lock:
                _symbol_cache[norm] = meta
            _save_symbol_cache_to_db(norm, meta)
        return meta

    candidates = _collect_resolution_candidates(
        company_name, lookup, allow_web_search=allow_web
    )
    meta = _normalize_listing_meta(
        _pick_best_candidate(
            candidates, reference_price, verify_price=verify_price
        )
    )

    if meta.get("symbol"):
        with _symbol_cache_lock:
            _symbol_cache[norm] = meta
        _save_symbol_cache_to_db(norm, meta)

    return meta


def _parse_percent(value: str) -> float | None:
    try:
        return float(str(value).replace("%", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def _parse_change(value: str) -> tuple[float | None, str]:
    raw = re.sub(r"<[^>]+>", "", str(value or "")).strip()
    if not raw:
        return None, "unchanged"
    upper = raw.upper()
    if upper == "NEW":
        return None, "new"
    try:
        num = float(raw)
        if num > 0:
            return num, "increased"
        if num < 0:
            return num, "decreased"
        return 0.0, "unchanged"
    except ValueError:
        return None, "unchanged"


def _parse_value_cr(value: str) -> float:
    raw = re.sub(r"<[^>]+>", "", str(value or "")).strip().lower().replace(",", "")
    if not raw:
        return 0.0
    match = re.search(r"([\d.]+)\s*cr", raw)
    if match:
        return float(match.group(1))
    match = re.search(r"([\d.]+)\s*lac", raw)
    if match:
        return float(match.group(1)) / 100.0
    match = re.search(r"([\d.]+)\s*k", raw)
    if match:
        return float(match.group(1)) / 100000.0
    try:
        return float(raw) / 1e7
    except ValueError:
        return 0.0


def _parse_holding_cell(cell_html: str) -> tuple[float | None, float | None, str]:
    """Parse holding % and QoQ change from Trendlyne table cell (incl. Filing Awaited)."""
    raw = unescape(re.sub(r"<[^>]+>", " ", str(cell_html or "")))
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return None, None, "unchanged"
    if "filing awaited" in raw.lower():
        pct_m = re.search(r"\(([\d.]+)%", raw)
        pct = float(pct_m.group(1)) if pct_m else None
        return pct, None, "unchanged"
    holding_pct = _parse_percent(raw)
    change_num, change_type = _parse_change(raw)
    return holding_pct, change_num, change_type


def _append_trendlyne_row(
    rows: list[dict[str, Any]],
    *,
    company_name: str,
    holder: str,
    price_raw: str,
    qty_raw: str,
    holding_cell: str,
    change_cell: str,
    value_cell: str,
) -> None:
    holding_pct, change_from_holding, change_type_holding = _parse_holding_cell(holding_cell)
    change_num, change_type = _parse_change(change_cell)
    if change_num is None and change_type == "unchanged" and change_from_holding is not None:
        change_num = change_from_holding
    if change_type == "unchanged" and change_type_holding != "unchanged":
        change_type = change_type_holding
    value_cr = _parse_value_cr(value_cell)
    try:
        price = float(str(price_raw).strip().replace(",", ""))
    except ValueError:
        price = None
    try:
        quantity = int(str(qty_raw).strip().replace(",", ""))
    except ValueError:
        quantity = None
    rows.append(
        {
            "company_name": company_name,
            "holder_name": holder,
            "price": price,
            "quantity": quantity,
            "holding_percent": holding_pct,
            "change_qtr": change_num,
            "change_type": change_type,
            "holding_value_cr": value_cr,
        }
    )


def _cells_from_tr(tr_html: str) -> list[str]:
    tds = _TD_RE.findall(tr_html)
    cells: list[str] = []
    for raw in tds:
        text = unescape(_TAG_RE.sub(" ", str(raw or "")))
        cells.append(re.sub(r"\s+", " ", text).strip())
    # Checkbox / empty leading columns on curated portfolio pages.
    while cells and not cells[0]:
        cells.pop(0)
    return cells


def _company_from_stockrow_tr(tr_html: str) -> str:
    title = _STOCKROW_TITLE_RE.search(tr_html)
    if title:
        return unescape(title.group(1).strip())
    anchor = _STOCKROW_ANCHOR_RE.search(tr_html)
    if anchor:
        text = unescape(_TAG_RE.sub(" ", anchor.group(1)))
        return re.sub(r"\s+", " ", text).strip()
    return ""


def _iter_stockrow_trs(html: str) -> list[str]:
    """Linear scan for `<tr>…stockrow…</tr>` — safe on large Trendlyne pages."""
    out: list[str] = []
    lower = html.lower()
    start = 0
    while True:
        idx = lower.find("stockrow", start)
        if idx < 0:
            break
        tr_start = lower.rfind("<tr", 0, idx)
        tr_end = lower.find("</tr>", idx)
        if tr_start < 0 or tr_end < 0:
            start = idx + 8
            continue
        out.append(html[tr_start : tr_end + 5])
        start = tr_end + 5
    return out


def _parse_qty(value: str) -> int | None:
    try:
        return int(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_price(value: str) -> float | None:
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _holding_row(
    *,
    company_name: str,
    holder_name: str,
    price: float | None,
    quantity: int | None,
    holding_percent: float | None,
    change_qtr: float | None,
    change_type: str,
    holding_value_cr: float,
) -> dict[str, Any]:
    return {
        "company_name": company_name,
        "holder_name": holder_name,
        "price": price,
        "quantity": quantity,
        "holding_percent": holding_percent,
        "change_qtr": change_qtr,
        "change_type": change_type,
        "holding_value_cr": holding_value_cr,
    }


def _row_from_search_cells(
    cells: list[str], holder_name: str
) -> dict[str, Any] | None:
    """Custom search page: company, holder, price, qty, holding %, qtr change, value."""
    if len(cells) < 7 or not cells[0]:
        return None
    change_num, change_type = _parse_change(cells[5])
    return _holding_row(
        company_name=cells[0],
        holder_name=cells[1] or holder_name,
        price=_parse_price(cells[2]),
        quantity=_parse_qty(cells[3]),
        holding_percent=_parse_percent(cells[4]),
        change_qtr=change_num,
        change_type=change_type,
        holding_value_cr=_parse_value_cr(cells[6]),
    )


def _row_from_portfolio_cells(
    cells: list[str], holder_name: str
) -> dict[str, Any] | None:
    """Curated portfolio page: company, value, qty, latest qtr change %, holding % columns."""
    if len(cells) < 5 or not cells[0]:
        return None
    value_cr = _parse_value_cr(cells[1])
    qty = _parse_qty(cells[2])
    change_num, change_type = _parse_change(cells[3].replace("%", ""))
    holding_pct = None
    for cell in cells[4:]:
        if cell and cell != "-" and "%" in cell:
            holding_pct = _parse_percent(cell)
            break
    price = None
    if qty and value_cr:
        price = (value_cr * 1e7) / qty
    return _holding_row(
        company_name=cells[0],
        holder_name=holder_name,
        price=price,
        quantity=qty,
        holding_percent=holding_pct,
        change_qtr=change_num,
        change_type=change_type,
        holding_value_cr=value_cr,
    )


def _detect_stockrow_layout(cells: list[str]) -> str:
    # Curated portfolio pages have many quarterly % columns.
    if len(cells) >= 10:
        return "portfolio"
    if len(cells) >= 7:
        if (
            _parse_price(cells[2]) is not None
            and _parse_qty(cells[3]) is not None
            and len(cells) <= 9
        ):
            return "search"
        if "cr" in cells[1].lower():
            return "portfolio"
    if len(cells) >= 4 and "cr" in cells[1].lower():
        return "portfolio"
    return "search"


def _merge_change_overrides(
    rows: list[dict[str, Any]], html: str
) -> list[dict[str, Any]]:
    """Fill change/holding gaps from legacy row regex (e.g. Filing Awaited cells)."""
    if not rows:
        return rows
    by_company = {_norm_name(row["company_name"]): row for row in rows}
    for regex in (_ROW_RE_V2, _ROW_RE):
        for match in regex.finditer(html):
            company = unescape(match.group(2).strip())
            key = _norm_name(company)
            target = by_company.get(key)
            if target is None:
                continue
            holding_pct, change_from_holding, change_type_holding = _parse_holding_cell(
                match.group(6)
            )
            change_num, change_type = _parse_change(match.group(7))
            if change_num is None and change_from_holding is not None:
                change_num = change_from_holding
            if change_type == "unchanged" and change_type_holding != "unchanged":
                change_type = change_type_holding
            if holding_pct is not None and target.get("holding_percent") is None:
                target["holding_percent"] = holding_pct
            if change_type != "unchanged" or change_num not in (None, 0.0):
                target["change_qtr"] = change_num
                target["change_type"] = change_type
    return rows


def _parse_trendlyne_stockrows(
    html: str, holder_name: str = "", *, merge_legacy_changes: bool = False
) -> list[dict[str, Any]]:
    """Parse all superstar holdings from Trendlyne search or portfolio HTML."""
    if "No Results Found" in html and "publicly holds" not in html:
        return []

    by_company: dict[str, dict[str, Any]] = {}
    for tr_html in _iter_stockrow_trs(html):
        cells = _cells_from_tr(tr_html)
        company = _company_from_stockrow_tr(tr_html)
        if company:
            if cells:
                cells[0] = company
            else:
                cells = [company]
        if not cells:
            continue
        layout = _detect_stockrow_layout(cells)
        row = (
            _row_from_search_cells(cells, holder_name)
            if layout == "search"
            else _row_from_portfolio_cells(cells, holder_name)
        )
        if not row:
            continue
        key = _norm_name(row["company_name"])
        prev = by_company.get(key)
        if not prev or row["holding_value_cr"] >= prev["holding_value_cr"]:
            by_company[key] = row

    rows = list(by_company.values())
    # Legacy regex merge is O(catastrophic) on ~1MB pages — only for sparse search HTML.
    if merge_legacy_changes and len(html) < 400_000:
        return _merge_change_overrides(rows, html)
    return rows


def _parse_trendlyne_html(html: str, holder_name: str = "") -> list[dict[str, Any]]:
    rows = _parse_trendlyne_stockrows(
        html, holder_name, merge_legacy_changes=True
    )
    if rows:
        return rows

    # Legacy fallback if Trendlyne markup changes again.
    legacy: list[dict[str, Any]] = []
    for match in _ROW_RE_V2.finditer(html):
        _append_trendlyne_row(
            legacy,
            company_name=unescape(match.group(2).strip()),
            holder=unescape(match.group(3).strip()) or holder_name,
            price_raw=match.group(4),
            qty_raw=match.group(5),
            holding_cell=match.group(6),
            change_cell=match.group(7),
            value_cell=match.group(8),
        )
    if legacy:
        return legacy

    for match in _ROW_RE.finditer(html):
        _append_trendlyne_row(
            legacy,
            company_name=unescape(match.group(2).strip()),
            holder=unescape(match.group(3).strip()) or holder_name,
            price_raw=match.group(4),
            qty_raw=match.group(5),
            holding_cell=match.group(6),
            change_cell=match.group(7),
            value_cell=match.group(8),
        )
    return legacy


def _parse_superstar_portfolio_page(
    html: str, holder_name: str
) -> list[dict[str, Any]]:
    """Parse Trendlyne curated superstar portfolio page (by portfolio id)."""
    return _parse_trendlyne_stockrows(html, holder_name, merge_legacy_changes=False)


def fetch_investor_portfolio(
    query: str,
    timeout: int = 25,
    portfolio_id: str | None = None,
    portfolio_slug: str | None = None,
    holder_name: str = "",
) -> list[dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    if portfolio_id:
        slug = portfolio_slug or "portfolio"
        url = TRENDLYNE_PORTFOLIO_URL.format(
            portfolio_id=portfolio_id, portfolio_slug=slug
        )
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return _parse_superstar_portfolio_page(
            response.text, holder_name or query
        )

    url = TRENDLYNE_SEARCH_URL.format(query=requests.utils.quote(query))
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return _parse_trendlyne_html(response.text, holder_name or query)


def enrich_holdings(
    holdings: list[dict[str, Any]],
    company_lookup: dict[str, dict[str, str]] | None = None,
    *,
    fast: bool = False,
) -> pd.DataFrame:
    if not holdings:
        return pd.DataFrame()

    global _price_cache
    if not fast:
        _price_cache = {}
    _load_symbol_cache_from_db()
    if company_lookup is None:
        company_lookup = _build_company_lookup()

    df = pd.DataFrame(holdings)

    def _apply_lookup(row: pd.Series) -> pd.Series:
        price = row.get("price")
        ref_price = float(price) if pd.notna(price) and price else None
        meta = _resolve_company(
            row["company_name"],
            company_lookup,
            reference_price=None if fast else ref_price,
            fast=fast,
        )
        return pd.Series(
            [
                meta.get("symbol", ""),
                meta.get("exchange", ""),
                meta.get("screener_slug", ""),
            ]
        )

    df[["symbol", "exchange", "screener_slug"]] = df.apply(_apply_lookup, axis=1)
    df["change_display"] = df.apply(
        lambda row: (
            "NEW"
            if row["change_type"] == "new"
            else (
                f"{row['change_qtr']:+.2f}%"
                if row["change_qtr"] is not None
                else "0.00%"
            )
        ),
        axis=1,
    )
    df["holding_value_display"] = df["holding_value_cr"].apply(
        lambda v: f"₹{v:.1f} Cr" if v else ""
    )
    df["price_display"] = df["price"].apply(
        lambda p: f"₹{p:,.2f}" if pd.notna(p) and p else ""
    )
    # Company-name merge can leave two rows that resolve to the same ticker.
    df = _collapse_holdings_by_symbol(df)
    return df.sort_values(
        ["holding_value_cr", "holding_percent"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def _collapse_holdings_by_symbol(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse rows that share the same resolved (symbol, exchange)."""
    if df is None or df.empty or "symbol" not in df.columns:
        return df
    work = df.copy()
    work["_sym"] = work["symbol"].map(lambda v: safe_str(v).upper())
    work["_ex"] = work["exchange"].map(lambda v: safe_str(v).upper() or "NSE") if "exchange" in work.columns else "NSE"
    # Keep unresolved names as distinct rows (empty symbol).
    unresolved = work[work["_sym"] == ""].drop(columns=["_sym", "_ex"], errors="ignore")
    resolved = work[work["_sym"] != ""]
    if resolved.empty:
        return unresolved.reset_index(drop=True) if not unresolved.empty else work.drop(
            columns=["_sym", "_ex"], errors="ignore"
        )

    rows: list[dict[str, Any]] = []
    rank = {"new": 3, "increased": 2, "decreased": 1, "unchanged": 0}
    for (_, _), grp in resolved.groupby(["_sym", "_ex"], sort=False):
        if len(grp) == 1:
            rows.append(grp.drop(columns=["_sym", "_ex"]).iloc[0].to_dict())
            continue
        base = grp.iloc[0].drop(labels=["_sym", "_ex"]).to_dict()
        entities: set[str] = set()
        for _, r in grp.iterrows():
            ent = safe_str(r.get("holding_entity"))
            if ent:
                for part in ent.split(" · "):
                    if safe_str(part):
                        entities.add(safe_str(part))
            if rank.get(safe_str(r.get("change_type")), 0) > rank.get(
                safe_str(base.get("change_type")), 0
            ):
                base["change_type"] = r.get("change_type")
                base["change_qtr"] = r.get("change_qtr")
            try:
                bp = float(base["holding_percent"]) if base.get("holding_percent") is not None else None
            except (TypeError, ValueError):
                bp = None
            try:
                cp = float(r["holding_percent"]) if r.get("holding_percent") is not None else None
            except (TypeError, ValueError):
                cp = None
            if cp is not None and (bp is None or cp > bp):
                base["holding_percent"] = cp
        try:
            base["holding_value_cr"] = float(grp["holding_value_cr"].fillna(0).sum())
        except (TypeError, ValueError):
            pass
        if entities:
            base["holding_entity"] = " · ".join(sorted(entities))
        rows.append(base)

    out = pd.DataFrame(rows)
    if not unresolved.empty:
        out = pd.concat([out, unresolved], ignore_index=True)
    return out


def _portfolio_from_df(df: pd.DataFrame) -> dict[str, pd.DataFrame | str | int]:
    if df.empty or "change_type" not in df.columns:
        return {
            "all": df,
            "new_picks": pd.DataFrame(),
            "increased": pd.DataFrame(),
            "decreased": pd.DataFrame(),
            "unchanged": pd.DataFrame(),
            "count": 0,
            "error": "",
        }
    return {
        "all": df,
        "new_picks": df[df["change_type"] == "new"].copy(),
        "increased": df[df["change_type"] == "increased"].copy(),
        "decreased": df[df["change_type"] == "decreased"].copy(),
        "unchanged": df[df["change_type"] == "unchanged"].copy(),
        "count": len(df),
        "error": "",
    }


def _merge_entity_holdings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Collapse same company across personal + fund entities under one stock row.

    Keeps ``holding_entity`` as a joined label (e.g. ``Personal · Equity Intelligence…``).
    """
    if not rows:
        return []
    by_company: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _norm_name(safe_str(row.get("company_name")))
        if not key:
            continue
        entity = safe_str(row.get("holding_entity") or row.get("holder_name")) or "Personal"
        prev = by_company.get(key)
        if prev is None:
            copy = dict(row)
            copy["holding_entity"] = entity
            entities = {entity}
            copy["_entities"] = entities
            by_company[key] = copy
            continue
        entities: set[str] = prev.get("_entities") or set()
        entities.add(entity)
        prev["_entities"] = entities
        prev["holding_entity"] = " · ".join(sorted(entities))
        prev_val = float(prev.get("holding_value_cr") or 0)
        cur_val = float(row.get("holding_value_cr") or 0)
        prev["holding_value_cr"] = prev_val + cur_val
        # Prefer richer change signal; keep higher single holding %.
        rank = {"new": 3, "increased": 2, "decreased": 1, "unchanged": 0}
        if rank.get(safe_str(row.get("change_type")), 0) > rank.get(
            safe_str(prev.get("change_type")), 0
        ):
            prev["change_type"] = row.get("change_type")
            prev["change_qtr"] = row.get("change_qtr")
        try:
            prev_pct = float(prev.get("holding_percent")) if prev.get("holding_percent") is not None else None
        except (TypeError, ValueError):
            prev_pct = None
        try:
            cur_pct = float(row.get("holding_percent")) if row.get("holding_percent") is not None else None
        except (TypeError, ValueError):
            cur_pct = None
        if cur_pct is not None and (prev_pct is None or cur_pct > prev_pct):
            prev["holding_percent"] = cur_pct
        if not safe_str(prev.get("holder_name")):
            prev["holder_name"] = row.get("holder_name")
    out = []
    for row in by_company.values():
        row.pop("_entities", None)
        out.append(row)
    return out


def _fetch_source_holdings(
    *,
    label: str,
    query: str = "",
    portfolio_id: str | None = None,
    portfolio_slug: str | None = None,
) -> list[dict[str, Any]]:
    raw = fetch_investor_portfolio(
        query or label,
        portfolio_id=portfolio_id,
        portfolio_slug=portfolio_slug,
        holder_name=label,
    )
    for row in raw:
        row["holding_entity"] = label
        if not safe_str(row.get("holder_name")):
            row["holder_name"] = label
    return raw


def load_superstar_portfolio(
    entry: dict[str, Any],
    company_lookup: dict[str, dict[str, str]] | None = None,
    *,
    fast: bool = False,
) -> dict[str, pd.DataFrame | str | int]:
    """
    Fetch personal + linked fund pages, merge under the investor ``name``.

    Example (Porinju): personal Trendlyne portfolio + Equity Intelligence fund
    holdings appear under ``Porinju V Veliyath``, with ``holding_entity`` showing
    which filing name held the stock.

    ``fast=True`` skips Yahoo price verification during ticker resolve (Refresh all).
    """
    empty = {
        "all": pd.DataFrame(),
        "new_picks": pd.DataFrame(),
        "increased": pd.DataFrame(),
        "decreased": pd.DataFrame(),
        "unchanged": pd.DataFrame(),
        "count": 0,
        "error": "",
        "entities": [],
    }
    if company_lookup is None:
        company_lookup = _build_company_lookup()

    investor_name = safe_str(entry.get("name"))
    combined: list[dict[str, Any]] = []
    entities: list[str] = []
    errors: list[str] = []

    has_personal = bool(entry.get("portfolio_id") or entry.get("query"))
    if has_personal:
        personal_label = "Personal"
        try:
            rows = _fetch_source_holdings(
                label=personal_label,
                query=safe_str(entry.get("query")) or investor_name,
                portfolio_id=entry.get("portfolio_id"),
                portfolio_slug=entry.get("portfolio_slug"),
            )
            combined.extend(rows)
            entities.append(personal_label)
        except Exception as exc:
            errors.append(f"Personal: {exc}")

    for fund in entry.get("funds") or []:
        if not isinstance(fund, dict):
            continue
        label = safe_str(fund.get("label")) or "Fund"
        try:
            rows = _fetch_source_holdings(
                label=label,
                query=safe_str(fund.get("query")) or label,
                portfolio_id=fund.get("portfolio_id"),
                portfolio_slug=fund.get("portfolio_slug"),
            )
            combined.extend(rows)
            entities.append(label)
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    if not combined:
        empty["error"] = "; ".join(errors) if errors else "No holdings fetched"
        empty["entities"] = entities
        return empty

    merged = _merge_entity_holdings(combined)
    # Canonical holder under the superstar display name.
    for row in merged:
        row["holder_name"] = investor_name
    try:
        df = enrich_holdings(merged, company_lookup, fast=fast)
        out = _portfolio_from_df(df)
        out["entities"] = entities
        if errors:
            out["error"] = "; ".join(errors)
        return out
    except Exception as exc:
        empty["error"] = str(exc)
        empty["entities"] = entities
        return empty


def load_superstar_portfolios(
    investors: list[dict[str, Any]] | None = None,
    *,
    fast: bool = False,
) -> dict[str, dict[str, pd.DataFrame | str | int]]:
    investors = investors or SUPERSTAR_INVESTORS
    company_lookup = _build_company_lookup()
    return {
        entry["name"]: load_superstar_portfolio(
            entry, company_lookup, fast=fast
        )
        for entry in investors
    }
