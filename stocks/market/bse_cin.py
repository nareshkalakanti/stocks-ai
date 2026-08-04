"""Resolve listed-company CIN via BSE CorpInfo (needs BSE scrip code)."""

from __future__ import annotations

import csv
import re
import threading
import time
from pathlib import Path

import requests

from stocks.core.config import DATA_DIR, SCREENER_REQUEST_DELAY
from stocks.core.text_utils import safe_str

_BSE_CODES_PATH = DATA_DIR / "bse_codes.csv"
_CIN_RE = re.compile(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")
_BSE_CODE_RE = re.compile(r"BSE:\s*(\d{5,6})", re.I)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_LOCK = threading.Lock()
_LAST_BSE_AT = 0.0
_LAST_SCREENER_AT = 0.0
_BSE_DELAY = 0.35


def _throttle(kind: str) -> None:
    global _LAST_BSE_AT, _LAST_SCREENER_AT
    delay = _BSE_DELAY if kind == "bse" else max(0.0, float(SCREENER_REQUEST_DELAY))
    with _LOCK:
        last = _LAST_BSE_AT if kind == "bse" else _LAST_SCREENER_AT
        now = time.monotonic()
        wait = delay - (now - last)
        if wait > 0:
            time.sleep(wait)
        stamp = time.monotonic()
        if kind == "bse":
            _LAST_BSE_AT = stamp
        else:
            _LAST_SCREENER_AT = stamp


def load_bse_code_map(path: Path | None = None) -> dict[str, str]:
    csv_path = path or _BSE_CODES_PATH
    if not csv_path.exists():
        return {}
    out: dict[str, str] = {}
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            t = safe_str(row.get("ticker")).upper()
            code = safe_str(row.get("bse_code")).strip()
            if t and code.isdigit():
                out[t] = code
    return out


def save_bse_code_map(code_map: dict[str, str], path: Path | None = None) -> None:
    csv_path = path or _BSE_CODES_PATH
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        ({"ticker": t, "bse_code": c} for t, c in code_map.items() if t and c),
        key=lambda r: r["ticker"],
    )
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ticker", "bse_code"])
        writer.writeheader()
        writer.writerows(rows)


def fetch_bse_code_from_screener(ticker: str) -> str | None:
    """Parse ``BSE: 500209`` from the Screener company page."""
    key = safe_str(ticker).upper()
    if not key:
        return None
    _throttle("screener")
    url = f"https://www.screener.in/company/{key}/"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
            timeout=30,
        )
        if not resp.ok:
            return None
        m = _BSE_CODE_RE.search(resp.text)
        return m.group(1) if m else None
    except Exception:
        return None


def fetch_cin_from_bse(bse_code: str) -> str | None:
    """Return CIN from BSE ``CorpInfo`` for a numeric scrip code."""
    code = safe_str(bse_code).strip()
    if not code.isdigit():
        return None
    _throttle("bse")
    url = "https://api.bseindia.com/BseIndiaAPI/api/CorpInfo/w"
    try:
        resp = requests.get(
            url,
            params={"scripcode": code},
            headers={
                "User-Agent": _USER_AGENT,
                "Referer": "https://www.bseindia.com/",
                "Accept": "application/json, text/plain, */*",
            },
            timeout=30,
        )
        if not resp.ok:
            return None
        payload = resp.json()
        rows = payload.get("Table3") or []
        if not rows:
            return None
        cin = safe_str(rows[0].get("fld_cin")).upper()
        return cin if _CIN_RE.match(cin) else None
    except Exception:
        return None


def resolve_bse_code(
    ticker: str,
    *,
    code_map: dict[str, str] | None = None,
    fetch_missing: bool = True,
) -> str | None:
    key = safe_str(ticker).upper()
    maps = code_map if code_map is not None else load_bse_code_map()
    code = maps.get(key)
    if code:
        return code
    if not fetch_missing:
        return None
    code = fetch_bse_code_from_screener(key)
    if code and code_map is not None:
        code_map[key] = code
    return code


def resolve_cin_for_ticker(
    ticker: str,
    *,
    code_map: dict[str, str] | None = None,
    fetch_missing_code: bool = True,
) -> dict[str, str | None]:
    """Return ``{ticker, bse_code, cin}`` for one symbol."""
    key = safe_str(ticker).upper()
    maps = code_map if code_map is not None else load_bse_code_map()
    code = resolve_bse_code(key, code_map=maps, fetch_missing=fetch_missing_code)
    cin = fetch_cin_from_bse(code) if code else None
    return {"ticker": key, "bse_code": code, "cin": cin}
