"""Enrich demerger rows with resulting company names from NSE announcements."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd
import requests

from stocks.core.config import (
    MERGER_DEMERGER_ENRICH_CACHE_HOURS,
    MERGER_DEMERGER_ENRICH_MAX_WORKERS,
)
from stocks.core.database import load_merger_demerger_enrich_cache, save_merger_demerger_enrich_cache
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.core.text_utils import safe_str

_NSE_HOME = "https://www.nseindia.com/"
_ANNOUNCE_URL = "https://www.nseindia.com/api/corporate-announcements"
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT_SEC = 30

_RESULTING_RE = re.compile(
    r"\band\s+([A-Z][A-Za-z0-9&.'()\- /]{2,100}?)\s*\(\s*(?:the\s+)?Resulting\s+Company(?:\s*\d+)?\s*\)",
    re.IGNORECASE,
)
_RESULTING_PAREN_RE = re.compile(
    r"([A-Z][A-Za-z0-9&.'()\- /]{3,100}?)\s*\(\s*(?:the\s+)?Resulting\s+Company(?:\s*\d+)?\s*\)",
    re.IGNORECASE,
)
_FROM_RESULTING_RE = re.compile(
    r"from\s+([^,]+?),\s*the\s+Resulting\s+Company",
    re.IGNORECASE,
)
_BETWEEN_DEMERGER_RE = re.compile(
    r"Demerger\s+between\s+.+?\s+and\s+(.+?)\s*\(\s*Resulting\s+Company",
    re.IGNORECASE,
)
_ARRANGEMENT_PARTIES_RE = re.compile(
    r"(?:scheme of )?(?:arrangement|demerger)(?:\s+and\s+)?\s*(?:between|for demerger between)\s+"
    r".+?\s+and\s+((?:M/s\s+)?[A-Z][^,.(]+?(?:Limited|Ltd\.?|Company))"
    r"(?:\s+and\s+((?:M/s\s+)?[A-Z][^,.(]+?(?:Limited|Ltd\.?|Company)))?",
    re.IGNORECASE,
)
_DEMERGER_AND_RE = re.compile(
    r"Demerger between\s+.+?\s+and\s+((?:M/s\s+)?[A-Z][^,.(—]+?(?:Limited|Ltd\.?|Company))",
    re.IGNORECASE,
)
_INCORPORATED_RE = re.compile(
    r"incorporated .+? in the name and style of\s+([A-Z][^.(]+?(?:Limited|Ltd\.?|Company))",
    re.IGNORECASE,
)

_INVALID_NAME_FRAGMENTS = (
    "between",
    "arrangement",
    "demerged company",
    "scheme of",
    "demerger",
    "gement between",
    "notice of",
    "petition",
)

_NAME_NOISE = re.compile(
    r"\b(limited|ltd\.?|private|pvt\.?|company|co\.?|the)\b",
    re.IGNORECASE,
)


def _clean_resulting_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", safe_str(name)).strip(" .,-")
    cleaned = re.sub(r"^(?:the|and|M/s)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\(Demerged Company\).*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" .,-")


def _is_valid_resulting_name(name: str) -> bool:
    if len(name) < 4 or len(name) > 90:
        return False
    lower = name.lower()
    return not any(frag in lower for frag in _INVALID_NAME_FRAGMENTS)


def _add_name(names: list[str], raw: str) -> None:
    name = _clean_resulting_name(raw)
    if _is_valid_resulting_name(name) and name not in names:
        names.append(name)


def _parse_resulting_companies(text: str) -> list[str]:
    blob = safe_str(text)
    if not blob:
        return []
    names: list[str] = []
    for pattern in (
        _RESULTING_RE,
        _RESULTING_PAREN_RE,
        _FROM_RESULTING_RE,
        _BETWEEN_DEMERGER_RE,
        _DEMERGER_AND_RE,
        _INCORPORATED_RE,
    ):
        for match in pattern.finditer(blob):
            _add_name(names, match.group(1))
    for match in _ARRANGEMENT_PARTIES_RE.finditer(blob):
        _add_name(names, match.group(1))
        if match.lastindex and match.lastindex >= 2 and match.group(2):
            _add_name(names, match.group(2))
    return names


def _normalize_name(name: str) -> str:
    s = _NAME_NOISE.sub("", safe_str(name).lower())
    return re.sub(r"[^a-z0-9]+", "", s)


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
    import threading

    key = str(threading.get_ident())
    if key not in _thread_local:
        _thread_local[key] = _nse_session()
    return _thread_local[key]


def fetch_resulting_companies_for_ticker(
    ticker: str,
    *,
    from_date: str = "01-01-2018",
    to_date: str | None = None,
) -> list[str]:
    symbol = safe_str(ticker).upper()
    if not symbol:
        return []
    end = to_date or datetime.now().strftime("%d-%m-%Y")
    session = _session_for_thread()
    try:
        resp = session.get(
            _ANNOUNCE_URL,
            params={
                "index": "equities",
                "symbol": symbol,
                "from_date": from_date,
                "to_date": end,
            },
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as exc:
        log_error(
            METRICS_ERROR,
            "NSE demerger announcement fetch failed",
            ticker=symbol,
            error=str(exc),
        )
        return []

    if not isinstance(items, list):
        return []

    names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        blob = " ".join(
            safe_str(item.get(key))
            for key in ("attchmntText", "desc", "subject", "sm_name")
        )
        lower = blob.lower()
        if not any(
            phrase in lower
            for phrase in (
                "demerger",
                "scheme of arrangement",
                "arrangement between",
                "resulting company",
            )
        ):
            continue
        for name in _parse_resulting_companies(blob):
            if name not in names:
                names.append(name)
    return names


def build_name_ticker_map(stocks: pd.DataFrame) -> dict[str, str]:
    if stocks is None or stocks.empty:
        return {}
    out: dict[str, str] = {}
    for _, row in stocks.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        for field in ("name", "company"):
            norm = _normalize_name(row.get(field))
            if norm and norm not in out:
                out[norm] = ticker
        norm_t = _normalize_name(ticker)
        if norm_t:
            out[norm_t] = ticker
    return out


def match_company_to_ticker(name: str, name_map: dict[str, str]) -> str | None:
    norm = _normalize_name(name)
    if not norm:
        return None
    if norm in name_map:
        return name_map[norm]
    # Prefix match on normalized names (e.g. borosilscientific -> BOROSCI or similar)
    best: tuple[int, str] | None = None
    for key, ticker in name_map.items():
        if len(key) < 6:
            continue
        if norm in key or key in norm:
            score = min(len(norm), len(key))
            if best is None or score > best[0]:
                best = (score, ticker)
    return best[1] if best else None


def _enrich_payload(
    names: list[str],
    name_map: dict[str, str],
) -> dict:
    tickers: list[str] = []
    for name in names:
        tk = match_company_to_ticker(name, name_map)
        if tk and tk not in tickers:
            tickers.append(tk)
    return {
        "resulting_companies": names,
        "resulting_tickers": tickers,
        "demerged_company": " · ".join(names) if names else None,
        "demerged_ticker": tickers[0] if len(tickers) == 1 else None,
    }


def enrich_demerger_dataframe(
    df: pd.DataFrame,
    stocks: pd.DataFrame,
    *,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fill demerged company names from NSE announcements for rows still missing them."""
    if df.empty:
        return df

    out = df.copy()
    for col in (
        "demerged_company",
        "demerged_ticker",
        "counterparty_company",
        "counterparty_ticker",
        "row_role",
        "parent_company",
        "parent_ticker",
    ):
        if col not in out.columns:
            out[col] = None

    name_map = build_name_ticker_map(stocks)
    tickers_need = []
    for _, row in out.iterrows():
        if safe_str(row.get("row_role")) == "Spin-off":
            continue
        if safe_str(row.get("demerged_company")):
            continue
        if safe_str(row.get("counterparty_company")):
            continue
        tk = safe_str(row.get("ticker")).upper()
        if tk and tk not in tickers_need:
            tickers_need.append(tk)

    if not tickers_need:
        return out

    cached = (
        {}
        if refresh
        else load_merger_demerger_enrich_cache(
            tickers_need,
            max_hours=MERGER_DEMERGER_ENRICH_CACHE_HOURS,
        )
    )
    to_fetch = [t for t in tickers_need if t not in cached]
    fetched: dict[str, dict] = dict(cached)

    if to_fetch:
        workers = min(MERGER_DEMERGER_ENRICH_MAX_WORKERS, len(to_fetch))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fetch_resulting_companies_for_ticker, t): t for t in to_fetch}
            for fut in as_completed(futures):
                ticker = futures[fut]
                try:
                    names = fut.result()
                except Exception:
                    names = []
                fetched[ticker] = _enrich_payload(names, name_map)
                time.sleep(0.15)
        save_rows = [
            {"ticker": t, **payload, "fetched_at": datetime.now(timezone.utc).isoformat()}
            for t, payload in fetched.items()
            if t in to_fetch
        ]
        if save_rows:
            save_merger_demerger_enrich_cache(save_rows)

    extra_rows: list[dict] = []
    for idx, row in out.iterrows():
        if safe_str(row.get("demerged_company")) or safe_str(row.get("counterparty_company")):
            continue
        if safe_str(row.get("row_role")) == "Spin-off":
            continue
        ticker = safe_str(row.get("ticker")).upper()
        payload = fetched.get(ticker) or {}
        names = payload.get("resulting_companies") or []
        if not names:
            continue
        dem_name = payload.get("demerged_company")
        dem_ticker = payload.get("demerged_ticker")
        out.at[idx, "demerged_company"] = dem_name
        if dem_ticker:
            out.at[idx, "demerged_ticker"] = dem_ticker
        out.at[idx, "counterparty_company"] = dem_name
        out.at[idx, "counterparty_ticker"] = dem_ticker
        if dem_ticker and dem_ticker != ticker:
            out.at[idx, "row_role"] = "Parent"

        dem_tickers = payload.get("resulting_tickers") or ([dem_ticker] if dem_ticker else [])
        for i, name in enumerate(names):
            child_ticker = dem_tickers[i] if i < len(dem_tickers) else None
            if not child_ticker or child_ticker == ticker:
                continue
            if (out["ticker"].astype(str).str.upper() == child_ticker).any():
                continue
            extra_rows.append(
                {
                    "ticker": child_ticker,
                    "company": name,
                    "action_type": row.get("action_type") or "Demerger",
                    "ex_date": row.get("ex_date"),
                    "record_date": row.get("record_date"),
                    "ratio": row.get("ratio"),
                    "parent_company": row.get("company"),
                    "parent_ticker": ticker,
                    "row_role": "Spin-off",
                    "subject": f"Spun off from {row.get('company') or ticker}",
                    "source": "NSE announcements",
                }
            )

    if extra_rows:
        out = pd.concat([out, pd.DataFrame(extra_rows)], ignore_index=True)

    from stocks.market.merger_demerger_supplements import _finalize_counterparty, sort_demerger_groups

    return _finalize_counterparty(sort_demerger_groups(out))
