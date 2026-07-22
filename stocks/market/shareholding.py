"""Quarterly shareholding — SQLite store + NSE XBRL (screener.in fallback)."""

from __future__ import annotations

import csv
import re
from html import unescape
from pathlib import Path

import pandas as pd
import requests

from stocks.core.config import DATA_DIR
from stocks.core.database import (
    init_db,
    load_shareholding_qtr,
    save_shareholding_qtr,
)
from stocks.core.text_utils import safe_str
from stocks.shared.links import screener_url

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_NSE_HOME = "https://www.nseindia.com/"
_NSE_SHP_URL = (
    "https://www.nseindia.com/api/corporate-share-holdings-master"
)
_NSE_TIMEOUT_SEC = 30
_NSE_MAX_QUARTERS = 4

# XBRL category members → FII / DII / promoter / public.
_XBRL_FII = "InstitutionsForeignMember"
_XBRL_DII = "InstitutionsDomesticMember"
_XBRL_PROMOTER = "ShareholdingOfPromoterAndPromoterGroupMember"
_XBRL_PUBLIC = "PublicShareholdingMember"

SHAREHOLDING_SEED_CSV = DATA_DIR / "shareholding_seed.csv"

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


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_pct(text: str) -> float | None:
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%?", str(text).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _nse_quarter_end(date_str: str | None) -> str | None:
    """NSE '30-JUN-2026' → '2026-06-30'."""
    raw = safe_str(date_str).upper().replace(" ", "")
    if not raw:
        return None
    m = re.match(r"^(\d{1,2})-([A-Z]{3})-(\d{4})$", raw)
    if not m:
        return None
    day, mon, year = m.group(1), m.group(2), m.group(3)
    month = _MONTH_NUM.get(mon)
    if not month:
        return None
    return f"{year}-{month}-{int(day):02d}"


def _nse_session() -> requests.Session:
    session = requests.Session()
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json,text/html,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": _NSE_HOME,
    }
    session.get(_NSE_HOME, headers=headers, timeout=20)
    session.headers.update(headers)
    return session


def _parse_xbrl_shareholding_pcts(xml_text: str) -> dict[str, float]:
    """Map XBRL CategoryOfShareholders members → ownership %."""
    ctx: dict[str, str] = {}
    for m in re.finditer(
        r'<xbrli:context id="([^"]+)">.*?'
        r'CategoryOfShareholdersAxis">in-bse-shp:([^<]+)</xbrldi:explicitMember>',
        xml_text,
        flags=re.S,
    ):
        ctx[m.group(1)] = m.group(2)

    pcts: dict[str, float] = {}
    for m in re.finditer(
        r"<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares "
        r'contextRef="([^"]+)"[^>]*>([0-9.]+)</',
        xml_text,
    ):
        cat = ctx.get(m.group(1))
        if not cat:
            continue
        # NSE XBRL stores ownership as a fraction of 1 (0.2709 → 27.09%).
        pcts[cat] = round(float(m.group(2)) * 100.0, 4)
    return pcts


