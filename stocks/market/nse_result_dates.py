"""NSE corporate announcements — financial result / board outcome dates for PEAD."""

from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from stocks.core.config import NSE_RESULT_DATES_CACHE_HOURS
from stocks.core.database import load_nse_result_dates_cache, save_nse_result_dates_cache
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.core.text_utils import safe_str

_NSE_HOME = "https://www.nseindia.com/"
_ANNOUNCE_URL = "https://www.nseindia.com/api/corporate-announcements"
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT_SEC = 30
_LOOKBACK_DAYS = 540

_PERIOD_ENDED_RE = re.compile(
    r"period ended\s+"
    r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[-\s][A-Za-z]+[-\s,]\d{4})",
    re.IGNORECASE,
)
_QUARTER_ENDED_RE = re.compile(
    r"quarter ended\s+"
    r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[-\s][A-Za-z]+[-\s,]\d{4})",
    re.IGNORECASE,
)

_RESULT_DESC_MARKERS = (
    "outcome of board meeting",
    "financial result updates",
    "integrated filing- financial",
    "financial results",
    "unaudited financial results",
    "audited financial results",
)


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


_thread_local: dict[str, requests.Session] = {}


def _session_for_thread() -> requests.Session:
    key = str(threading.get_ident())
    if key not in _thread_local:
        _thread_local[key] = _nse_session()
    return _thread_local[key]


def parse_nse_announcement_timestamp(
    an_dt: str | None,
    *,
    sort_date: str | None = None,
) -> pd.Timestamp | None:
    """Parse NSE ``an_dt`` (``17-Apr-2026 13:05:12``) or ``sort_date`` ISO."""
    for raw in (an_dt, sort_date):
        text = safe_str(raw).strip()
        if not text:
            continue
        for fmt in (
            "%d-%b-%Y %H:%M:%S",
            "%d-%B-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d-%b-%Y",
            "%d-%B-%Y",
        ):
            try:
                return pd.Timestamp(datetime.strptime(text, fmt)).normalize()
            except ValueError:
                continue
        try:
            return pd.Timestamp(text).normalize()
        except (ValueError, TypeError):
            continue
    return None


def parse_period_end_from_text(text: str | None) -> pd.Timestamp | None:
    """Extract quarter/year-end from announcement body (e.g. period ended March 31, 2026)."""
    blob = safe_str(text)
    if not blob:
        return None
    for pattern in (_PERIOD_ENDED_RE, _QUARTER_ENDED_RE):
        match = pattern.search(blob)
        if not match:
            continue
        fragment = match.group(1).strip().rstrip(".")
        normalized = fragment.replace(",", "")
        for fmt in ("%B %d %Y", "%d-%b-%Y", "%d-%B-%Y", "%d %b %Y", "%d %B %Y"):
            try:
                return pd.Timestamp(datetime.strptime(normalized, fmt)).normalize()
            except ValueError:
                continue
        try:
            return pd.Timestamp(fragment).normalize()
        except (ValueError, TypeError):
            continue
    return None


def is_financial_result_announcement(item: dict) -> bool:
    blob = " ".join(
        safe_str(item.get(key))
        for key in ("desc", "subject", "attchmntText", "sm_name")
    ).lower()
    if not blob:
        return False
    if any(marker in blob for marker in _RESULT_DESC_MARKERS):
        if "outcome of board meeting" in blob:
            return "financial result" in blob or "period ended" in blob
        return True
    return "period ended" in blob and "financial" in blob


