"""NSE Integrated Filing – Financials XBRL helpers (Positive Surprise / Earnings)."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from stocks.core.config import DATA_DIR
from stocks.core.text_utils import safe_str
from stocks.market.nse_result_dates import _session_for_thread

_INTEGRATED_URL = "https://www.nseindia.com/api/integrated-filing-results"
_CACHE_DIR = DATA_DIR / "nse_xbrl_cache"
_TIMEOUT_SEC = 45

_MONTH_NUM = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}

_REV_TAGS = ("RevenueFromOperations",)
_NP_TAGS = ("ProfitLossForPeriod", "ProfitLossForPeriodFromContinuingOperations")
_EPS_TAGS = (
    "BasicEarningsLossPerShareFromContinuingOperations",
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
)


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def quarter_end_iso(raw: str | None) -> str | None:
    """NSE ``30-JUN-2026`` / ``30-Jun-2026`` → ``2026-06-30``."""
    text = safe_str(raw).upper().replace(" ", "")
    if not text:
        return None
    m = re.match(r"^(\d{1,2})-([A-Z]{3})-(\d{4})$", text)
    if not m:
        try:
            return pd.Timestamp(raw).strftime("%Y-%m-%d")
        except Exception:
            return None
    day, mon, year = m.group(1), m.group(2), m.group(3)
    month = _MONTH_NUM.get(mon)
    if not month:
        return None
    return f"{year}-{month}-{int(day):02d}"


def _prior_year_quarter_end(iso: str) -> str | None:
    try:
        ts = pd.Timestamp(iso)
    except Exception:
        return None
    return (ts - pd.DateOffset(years=1)).strftime("%Y-%m-%d")


def _cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]
    return _CACHE_DIR / f"{digest}.xml"


def fetch_xbrl_xml(url: str, *, use_cache: bool = True) -> str | None:
    url = safe_str(url)
    if not url.startswith("http") or url.rstrip("/").endswith("/-"):
        return None
    path = _cache_path(url)
    if use_cache and path.is_file() and path.stat().st_size > 200:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    session = _session_for_thread()
    try:
        resp = session.get(url, timeout=_TIMEOUT_SEC)
        resp.raise_for_status()
        text = resp.text or ""
    except Exception:
        return None
    if len(text) < 200 or "<" not in text:
        return None
    if use_cache:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError:
            pass
    return text


def parse_indas_quarter_xbrl(xml_text: str) -> dict[str, Any] | None:
    """
    Extract OneD (current quarter) revenue / NP / EPS from NSE Ind-AS XBRL.
    """
    if not xml_text:
        return None
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return None

    period_start = period_end = None
    for el in root.iter():
        if _local(el.tag) != "context" or el.attrib.get("id") != "OneD":
            continue
        for c in el.iter():
            ln = _local(c.tag)
            if ln == "startDate":
                period_start = safe_str(c.text) or None
            elif ln == "endDate":
                period_end = safe_str(c.text) or None
        break

    facts: dict[str, float] = {}
    for el in root.iter():
        if el.attrib.get("contextRef") != "OneD" or el.text is None:
            continue
        name = _local(el.tag)
        try:
            val = float(str(el.text).strip().replace(",", ""))
        except (TypeError, ValueError):
            continue
        facts[name] = val

    def _first(tags: tuple[str, ...]) -> float | None:
        for t in tags:
            if t in facts:
                return facts[t]
        return None

    rev = _first(_REV_TAGS)
    np_ = _first(_NP_TAGS)
    eps = _first(_EPS_TAGS)
    if rev is None and np_ is None and eps is None:
        return None
    return {
        "rev_actual": rev,
        "np_actual": np_,
        "eps_actual": eps,
        "period_start": period_start,
        "period_end": period_end,
    }


def fetch_integrated_financial_filings(symbol: str) -> list[dict]:
    """NSE Integrated Filing – Financials list for one symbol (newest first)."""
    sym = safe_str(symbol).upper()
    if not sym:
        return []
    session = _session_for_thread()
    try:
        resp = session.get(
            _INTEGRATED_URL,
            params={"symbol": sym, "integratedType": "Financials"},
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return []
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []

    out: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        xbrl = safe_str(item.get("xbrl"))
        if "INDAS" not in xbrl.upper() or not xbrl.startswith("http"):
            continue
        consol = safe_str(item.get("consolidated")).lower()
        qe = quarter_end_iso(item.get("qe_Date"))
        if not qe:
            continue
        out.append(
            {
                "ticker": sym,
                "name": safe_str(item.get("cmName") or item.get("smName")) or sym,
                "consolidated": safe_str(item.get("consolidated")) or None,
                "is_consolidated": "non" not in consol and "stand" not in consol,
                "audited": safe_str(item.get("audited")) or None,
                "broadcast_at": safe_str(item.get("broadcast_Date")) or None,
                "period_end": qe,
                "xbrl": xbrl,
                "ixbrl": safe_str(item.get("ixbrl")) or None,
                "source": "nse_integrated_financials",
            }
        )
    out.sort(key=lambda r: (r.get("period_end") or "", r.get("broadcast_at") or ""), reverse=True)
    return out


def _pick_filing(filings: list[dict], *, period_end: str | None = None) -> dict | None:
    """Prefer Consolidated Ind-AS filing for period_end (or latest)."""
    pool = filings
    if period_end:
        pool = [f for f in filings if f.get("period_end") == period_end]
    if not pool:
        return None
    consol = [f for f in pool if f.get("is_consolidated")]
    return (consol or pool)[0]


def _pct_change(latest: float | None, prior: float | None) -> float | None:
    if latest is None or prior is None or prior == 0:
        return None
    return round((latest / prior - 1.0) * 100.0, 2)


def seasonal_yoy_metrics_from_nse(
    ticker: str,
    *,
    use_cache: bool = True,
) -> dict[str, Any] | None:
    """
    Latest quarter + same-quarter prior-year Ind-AS XBRL → YoY growth (NSE only).
    """
    filings = fetch_integrated_financial_filings(ticker)
    current = _pick_filing(filings)
    if not current:
        return None
    cur_xml = fetch_xbrl_xml(current["xbrl"], use_cache=use_cache)
    cur = parse_indas_quarter_xbrl(cur_xml or "")
    if not cur:
        return None

    prior_end = _prior_year_quarter_end(current["period_end"])
    prior_filing = _pick_filing(filings, period_end=prior_end) if prior_end else None
    pri = None
    if prior_filing:
        pri_xml = fetch_xbrl_xml(prior_filing["xbrl"], use_cache=use_cache)
        pri = parse_indas_quarter_xbrl(pri_xml or "")

    sales_yoy = _pct_change(cur.get("rev_actual"), (pri or {}).get("rev_actual"))
    np_yoy = _pct_change(cur.get("np_actual"), (pri or {}).get("np_actual"))
    eps_yoy = _pct_change(cur.get("eps_actual"), (pri or {}).get("eps_actual"))

    broadcast = current.get("broadcast_at")
    result_date = None
    if broadcast:
        try:
            result_date = datetime.strptime(broadcast[:16], "%d-%b-%Y %H:%M").strftime("%Y-%m-%d")
        except ValueError:
            try:
                result_date = pd.Timestamp(broadcast).strftime("%Y-%m-%d")
            except Exception:
                result_date = current.get("period_end")

    return {
        "ticker": safe_str(ticker).upper(),
        "name": current.get("name"),
        "market": "NSE",
        "period_end": current.get("period_end"),
        "result_date": result_date,
        "broadcast_at": broadcast,
        "filing_type": "Consolidated" if current.get("is_consolidated") else "Standalone",
        "xbrl": current.get("xbrl"),
        "rev_actual": cur.get("rev_actual"),
        "np_actual": cur.get("np_actual"),
        "eps_actual": cur.get("eps_actual"),
        "sales_yoy": sales_yoy,
        "np_yoy": np_yoy,
        "eps_yoy": eps_yoy,
        "prior_period_end": prior_end if pri else None,
        "feed_source": "nse_xbrl",
    }


__all__ = [
    "fetch_integrated_financial_filings",
    "fetch_xbrl_xml",
    "parse_indas_quarter_xbrl",
    "quarter_end_iso",
    "seasonal_yoy_metrics_from_nse",
]
