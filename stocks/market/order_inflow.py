"""NSE order / contract inflow — fetch, parse, aggregate (values stored as INR rupees)."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import yfinance as yf

from stocks.core.config import (
    ORDER_INFLOW_CACHE_HOURS,
    ORDER_INFLOW_LOOKBACK_DAYS,
    ORDER_INFLOW_MAX_WORKERS,
    ORDER_INFLOW_MIN_VALUE_CR,
)
from stocks.core.database import load_order_inflow_cache, save_order_inflow_cache
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.core.text_utils import safe_str
from stocks.market.nse_result_dates import parse_nse_announcement_timestamp
from stocks.market.price_service import to_yfinance_symbol
from stocks.market.yfinance_limits import call_fast
from stocks.shared.links import attach_research_links
from stocks.strategies.pead2.service import REVENUE_FIELDS, _series_from_income

_NSE_HOME = "https://www.nseindia.com/"
_ANNOUNCE_URL = "https://www.nseindia.com/api/corporate-announcements"
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT_SEC = 30

_ORDER_SUBJECT_MARKERS = (
    "bagging/receiving of orders",
    "bagging of orders",
    "receiving of orders",
    "receipt of order",
    "orders/contracts",
    "work order",
    "purchase order",
    "letter of intent",
    "contract worth",
    "order worth",
    "order valued",
    "orders valued",
)

_ORDER_BODY_MARKERS = (
    "order worth",
    "contract worth",
    "valued at",
    "value of rs",
    "value of ₹",
    "bagged an order",
    "received an order",
    "awarded a contract",
    "work order",
)

_CR_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr\.?|crores)\b",
    re.IGNORECASE,
)
_CR_WORD_FIRST_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(?:crore|cr\.?|crores)\b",
    re.IGNORECASE,
)
_LAKH_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(?:lakh|lac|lacs)\b",
    re.IGNORECASE,
)
_LAKH_WORD_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(?:lakh|lac|lacs)\b",
    re.IGNORECASE,
)
_USD_RE = re.compile(
    r"(?:usd|\$)\s*([\d,]+(?:\.\d+)?)\s*(million|mn|m|billion|bn|b)?",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"(?:period|duration|within|over|execution|completion)\s*(?:of\s*)?"
    r"(\d{1,3})\s*months?",
    re.IGNORECASE,
)
_DURATION_SIMPLE_RE = re.compile(r"\b(\d{1,3})\s*months?\b", re.IGNORECASE)
_CUSTOMER_FROM_RE = re.compile(
    r"(?:from|awarded by|received from|placed by|by)\s+"
    r"(M/s\.?\s*)?([A-Z][A-Za-z0-9&.'()\- /]{2,80}?)"
    r"(?:\s*[,.]|$|\s+(?:for|to|valued|worth|amount))",
    re.IGNORECASE,
)

_INR_PER_USD_DEFAULT = 84.0


def inr_to_cr(value_inr: int | float | None) -> float | None:
    if value_inr is None:
        return None
    try:
        v = float(value_inr)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return round(v / 1e7, 1)


def fy_label(ts: pd.Timestamp | datetime | str | None) -> str | None:
    if ts is None:
        return None
    try:
        dt = pd.Timestamp(ts)
    except (TypeError, ValueError):
        return None
    if pd.isna(dt):
        return None
    y = dt.year + (1 if dt.month >= 4 else 0)
    return f"FY{y}"


def parse_inr_from_text(text: str | None, *, usd_inr: float = _INR_PER_USD_DEFAULT) -> int | None:
    """Parse announcement text → integer rupees (1 Cr = 1e7)."""
    blob = safe_str(text).replace(",", "")
    if not blob:
        return None

    for pattern in (_CR_RE, _CR_WORD_FIRST_RE):
        match = pattern.search(blob)
        if match:
            return int(round(float(match.group(1)) * 1e7))

    for pattern in (_LAKH_RE, _LAKH_WORD_RE):
        match = pattern.search(blob)
        if match:
            return int(round(float(match.group(1)) * 1e5))

    match = _USD_RE.search(blob)
    if match:
        amount = float(match.group(1))
        unit = safe_str(match.group(2)).lower()
        if unit in ("billion", "bn", "b"):
            amount *= 1e9
        else:
            amount *= 1e6
        return int(round(amount * usd_inr))

    return None


def parse_duration_months(text: str | None) -> int | None:
    blob = safe_str(text)
    if not blob:
        return None
    match = _DURATION_RE.search(blob) or _DURATION_SIMPLE_RE.search(blob)
    if not match:
        return None
    months = int(match.group(1))
    return months if 1 <= months <= 360 else None


def parse_customer(text: str | None) -> str | None:
    blob = safe_str(text)
    if not blob:
        return None
    match = _CUSTOMER_FROM_RE.search(blob)
    if not match:
        return None
    name = re.sub(r"\s+", " ", match.group(2)).strip(" .,-")
    if len(name) < 3 or len(name) > 80:
        return None
    lower = name.lower()
    noise = ("the company", "our company", "not mentioned", "confidential", "registrar")
    if any(n in lower for n in noise):
        return None
    return name


def parse_order_type(subject: str | None, body: str | None) -> str:
    blob = f"{safe_str(subject)} {safe_str(body)}".lower()
    if "work order" in blob:
        return "Work order"
    if "purchase order" in blob:
        return "Purchase order"
    if "letter of intent" in blob:
        return "LOI"
    if "contract" in blob or "contracts" in blob:
        return "Contract"
    if "order" in blob:
        return "Order"
    return "Not mentioned"


def is_order_announcement(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    blob = " ".join(
        safe_str(item.get(key))
        for key in ("desc", "attchmntText", "subject", "sm_name")
    ).lower()
    if not blob:
        return False
    if any(marker in blob for marker in _ORDER_SUBJECT_MARKERS):
        return True
    if "order" in blob and any(marker in blob for marker in _ORDER_BODY_MARKERS):
        return True
    return False


def nse_attachment_url(raw: str | None) -> str | None:
    path = safe_str(raw).strip()
    if not path:
        return None
    if path.startswith("http"):
        return path
    if path.startswith("/"):
        return f"{_NSE_HOME.rstrip('/')}{path}"
    return f"{_NSE_HOME}{path}"


def normalize_order_announcement(item: dict) -> dict | None:
    if not is_order_announcement(item):
        return None
    blob = " ".join(
        safe_str(item.get(key))
        for key in ("attchmntText", "desc", "subject")
    )
    value_inr = parse_inr_from_text(blob)
    if value_inr is None or value_inr <= 0:
        return None

    announced_at = parse_nse_announcement_timestamp(
        item.get("an_dt"),
        sort_date=item.get("sort_date"),
    )
    if announced_at is None:
        return None

    duration = parse_duration_months(blob)
    annual_inr = None
    if duration and duration > 0:
        annual_inr = int(round(value_inr * 12 / duration))

    return {
        "announced_at": announced_at.strftime("%Y-%m-%d"),
        "fy": fy_label(announced_at),
        "customer": parse_customer(blob),
        "order_type": parse_order_type(item.get("desc"), blob),
        "value_inr": value_inr,
        "value_cr": inr_to_cr(value_inr),
        "duration_months": duration,
        "annual_value_inr": annual_inr,
        "annual_value_cr": inr_to_cr(annual_inr) if annual_inr else None,
        "subject": safe_str(item.get("desc")) or safe_str(item.get("subject")) or None,
        "pdf_url": nse_attachment_url(item.get("attchmntFile")),
        "source_id": safe_str(item.get("an_dt")) + "|" + safe_str(item.get("desc"))[:80],
    }


_thread_local: dict[str, requests.Session] = {}


def _nse_session() -> requests.Session:
    session = requests.Session()
    headers = {
        "User-Agent": _USER_AGENT,
        "Referer": _NSE_HOME,
        "Accept": "application/json",
    }
    session.get(_NSE_HOME, headers=headers, timeout=20)
    session.headers.update(headers)
    return session


def _session_for_thread() -> requests.Session:
    key = str(threading.get_ident())
    if key not in _thread_local:
        _thread_local[key] = _nse_session()
    return _thread_local[key]


def fetch_nse_order_announcements(
    ticker: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    symbol = safe_str(ticker).upper()
    if not symbol:
        return []
    end = to_date or datetime.now().strftime("%d-%m-%Y")
    start = from_date or (
        datetime.now() - timedelta(days=ORDER_INFLOW_LOOKBACK_DAYS)
    ).strftime("%d-%m-%Y")
    session = _session_for_thread()
    try:
        resp = session.get(
            _ANNOUNCE_URL,
            params={
                "index": "equities",
                "symbol": symbol,
                "from_date": start,
                "to_date": end,
            },
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as exc:
        log_error(
            METRICS_ERROR,
            "NSE order announcement fetch failed",
            ticker=symbol,
            error=str(exc),
        )
        return []

    if not isinstance(items, list):
        return []

    rows: list[dict] = []
    seen: set[str] = set()
    for item in items:
        row = normalize_order_announcement(item)
        if row is None:
            continue
        key = f"{row['announced_at']}|{row['value_inr']}|{row.get('subject', '')[:60]}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    rows.sort(key=lambda r: r["announced_at"], reverse=True)
    return rows


def _use_nse_for_market(market: str | None) -> bool:
    m = safe_str(market).upper()
    if not m or m == "NSE":
        return True
    return m not in {"BSE", "BOMBAY STOCK EXCHANGE"}


def load_ticker_orders(
    ticker: str,
    *,
    market: str | None = None,
    refresh: bool = False,
) -> list[dict]:
    symbol = safe_str(ticker).upper()
    if not symbol or not _use_nse_for_market(market):
        return []

    if not refresh:
        cached = load_order_inflow_cache([symbol], max_hours=ORDER_INFLOW_CACHE_HOURS)
        if symbol in cached:
            payload = cached[symbol].get("orders")
            if isinstance(payload, list):
                return payload

    rows = fetch_nse_order_announcements(symbol)
    save_order_inflow_cache(
        [
            {
                "ticker": symbol,
                "orders": rows,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )
    return rows


def fetch_ttm_revenue_inr(ticker: str, market: str | None) -> int | None:
    symbol = to_yfinance_symbol(ticker, market)

    def _fetch() -> int | None:
        yt = yf.Ticker(symbol)
        income = yt.quarterly_income_stmt
        revenue = _series_from_income(income, REVENUE_FIELDS)
        if revenue is None or revenue.empty:
            return None
        s = revenue.dropna().sort_index().astype(float)
        if s.empty:
            return None
        ttm = float(s.iloc[-4:].sum()) if len(s) >= 4 else float(s.sum())
        if ttm <= 0:
            return None
        return int(round(ttm))

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Order inflow TTM revenue fetch failed",
            ticker=ticker,
            error=str(exc),
        )

    return call_fast(_fetch, on_error=_log)


def enrich_orders_with_revenue_pct(
    orders: list[dict],
    *,
    ttm_revenue_inr: int | None,
) -> list[dict]:
    out: list[dict] = []
    for row in orders:
        item = dict(row)
        annual = item.get("annual_value_inr") or item.get("value_inr")
        pct = None
        if ttm_revenue_inr and annual:
            pct = round(int(annual) / ttm_revenue_inr * 100, 1)
        item["revenue_pct"] = pct
        out.append(item)
    return out


def aggregate_company_orders(
    ticker: str,
    name: str,
    market: str | None,
    orders: list[dict],
    *,
    ttm_revenue_inr: int | None = None,
    current_fy: str | None = None,
) -> dict | None:
    if not orders:
        return None

    cur_fy = current_fy or fy_label(pd.Timestamp.now())
    prior_fy = None
    if cur_fy and cur_fy.startswith("FY"):
        try:
            prior_fy = f"FY{int(cur_fy[2:]) - 1}"
        except ValueError:
            prior_fy = None

    min_inr = int(ORDER_INFLOW_MIN_VALUE_CR * 1e7)
    filtered = [o for o in orders if int(o.get("value_inr") or 0) >= min_inr]
    if not filtered:
        return None

    total_inr = sum(int(o["value_inr"]) for o in filtered)
    cur_fy_inr = sum(
        int(o["value_inr"]) for o in filtered if o.get("fy") == cur_fy
    )
    prior_fy_inr = sum(
        int(o["value_inr"]) for o in filtered if prior_fy and o.get("fy") == prior_fy
    )
    growth_pct = None
    if prior_fy_inr and prior_fy_inr > 0:
        growth_pct = round((cur_fy_inr / prior_fy_inr - 1) * 100, 2)

    enriched = enrich_orders_with_revenue_pct(filtered, ttm_revenue_inr=ttm_revenue_inr)

    return {
        "ticker": safe_str(ticker).upper(),
        "name": safe_str(name) or safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "order_count": len(filtered),
        "total_inr": total_inr,
        "total_cr": inr_to_cr(total_inr),
        "current_fy": cur_fy,
        "current_fy_inr": cur_fy_inr,
        "current_fy_cr": inr_to_cr(cur_fy_inr),
        "prior_fy_inr": prior_fy_inr,
        "growth_pct": growth_pct,
        "ttm_revenue_inr": ttm_revenue_inr,
        "orders": enriched,
    }


def scan_order_inflow_universe(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    refresh: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    if universe.empty:
        return pd.DataFrame()

    work = universe.drop_duplicates(subset="ticker").copy()
    tickers = work["ticker"].astype(str).tolist()
    markets = work["market"].tolist() if "market" in work.columns else [None] * len(tickers)
    names = work["name"].tolist() if "name" in work.columns else tickers

    workers = min(max_workers or ORDER_INFLOW_MAX_WORKERS, len(tickers), 16)
    cur_fy = fy_label(pd.Timestamp.now())
    summaries: list[dict] = []
    total = len(tickers)
    done = 0

    def _one(args: tuple) -> dict | None:
        ticker, market, name = args
        orders = load_ticker_orders(ticker, market=market, refresh=refresh)
        if not orders:
            return None
        ttm = fetch_ttm_revenue_inr(ticker, market)
        return aggregate_company_orders(
            ticker,
            name,
            market,
            orders,
            ttm_revenue_inr=ttm,
            current_fy=cur_fy,
        )

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(_one, (t, m, n)): t
            for t, m, n in zip(tickers, markets, names)
        }
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                summaries.append(result)
            done += 1
            if progress_callback:
                progress_callback(done, total)

    if not summaries:
        return pd.DataFrame()

    df = pd.DataFrame(summaries)
    df = attach_research_links(df)
    sort_col = "total_inr" if "total_inr" in df.columns else "order_count"
    return df.sort_values(sort_col, ascending=False).reset_index(drop=True)