def normalize_nse_announcement(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    if not is_financial_result_announcement(item):
        return None
    announced_at = parse_nse_announcement_timestamp(
        item.get("an_dt"),
        sort_date=item.get("sort_date"),
    )
    if announced_at is None:
        return None
    text = " ".join(
        safe_str(item.get(key)) for key in ("desc", "subject", "attchmntText")
    )
    period_end = parse_period_end_from_text(text)
    return {
        "result_date": announced_at.strftime("%Y-%m-%d"),
        "period_end": period_end.strftime("%Y-%m-%d") if period_end is not None else None,
        "desc": safe_str(item.get("desc")) or None,
    }


def fetch_nse_result_announcements(
    ticker: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    symbol = safe_str(ticker).upper()
    if not symbol:
        return []
    end = to_date or datetime.now().strftime("%d-%m-%Y")
    start = from_date or (datetime.now() - timedelta(days=_LOOKBACK_DAYS)).strftime("%d-%m-%Y")
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
            "NSE result announcement fetch failed",
            ticker=symbol,
            error=str(exc),
        )
        return []

    if not isinstance(items, list):
        return []

    rows: list[dict] = []
    seen: set[str] = set()
    for item in items:
        row = normalize_nse_announcement(item)
        if row is None:
            continue
        key = f"{row['result_date']}|{row.get('period_end')}|{row.get('desc')}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    rows.sort(key=lambda r: r["result_date"], reverse=True)
    return rows


def _use_nse_for_market(market: str | None) -> bool:
    m = safe_str(market).upper()
    if not m or m == "NSE":
        return True
    return m not in {"BSE", "BOMBAY STOCK EXCHANGE"}


def load_result_announcements(
    ticker: str,
    *,
    market: str | None = None,
    refresh: bool = False,
) -> list[dict]:
    """Cached NSE financial-result announcements for one ticker."""
    symbol = safe_str(ticker).upper()
    if not symbol or not _use_nse_for_market(market):
        return []

    if not refresh:
        cached = load_nse_result_dates_cache([symbol], max_hours=NSE_RESULT_DATES_CACHE_HOURS)
        if symbol in cached:
            payload = cached[symbol].get("announcements")
            if isinstance(payload, list):
                return payload

    rows = fetch_nse_result_announcements(symbol)
    save_nse_result_dates_cache(
        [
            {
                "ticker": symbol,
                "announcements": rows,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )
    return rows


def nse_result_date_for_quarter(
    ticker: str,
    quarter_end: pd.Timestamp,
    *,
    market: str | None = None,
    as_of: pd.Timestamp | None = None,
) -> pd.Timestamp | None:
    """Best NSE announcement date for a quarter-end, if filed."""
    symbol = safe_str(ticker).upper()
    if not symbol or not _use_nse_for_market(market):
        return None

    q_end = pd.Timestamp(quarter_end).tz_localize(None).normalize()
    today = pd.Timestamp(as_of or pd.Timestamp.now())
    if getattr(today, "tzinfo", None) is not None:
        today = today.tz_convert(None)
    today = today.normalize()

    announcements = load_result_announcements(symbol, market=market)
    if not announcements:
        return None

    exact: list[pd.Timestamp] = []
    window: list[pd.Timestamp] = []
    for row in announcements:
        rd = pd.Timestamp(row["result_date"]).normalize()
        if rd > today:
            continue
        pe_raw = row.get("period_end")
        if pe_raw:
            pe = pd.Timestamp(pe_raw).normalize()
            if pe == q_end:
                exact.append(rd)
                continue
        delta = (rd.date() - q_end.date()).days
        if 0 <= delta <= 120:
            window.append(rd)

    if exact:
        return max(exact)
    if window:
        return max(window)
    return None


def nse_announced_dates(
    ticker: str,
    *,
    market: str | None = None,
    as_of: pd.Timestamp | None = None,
) -> list[pd.Timestamp]:
    """All NSE result announcement dates (for quarter-end selection)."""
    symbol = safe_str(ticker).upper()
    if not symbol or not _use_nse_for_market(market):
        return []
    today = pd.Timestamp(as_of or pd.Timestamp.now())
    if getattr(today, "tzinfo", None) is not None:
        today = today.tz_convert(None)
    today = today.normalize()

    out: list[pd.Timestamp] = []
    for row in load_result_announcements(symbol, market=market):
        rd = pd.Timestamp(row["result_date"]).normalize()
        if rd <= today:
            out.append(rd)
    return sorted(set(out))