def _pct_from_master(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() in ("", "-", "null", "None"):
        return None
    try:
        return round(float(str(raw).replace(",", "")), 4)
    except ValueError:
        return None


def fetch_nse_shareholding(
    ticker: str,
    *,
    session: requests.Session | None = None,
    max_quarters: int = _NSE_MAX_QUARTERS,
) -> list[dict]:
    """
    Pull latest shareholding quarters from NSE master API + XBRL.

    FII = InstitutionsForeignMember, DII = InstitutionsDomesticMember.
    Falls back to master promoter/public when XBRL is missing.
    """
    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        return []

    own_session = session is None
    sess = session or _nse_session()
    try:
        resp = sess.get(
            _NSE_SHP_URL,
            params={"index": "equities", "symbol": ticker_key},
            timeout=_NSE_TIMEOUT_SEC,
            headers={
                "Referer": (
                    "https://www.nseindia.com/companies-listing/"
                    "corporate-filings-shareholding-pattern"
                ),
            },
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        if own_session:
            sess.close()
        return []

    if not isinstance(payload, list) or not payload:
        if own_session:
            sess.close()
        return []

    # Newest first (API usually returns newest-first; sort defensively).
    dated: list[tuple[str, dict]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        q = _nse_quarter_end(item.get("date"))
        if q:
            dated.append((q, item))
    dated.sort(key=lambda x: x[0], reverse=True)

    out: list[dict] = []
    seen_q: set[str] = set()
    try:
        for quarter_end, item in dated:
            if quarter_end in seen_q:
                continue
            seen_q.add(quarter_end)
            if len(out) >= max(1, int(max_quarters)):
                break

            promoter = _pct_from_master(item.get("pr_and_prgrp"))
            public = _pct_from_master(item.get("public_val"))
            fii = None
            dii = None
            xbrl_url = safe_str(item.get("xbrl"))
            if xbrl_url.startswith("http"):
                try:
                    xr = sess.get(xbrl_url, timeout=_NSE_TIMEOUT_SEC)
                    xr.raise_for_status()
                    pcts = _parse_xbrl_shareholding_pcts(xr.text)
                    fii = pcts.get(_XBRL_FII)
                    dii = pcts.get(_XBRL_DII)
                    promoter = pcts.get(_XBRL_PROMOTER, promoter)
                    public = pcts.get(_XBRL_PUBLIC, public)
                except Exception:
                    pass

            disclosure = None
            for key in ("submissionDate", "broadcastDate"):
                raw = safe_str(item.get(key))
                if not raw:
                    continue
                # '15-JUL-2026' or '15-JUL-2026 18:52:47'
                part = raw.split()[0]
                iso = _nse_quarter_end(part)
                if iso:
                    disclosure = iso
                    break

            out.append(
                {
                    "ticker": ticker_key,
                    "quarter_end": quarter_end,
                    "disclosure_date": disclosure,
                    "promoter_pct": promoter,
                    "fii_pct": fii,
                    "dii_pct": dii,
                    "public_pct": public,
                    "source": "nse",
                }
            )
    finally:
        if own_session:
            sess.close()

    return out


def import_shareholding_seed_csv(path: Path | None = None) -> int:
    """
    Load optional CSV into shareholding_qtr.

    Columns: ticker,quarter_end,promoter_pct,fii_pct,dii_pct,public_pct[,disclosure_date]
    """
    csv_path = path or SHAREHOLDING_SEED_CSV
    if not csv_path.is_file():
        return 0
    rows: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            ticker = safe_str(raw.get("ticker") or raw.get("symbol")).upper()
            quarter = safe_str(raw.get("quarter_end"))
            if not ticker or not quarter:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "quarter_end": quarter,
                    "disclosure_date": safe_str(raw.get("disclosure_date")) or None,
                    "promoter_pct": _parse_pct(str(raw.get("promoter_pct") or "")),
                    "fii_pct": _parse_pct(str(raw.get("fii_pct") or "")),
                    "dii_pct": _parse_pct(str(raw.get("dii_pct") or "")),
                    "public_pct": _parse_pct(str(raw.get("public_pct") or "")),
                    "source": "seed_csv",
                }
            )
    if rows:
        init_db()
        save_shareholding_qtr(rows)
    return len(rows)


def fetch_screener_shareholding(
    ticker: str,
    market: str | None = None,
) -> list[dict]:
    """Best-effort screener.in shareholding table parse (latest quarters)."""
    url = screener_url(ticker, market)
    if not url or url.rstrip("/").endswith("screener.in"):
        return []
    try:
        resp = requests.get(url, timeout=12, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return []

    section = re.search(
        r"(Shareholding|shareholding)([\s\S]{0,25000}?)</table>",
        html,
        flags=re.I,
    )
    if not section:
        return []
    block = section.group(0)
    headers = re.findall(r"<th[^>]*>([\s\S]*?)</th>", block, flags=re.I)
    quarters: list[str] = []
    for h in headers:
        label = _strip_html(h)
        m = re.search(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})",
            label,
            flags=re.I,
        )
        if not m:
            continue
        mon = m.group(1)[:3].title()
        year = int(m.group(2))
        month = {
            "Jan": "01",
            "Feb": "02",
            "Mar": "03",
            "Apr": "04",
            "May": "05",
            "Jun": "06",
            "Jul": "07",
            "Aug": "08",
            "Sep": "09",
            "Oct": "10",
            "Nov": "11",
            "Dec": "12",
        }.get(mon)
        if month:
            day = {"02": "28", "03": "31", "06": "30", "09": "30", "12": "31"}.get(
                month, "30"
            )
            quarters.append(f"{year}-{month}-{day}")

    if len(quarters) < 2:
        return []

    def _row_values(label: str) -> list[float | None]:
        pat = rf"<tr[^>]*>\s*<td[^>]*>\s*{label}[\s\S]*?</tr>"
        m = re.search(pat, block, flags=re.I)
        if not m:
            return []
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", m.group(0), flags=re.I)
        vals: list[float | None] = []
        for cell in cells[1 : 1 + len(quarters)]:
            vals.append(_parse_pct(_strip_html(cell)))
        return vals

    promoters = _row_values("Promoters")
    fiis = _row_values("FIIs") or _row_values("FII")
    diis = _row_values("DIIs") or _row_values("DII")
    public = _row_values("Public")

    if not promoters and not fiis and not diis:
        return []

    ticker_key = safe_str(ticker).upper()
    out: list[dict] = []
    for i, q in enumerate(quarters):
        out.append(
            {
                "ticker": ticker_key,
                "quarter_end": q,
                "promoter_pct": promoters[i] if i < len(promoters) else None,
                "fii_pct": fiis[i] if i < len(fiis) else None,
                "dii_pct": diis[i] if i < len(diis) else None,
                "public_pct": public[i] if i < len(public) else None,
                "source": "screener",
            }
        )
    return out


