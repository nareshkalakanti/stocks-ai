"""Fetch and parse superstar investor portfolios from Trendlyne shareholding filings."""

from __future__ import annotations

import re
import sqlite3
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

_STOCKROW_TR_RE = re.compile(
    r'<tr>\s*<td[^>]*>.*?class="nolb stockrow"[^>]*>.*?</tr>',
    re.S | re.I,
)

SUPERSTAR_INVESTORS = [
    {"name": "Manohar Devabhaktuni", "query": "MANOHAR DEVABHAKTUNI"},
    {"name": "Madhusudan Kela", "query": "MADHUSUDAN KELA"},
    {"name": "Ashish Kacholia", "query": "ASHISH KACHOLIA"},
    {"name": "Dolly Khanna", "query": "DOLLY KHANNA"},
    {"name": "Porinju V Veliyath", "query": "PORINJU V VELIYATH"},
    {"name": "Ramesh Damani", "query": "RAMESH DAMANI"},
    {
        "name": "Sunil Kumar",
        "query": "SUNIL KUMAR",
        "portfolio_id": "53800",
        "portfolio_slug": "sunil-kumar-portfolio",
    },
    {"name": "Radhakishan Damani", "query": "RADHAKISHAN DAMANI"},
    {
        "name": "Sunil Singhania",
        "query": "SUNIL SINGHANIA",
        "portfolio_id": "182955",
        "portfolio_slug": "sunil-singhania-portfolio",
    },
    {"name": "Mukul Mahavir Agrawal", "query": "MUKUL MAHAVIR AGRAWAL"},
    {"name": "Vijay Kishanlal Kedia", "query": "VIJAY KISHANLAL KEDIA"},
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
}

_NAME_ABBREVS = (
    (r"\bmfg\b", "manufacturing"),
    (r"\bco\b", "company"),
    (r"\bcorp\b", "corporation"),
    (r"\bfin\b", "finance"),
    (r"\bintl\b", "international"),
    (r"\bind\b", "industries"),
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

RESOLVER_VERSION = 5

_symbol_cache: dict[str, dict[str, str]] = {}
_price_cache: dict[str, float | None] = {}


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
        conn.commit()
        conn.close()
    except Exception:
        pass
    for key, cached in list(_symbol_cache.items()):
        if cached.get("symbol") == "IEL" and key == "indiabulls":
            del _symbol_cache[key]


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
                _symbol_cache[norm] = {
                    "symbol": sym,
                    "exchange": exch or "NSE",
                    "screener_slug": slug or sym,
                }
    except Exception:
        pass


def _save_symbol_cache_to_db(norm_name: str, meta: dict[str, str]) -> None:
    if not meta.get("symbol"):
        return
    _init_symbol_cache_table()
    try:
        conn = sqlite3.connect(DB_PATH)
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
        for _, row in stocks.iterrows():
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
    score = overlap / max(len(q_tokens), len(c_tokens))
    extra = len(c_tokens - q_tokens)
    if extra > 0:
        score *= len(q_tokens) / len(c_tokens)
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
        market = "NSE" if exchange == "NSE" else "BSE"
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
    company_name: str, lookup: dict[str, dict[str, str]]
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

    for db_key, meta in lookup.items():
        if db_key == key:
            continue
        name_score = _token_match_score(company_name, db_key)
        if name_score >= 0.55:
            _add(meta, name_score, "fuzzy")

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
) -> dict[str, str]:
    empty = {"symbol": "", "exchange": "", "screener_slug": ""}
    if not candidates:
        return empty

    best_meta = empty
    best_score = float("-inf")
    for meta, name_score, source in candidates:
        price_score = _price_fit_score(
            reference_price, meta["symbol"], meta["exchange"]
        )
        if reference_price is not None and price_score <= -1.0:
            continue
        if reference_price is not None:
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
) -> dict[str, str]:
    norm = _norm_name(company_name)
    cached = _symbol_cache.get(norm)
    if cached and cached.get("symbol"):
        price_ok = _price_fit_score(
            reference_price, cached["symbol"], cached.get("exchange", "NSE")
        )
        if reference_price is None or price_ok >= 0.0:
            return cached

    candidates = _collect_resolution_candidates(company_name, lookup)
    meta = _pick_best_candidate(candidates, reference_price)

    if meta.get("symbol"):
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
    tds = re.findall(r"<td[^>]*>(.*?)</td>", tr_html, re.S | re.I)
    cells: list[str] = []
    for raw in tds:
        text = unescape(re.sub(r"<[^>]+>", " ", str(raw or "")))
        cells.append(re.sub(r"\s+", " ", text).strip())
    return cells


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
    html: str, holder_name: str = ""
) -> list[dict[str, Any]]:
    """Parse all superstar holdings from Trendlyne search or portfolio HTML."""
    if "No Results Found" in html and "publicly holds" not in html:
        return []

    by_company: dict[str, dict[str, Any]] = {}
    for tr_html in _STOCKROW_TR_RE.findall(html):
        cells = _cells_from_tr(tr_html)
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
    return _merge_change_overrides(rows, html)


def _parse_trendlyne_html(html: str, holder_name: str = "") -> list[dict[str, Any]]:
    rows = _parse_trendlyne_stockrows(html, holder_name)
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
    return _parse_trendlyne_stockrows(html, holder_name)


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
) -> pd.DataFrame:
    if not holdings:
        return pd.DataFrame()

    global _price_cache
    _price_cache = {}
    _load_symbol_cache_from_db()
    if company_lookup is None:
        company_lookup = _build_company_lookup()

    df = pd.DataFrame(holdings)

    def _apply_lookup(row: pd.Series) -> pd.Series:
        price = row.get("price")
        ref_price = float(price) if pd.notna(price) and price else None
        meta = _resolve_company(
            row["company_name"], company_lookup, reference_price=ref_price
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
    return df.sort_values(
        ["holding_value_cr", "holding_percent"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


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


def load_superstar_portfolio(
    entry: dict[str, str],
    company_lookup: dict[str, dict[str, str]] | None = None,
) -> dict[str, pd.DataFrame | str | int]:
    """Fetch and enrich one superstar investor portfolio."""
    empty = {
        "all": pd.DataFrame(),
        "new_picks": pd.DataFrame(),
        "increased": pd.DataFrame(),
        "decreased": pd.DataFrame(),
        "unchanged": pd.DataFrame(),
        "count": 0,
        "error": "",
    }
    if company_lookup is None:
        company_lookup = _build_company_lookup()
    try:
        raw = fetch_investor_portfolio(
            entry["query"],
            portfolio_id=entry.get("portfolio_id"),
            portfolio_slug=entry.get("portfolio_slug"),
            holder_name=entry.get("name", ""),
        )
        holder_label = entry.get("name", "")
        if holder_label:
            for row in raw:
                if not safe_str(row.get("holder_name")):
                    row["holder_name"] = holder_label
        df = enrich_holdings(raw, company_lookup)
        return _portfolio_from_df(df)
    except Exception as exc:
        empty["error"] = str(exc)
        return empty


def load_superstar_portfolios(
    investors: list[dict[str, str]] | None = None,
) -> dict[str, dict[str, pd.DataFrame | str | int]]:
    investors = investors or SUPERSTAR_INVESTORS
    company_lookup = _build_company_lookup()
    return {
        entry["name"]: load_superstar_portfolio(entry, company_lookup)
        for entry in investors
    }
