"""NSE board composition with DIN — Corporate Governance / Integrated Filing.

Primary quality source for governance.db (not Yahoo).

Discovery:
  1. ``/api/integrated-filing-results?integratedType=Governance`` → iXBRL HTML
  2. Fallback ``/api/corporate-governance-master`` + ``/api/corporate-governance?recId=``
"""

from __future__ import annotations

import re
from typing import Any

import requests
from lxml import html as lhtml

from stocks.core.text_utils import safe_str

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_NSE_HOME = "https://www.nseindia.com/"
_NSE_QUOTE = "https://www.nseindia.com/get-quotes/equity"
_NSE_GOV_REF = (
    "https://www.nseindia.com/companies-listing/corporate-filings-governance"
)
_INTEGRATED_URL = "https://www.nseindia.com/api/integrated-filing-results"
_CG_MASTER_URL = "https://www.nseindia.com/api/corporate-governance-master"
_CG_DETAIL_URL = "https://www.nseindia.com/api/corporate-governance"
_TIMEOUT_SEC = 30

# SEBI dummy DIN when director has no DIN — not a real identity.
_DUMMY_DINS = frozenset({"99999999", "00000000"})

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


def _nse_session() -> requests.Session:
    session = requests.Session()
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json,text/html,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": _NSE_HOME,
    }
    # Quote page tends to set cookies more reliably than bare homepage.
    try:
        session.get(
            _NSE_QUOTE,
            params={"symbol": "TCS"},
            headers=headers,
            timeout=20,
        )
    except Exception:
        try:
            session.get(_NSE_HOME, headers=headers, timeout=20)
        except Exception:
            pass
    session.headers.update(headers)
    return session


def _norm_din(raw: str | None) -> str:
    digits = re.sub(r"\D", "", safe_str(raw))
    if not digits:
        return ""
    return digits.zfill(8)[-8:]


def _quarter_end_iso(raw: str | None) -> str | None:
    """NSE ``31-DEC-2024`` / ``31-Mar-2026`` → ``2024-12-31``."""
    text = safe_str(raw).upper().replace(" ", "")
    if not text:
        return None
    m = re.match(r"^(\d{1,2})-([A-Z]{3})-(\d{4})$", text)
    if not m:
        return None
    day, mon, year = m.group(1), m.group(2), m.group(3)
    month = _MONTH_NUM.get(mon)
    if not month:
        return None
    return f"{year}-{month}-{int(day):02d}"


def _infer_category(text: str) -> str:
    low = text.lower()
    if "independent" in low:
        return "Independent"
    if any(x in low for x in ("executive", "managing", "ceo", "md", "whole")):
        return "Executive"
    if "non-executive" in low or "non executive" in low:
        return "Non-Executive"
    return ""


def _designation_from_parts(*parts: str) -> str:
    bits = [safe_str(p) for p in parts if safe_str(p) and safe_str(p).lower() not in {"", "-", "na", "not applicable"}]
    # Prefer richest non-empty joined label.
    if not bits:
        return "Director"
    # Drop redundant duplicates while keeping order.
    seen: set[str] = set()
    out: list[str] = []
    for b in bits:
        key = b.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return " · ".join(out) if out else "Director"


def _active_status(raw: str | None) -> bool:
    text = safe_str(raw).lower()
    if not text or text in {"-", "na", "n/a"}:
        return True
    if "inactive" in text or "cessation" in text or text == "no":
        return False
    return True


def parse_governance_ixbrl_html(html_text: str, *, as_of: str | None = None) -> list[dict[str, str]]:
    """Parse Composition of Board table from Integrated Filing – Governance iXBRL HTML."""
    if not html_text or not html_text.strip():
        return []
    try:
        tree = lhtml.fromstring(html_text)
    except Exception:
        return []

    seats: list[dict[str, str]] = []
    seen_din: set[str] = set()
    for table in tree.xpath("//table"):
        rows = table.xpath(".//tr")
        if len(rows) < 2:
            continue
        header_idx = None
        col: dict[str, int] = {}
        for i, tr in enumerate(rows[:8]):
            cells = [
                " ".join(c.itertext()).strip()
                for c in tr.xpath("./th|./td")
            ]
            joined = " | ".join(cells).lower()
            if "din" in joined and "name of the director" in joined:
                header_idx = i
                for j, cell in enumerate(cells):
                    key = re.sub(r"\s+", " ", cell.lower())
                    if key.startswith("name of the director"):
                        col["name"] = j
                    elif key == "din" or key.startswith("din"):
                        col["din"] = j
                    elif "category 1" in key:
                        col["cat1"] = j
                    elif "category 2" in key:
                        col["cat2"] = j
                    elif "category 3" in key:
                        col["cat3"] = j
                    elif key.startswith("title"):
                        col["title"] = j
                    elif "current status" in key:
                        col["status"] = j
                    elif "initial date of appointment" in key:
                        col["appointed"] = j
                break
        if header_idx is None or "name" not in col or "din" not in col:
            continue

        for tr in rows[header_idx + 1 :]:
            cells = [" ".join(c.itertext()).strip() for c in tr.xpath("./th|./td")]
            if len(cells) <= max(col.values()):
                continue
            din = _norm_din(cells[col["din"]])
            name = safe_str(cells[col["name"]])
            if not din or din in _DUMMY_DINS or not name:
                continue
            if din in seen_din:
                continue
            status = cells[col["status"]] if "status" in col else ""
            if not _active_status(status):
                continue
            cat1 = cells[col["cat1"]] if "cat1" in col else ""
            cat2 = cells[col["cat2"]] if "cat2" in col else ""
            cat3 = cells[col["cat3"]] if "cat3" in col else ""
            designation = _designation_from_parts(cat1, cat2, cat3)
            category = _infer_category(f"{cat1} {cat2} {cat3}")
            seats.append(
                {
                    "din": din,
                    "name": name,
                    "designation": designation,
                    "category": category,
                    "source": "nse_integrated_governance",
                    "as_of": safe_str(as_of) or "",
                }
            )
            seen_din.add(din)
        if seats:
            break
    return seats