def _inst_pct(row: pd.Series) -> float:
    fii = row.get("fii_pct")
    dii = row.get("dii_pct")
    fii_f = float(fii) if fii is not None and not pd.isna(fii) else 0.0
    dii_f = float(dii) if dii is not None and not pd.isna(dii) else 0.0
    return fii_f + dii_f


def institutional_entry_signal(
    ticker: str,
    *,
    min_delta: float,
    as_of_quarter: str | None = None,
) -> dict | None:
    """DII+FII QoQ jump ≥ min_delta. first_time when prior inst% ≈ 0."""
    df = load_shareholding_qtr([ticker])
    if df.empty:
        return None
    work = df.copy()
    work["quarter_end"] = work["quarter_end"].astype(str)
    work = work.sort_values("quarter_end", ascending=False)
    if as_of_quarter:
        work = work[work["quarter_end"] <= str(as_of_quarter)]
    if work.empty:
        return None
    cur = work.iloc[0]
    prior = work.iloc[1] if len(work) > 1 else None
    now = _inst_pct(cur)
    prev = _inst_pct(prior) if prior is not None else 0.0
    delta = now - prev
    if delta < min_delta:
        return None
    return {
        "quarter_end": str(cur["quarter_end"]),
        "institutional_pct_now": round(now, 2),
        "institutional_pct_prior": round(prev, 2),
        "institutional_pct_delta": round(delta, 2),
        "first_time_entry": prev <= 0.05,
        "promoter_pct": cur.get("promoter_pct"),
        "fii_pct": cur.get("fii_pct"),
        "dii_pct": cur.get("dii_pct"),
    }


def shareholding_deltas(ticker: str) -> dict:
    """Latest vs prior promoter and DII+FII percentage-point changes (any sign)."""
    df = load_shareholding_qtr([ticker])
    empty = {
        "promoter_pct_delta": None,
        "institutional_pct_delta": None,
        "quarter_end": None,
        "promoter_pct": None,
    }
    if df.empty:
        return empty
    work = df.copy()
    work["quarter_end"] = work["quarter_end"].astype(str)
    work = work.sort_values("quarter_end", ascending=False)
    cur = work.iloc[0]
    prior = work.iloc[1] if len(work) > 1 else None
    prom_now = cur.get("promoter_pct")
    prom_prev = prior.get("promoter_pct") if prior is not None else None
    prom_delta = None
    if (
        prom_now is not None
        and not pd.isna(prom_now)
        and prom_prev is not None
        and not pd.isna(prom_prev)
    ):
        prom_delta = round(float(prom_now) - float(prom_prev), 2)
    inst_now = _inst_pct(cur)
    inst_prev = _inst_pct(prior) if prior is not None else 0.0
    return {
        "promoter_pct_delta": prom_delta,
        "institutional_pct_delta": round(inst_now - inst_prev, 2),
        "quarter_end": str(cur["quarter_end"]),
        "promoter_pct": prom_now,
    }


def ensure_shareholding_for_ticker(
    ticker: str,
    market: str | None = None,
    *,
    fetch_nse: bool = True,
    fetch_screener: bool = False,
) -> None:
    existing = load_shareholding_qtr([ticker])
    if len(existing) >= 2:
        return
    rows: list[dict] = []
    if fetch_nse:
        rows = fetch_nse_shareholding(ticker)
    if len(rows) < 2 and fetch_screener:
        rows = fetch_screener_shareholding(ticker, market) or rows
    if rows:
        save_shareholding_qtr(rows)


__all__ = [
    "SHAREHOLDING_SEED_CSV",
    "ensure_shareholding_for_ticker",
    "fetch_nse_shareholding",
    "fetch_screener_shareholding",
    "import_shareholding_seed_csv",
    "institutional_entry_signal",
    "shareholding_deltas",
]