def _parse_composition_bod(
    rows: list[dict[str, Any]],
    *,
    as_of: str | None = None,
    source: str = "nse_corporate_governance",
) -> list[dict[str, str]]:
    seats: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        din = _norm_din(raw.get("din"))
        name = safe_str(raw.get("directorName") or raw.get("name"))
        if not din or din in _DUMMY_DINS or not name:
            continue
        if din in seen:
            continue
        if not _active_status(raw.get("status") or raw.get("currentStatus")):
            continue
        category_raw = safe_str(raw.get("category"))
        designation = category_raw or "Director"
        seats.append(
            {
                "din": din,
                "name": name,
                "designation": designation,
                "category": _infer_category(category_raw),
                "source": source,
                "as_of": safe_str(as_of) or "",
            }
        )
        seen.add(din)
    return seats


def _fetch_integrated_governance(
    ticker: str,
    *,
    session: requests.Session,
) -> dict[str, Any] | None:
    resp = session.get(
        _INTEGRATED_URL,
        params={
            "index": "equities",
            "symbol": ticker,
            "integratedType": "Governance",
        },
        timeout=_TIMEOUT_SEC,
        headers={"Referer": _NSE_GOV_REF},
    )
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return None
    gov = [
        r
        for r in rows
        if isinstance(r, dict)
        and "Governance" in safe_str(r.get("type"))
        and safe_str(r.get("ixbrl")).startswith("http")
    ]
    if not gov:
        return None

    def _sort_key(item: dict) -> str:
        return _quarter_end_iso(item.get("qe_Date")) or ""

    gov.sort(key=_sort_key, reverse=True)
    latest = gov[0]
    ixbrl_url = safe_str(latest.get("ixbrl"))
    as_of = _quarter_end_iso(latest.get("qe_Date"))
    page = session.get(
        ixbrl_url,
        timeout=_TIMEOUT_SEC,
        headers={"Referer": _NSE_HOME},
    )
    page.raise_for_status()
    seats = parse_governance_ixbrl_html(page.text, as_of=as_of)
    if not seats:
        return None
    return {
        "ticker": ticker,
        "name": safe_str(latest.get("cmName") or latest.get("smName")) or ticker,
        "seats": seats,
        "market": "NSE",
        "as_of": as_of,
        "source": "nse_integrated_governance",
        "filing_url": ixbrl_url,
    }


def _fetch_cg_master_board(
    ticker: str,
    *,
    session: requests.Session,
) -> dict[str, Any] | None:
    resp = session.get(
        _CG_MASTER_URL,
        params={"index": "equities", "symbol": ticker},
        timeout=_TIMEOUT_SEC,
        headers={"Referer": _NSE_GOV_REF},
    )
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return None

    def _sort_key(item: dict) -> str:
        return _quarter_end_iso(item.get("date")) or ""

    dated = [r for r in rows if isinstance(r, dict) and safe_str(r.get("recordId"))]
    if not dated:
        return None
    dated.sort(key=_sort_key, reverse=True)
    latest = dated[0]
    rec_id = safe_str(latest.get("recordId"))
    as_of = _quarter_end_iso(latest.get("date"))
    detail = session.get(
        _CG_DETAIL_URL,
        params={"recId": rec_id},
        timeout=_TIMEOUT_SEC,
        headers={"Referer": _NSE_GOV_REF},
    )
    detail.raise_for_status()
    body = detail.json()
    cobod = body.get("cobod") if isinstance(body, dict) else None
    composition: list[dict] = []
    if isinstance(cobod, list) and cobod:
        data = cobod[0].get("data") if isinstance(cobod[0], dict) else None
        if isinstance(data, dict):
            raw = data.get("CompositionBOD") or []
            if isinstance(raw, list):
                composition = [r for r in raw if isinstance(r, dict)]
    seats = _parse_composition_bod(composition, as_of=as_of)
    if not seats:
        return None
    return {
        "ticker": ticker,
        "name": safe_str(latest.get("name")) or ticker,
        "seats": seats,
        "market": "NSE",
        "as_of": as_of,
        "source": "nse_corporate_governance",
        "record_id": rec_id,
        "xbrl": safe_str(latest.get("xbrl")) or None,
    }


def fetch_board_from_nse_governance(
    ticker: str,
    *,
    session: requests.Session | None = None,
) -> dict[str, Any] | None:
    """
    Return ``{ticker, name, seats, market, as_of, source}`` with DIN-backed seats.

    Tries Integrated Filing – Governance first, then CG master/detail JSON.
    """
    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        return None

    own = session is None
    sess = session or _nse_session()
    try:
        try:
            board = _fetch_integrated_governance(ticker_key, session=sess)
            if board and board.get("seats"):
                return board
        except Exception:
            board = None
        try:
            board = _fetch_cg_master_board(ticker_key, session=sess)
            if board and board.get("seats"):
                return board
        except Exception:
            return None
        return None
    finally:
        if own:
            sess.close()


__all__ = [
    "fetch_board_from_nse_governance",
    "parse_governance_ixbrl_html",
]
