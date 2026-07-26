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
    get_connection,
    init_db,
    load_shareholding_holder_scan_tickers,
    load_shareholding_holders,
    load_shareholding_qtr,
    save_shareholding_holders,
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

# Public *individual* name disclosures in SHP XBRL (not funds / institutions).
_PUBLIC_INDIVIDUAL_AXIS_MARKERS = (
    "ResidentIndividualShareholders",
    "NonResidentIndians",
)
_PROMOTER_HOLDER_AXIS_MARKERS = (
    "IndividualsOrHUF",
    "OthersIndianShareholders",
    "OtherForeignShareholders",
    "DetailsSharesHeldByIndividualsOrHUF",
)

_CATEGORY_LABELS = {
    "ResidentIndividualShareholders": "Individual",
    "NonResidentIndians": "NRI",
}

# Reject entity-looking names that sometimes leak into individual rows.
_ENTITY_NAME_RE = re.compile(
    r"\b("
    r"ltd|limited|llp|llc|inc|corp|corporation|pvt|private|fund|funds|"
    r"trust|trustee|bank|insurance|mutual|etf|capital|holdings|investment|"
    r"investments|partners|partner|plc|sa\b|nv\b|gmbh|pte|company|co\."
    r")\b",
    flags=re.I,
)

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


def _xbrl_pct_to_percent(raw: str) -> float | None:
    try:
        val = float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if val != val or val < 0:
        return None
    # NSE stores most ownership facts as a fraction of 1.
    if val <= 1.0001:
        val *= 100.0
    if val > 100:
        return None
    return round(val, 4)


def _holder_category_from_context(ctx_id: str, ctx_body: str) -> str | None:
    blob = f"{ctx_id} {ctx_body}"
    for key, label in _CATEGORY_LABELS.items():
        if key.lower() in blob.lower():
            return label
    for key in _PUBLIC_INDIVIDUAL_AXIS_MARKERS:
        if key.lower() in blob.lower():
            return key
    return None


def _looks_like_person_name(name: str) -> bool:
    raw = safe_str(name)
    if not raw or len(raw) < 3:
        return False
    if _ENTITY_NAME_RE.search(raw):
        return False
    # Need at least one letter; reject pure codes.
    if not re.search(r"[A-Za-z]", raw):
        return False
    return True


def _is_public_individual_context(ctx_id: str, ctx_body: str) -> bool:
    blob = f"{ctx_id} {ctx_body}".lower()
    if any(m.lower() in blob for m in _PROMOTER_HOLDER_AXIS_MARKERS):
        return False
    return any(m.lower() in blob for m in _PUBLIC_INDIVIDUAL_AXIS_MARKERS)


def parse_xbrl_public_gt1_holders(
    xml_text: str,
    *,
    min_pct: float = 1.0,
) -> list[dict]:
    """
    Named *individual* public shareholders at/above ``min_pct`` from SHP XBRL.

    Keeps resident / NRI individual disclosures only — skips promoters, funds,
    FPIs, insurers, and body corporates.
    """
    if not xml_text:
        return []
    ctx_bodies: dict[str, str] = {}
    for m in re.finditer(
        r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>',
        xml_text,
        flags=re.S,
    ):
        ctx_bodies[m.group(1)] = m.group(2)

    pct_by_ctx: dict[str, float] = {}
    for m in re.finditer(
        r"<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares "
        r'contextRef="([^"]+)"[^>]*>([^<]+)</',
        xml_text,
    ):
        pct = _xbrl_pct_to_percent(m.group(2))
        if pct is not None:
            pct_by_ctx[m.group(1)] = pct

    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(
        r"<in-bse-shp:NameOfTheShareholder "
        r'contextRef="([^"]+)"[^>]*>([^<]+)</',
        xml_text,
    ):
        ctx = m.group(1)
        name = unescape(safe_str(m.group(2)))
        name = re.sub(r"\s+", " ", name).strip(" .")
        if not name or name in {"******", "-", "NA", "N/A"}:
            continue
        body = ctx_bodies.get(ctx, "")
        if not _is_public_individual_context(ctx, body):
            continue
        if not _looks_like_person_name(name):
            continue
        base = ctx[2:] if ctx.startswith("D_") else ctx
        pct = pct_by_ctx.get(base)
        if pct is None:
            pct = pct_by_ctx.get(ctx)
        if pct is None or pct < float(min_pct):
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "name": name,
                "pct": round(pct, 2),
                "category": _holder_category_from_context(ctx, body) or "Individual",
            }
        )
    out.sort(key=lambda h: (-float(h["pct"]), h["name"].casefold()))
    return out


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
    holders_saved = False
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
                    xml_text = xr.text
                    pcts = _parse_xbrl_shareholding_pcts(xml_text)
                    fii = pcts.get(_XBRL_FII)
                    dii = pcts.get(_XBRL_DII)
                    promoter = pcts.get(_XBRL_PROMOTER, promoter)
                    public = pcts.get(_XBRL_PUBLIC, public)
                    if not holders_saved:
                        holders = parse_xbrl_public_gt1_holders(xml_text)
                        save_shareholding_holders(ticker_key, quarter_end, holders)
                        holders_saved = True
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


def _valid_promoter_pct(val) -> float | None:
    """Reject XBRL/share-count misparses (must be a 0–100 ownership %)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        pct = float(val)
    except (TypeError, ValueError):
        return None
    if pct != pct or pct < 0 or pct > 100:
        return None
    return round(pct, 2)


def shareholding_deltas(ticker: str) -> dict:
    """Latest vs prior promoter and DII+FII percentage-point changes (any sign)."""
    by = promoter_holdings_for_tickers([ticker])
    hit = by.get(safe_str(ticker).upper()) or {}
    return {
        "promoter_pct_delta": hit.get("promoter_pct_delta"),
        "promoter_move": hit.get("promoter_move"),
        "promoter_history": hit.get("promoter_history"),
        "institutional_pct_delta": hit.get("institutional_pct_delta"),
        "quarter_end": hit.get("quarter_end"),
        "promoter_pct": hit.get("promoter_pct"),
    }


def promoter_holdings_for_tickers(tickers: list[str] | None = None) -> dict[str, dict]:
    """
    Batch latest promoter % + QoQ Δ + multi-quarter move per ticker.

    ``promoter_pct_delta`` = latest − prior quarter (pp).
    ``promoter_move`` = latest − oldest among last ≤4 valid quarters (pp).
    ``promoter_history`` = compact ``q:pct`` trail newest-first for tooltips.
    """
    keys = sorted(
        {safe_str(t).upper() for t in (tickers or []) if safe_str(t)}
    )
    if not keys:
        return {}
    df = load_shareholding_qtr(keys)
    if df is None or df.empty:
        return {}
    work = df.copy()
    work["ticker"] = work["ticker"].astype(str).str.upper()
    work["quarter_end"] = work["quarter_end"].astype(str)
    work = work.sort_values(["ticker", "quarter_end"], ascending=[True, False])

    out: dict[str, dict] = {}
    for ticker, grp in work.groupby("ticker", sort=False):
        series: list[tuple[str, float]] = []
        for _, row in grp.iterrows():
            pct = _valid_promoter_pct(row.get("promoter_pct"))
            if pct is None:
                continue
            q = str(row.get("quarter_end") or "")
            if not q:
                continue
            series.append((q, pct))
            if len(series) >= 4:
                break
        if not series:
            continue
        prom_f = series[0][1]
        prom_delta = None
        if len(series) >= 2:
            prom_delta = round(series[0][1] - series[1][1], 2)
        prom_move = None
        if len(series) >= 2:
            prom_move = round(series[0][1] - series[-1][1], 2)
        history = " → ".join(
            f"{q[2:7] if len(q) >= 7 else q}:{pct:g}%" for q, pct in reversed(series)
        )
        # Inst delta still uses raw rows (may lack promoter but have FII/DII).
        cur = grp.iloc[0]
        prior = grp.iloc[1] if len(grp) > 1 else None
        inst_now = _inst_pct(cur)
        inst_prev = _inst_pct(prior) if prior is not None else 0.0
        out[str(ticker)] = {
            "promoter_pct": prom_f,
            "promoter_pct_delta": prom_delta,
            "promoter_move": prom_move,
            "promoter_history": history,
            "institutional_pct_delta": round(inst_now - inst_prev, 2),
            "quarter_end": series[0][0],
        }
    return out


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


def public_holders_for_tickers(
    tickers: list[str] | None = None,
    *,
    min_pct: float = 1.0,
) -> dict[str, list[dict]]:
    """Cached named *individual* public holders (≥ ``min_pct``) keyed by ticker."""
    keys = sorted({safe_str(t).upper() for t in (tickers or []) if safe_str(t)})
    if not keys:
        return {}
    raw = load_shareholding_holders(keys, min_pct=min_pct)
    out: dict[str, list[dict]] = {}
    for ticker, holders in raw.items():
        people = []
        for h in holders or []:
            cat = safe_str(h.get("category")).lower()
            name = safe_str(h.get("name"))
            if cat not in {"individual", "nri"}:
                continue
            if not _looks_like_person_name(name):
                continue
            people.append(h)
        if people:
            out[ticker] = people
    return out


def individual_holders_index(
    *,
    min_pct: float = 1.0,
    min_companies: int = 1,
    limit: int = 400,
) -> list[dict]:
    """
    Cross-company index of public individual / NRI holders (≥ ``min_pct``).

    People like Manohar Devabhaktuni appear once with all their >1% stakes.
    """
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT h.ticker, h.holder_name, h.holder_pct, h.category, h.quarter_end
            FROM shareholding_holders h
            INNER JOIN (
                SELECT ticker, MAX(quarter_end) AS quarter_end
                FROM shareholding_holders
                GROUP BY ticker
            ) latest
              ON latest.ticker = h.ticker
             AND latest.quarter_end = h.quarter_end
            WHERE h.holder_pct >= ?
              AND lower(coalesce(h.category, '')) IN ('individual', 'nri')
            ORDER BY h.holder_name COLLATE NOCASE, h.holder_pct DESC
            """,
            (float(min_pct),),
        ).fetchall()

    by_key: dict[str, dict] = {}
    for row in rows:
        name = safe_str(row["holder_name"])
        if not _looks_like_person_name(name):
            continue
        key = re.sub(r"\s+", " ", name).strip().casefold()
        if not key:
            continue
        ticker = safe_str(row["ticker"]).upper()
        if not ticker:
            continue
        try:
            pct = float(row["holder_pct"])
        except (TypeError, ValueError):
            continue
        bucket = by_key.get(key)
        if bucket is None:
            bucket = {
                "name": re.sub(r"\s+", " ", name).strip(),
                "name_key": key,
                "holdings": [],
            }
            by_key[key] = bucket
        # Prefer display name with better casing if longer/titled.
        if len(name) > len(safe_str(bucket.get("name"))):
            bucket["name"] = re.sub(r"\s+", " ", name).strip()
        holdings = bucket["holdings"]
        if any(safe_str(h.get("ticker")).upper() == ticker for h in holdings):
            continue
        holdings.append(
            {
                "ticker": ticker,
                "pct": round(pct, 2),
                "category": safe_str(row["category"]) or "Individual",
                "quarter_end": safe_str(row["quarter_end"]) or None,
            }
        )

    out: list[dict] = []
    for bucket in by_key.values():
        holdings = sorted(
            bucket["holdings"],
            key=lambda h: (-float(h.get("pct") or 0), safe_str(h.get("ticker"))),
        )
        if len(holdings) < int(min_companies):
            continue
        out.append(
            {
                "name": bucket["name"],
                "name_key": bucket["name_key"],
                "company_count": len(holdings),
                "holdings": holdings,
            }
        )
    out.sort(
        key=lambda p: (-int(p.get("company_count") or 0), safe_str(p.get("name")).casefold())
    )
    if limit > 0:
        out = out[: int(limit)]
    return out


SHAREHOLDING_HOLDERS_CSV = DATA_DIR / "shareholding_holders.csv"
SHAREHOLDING_HOLDER_SCAN_CSV = DATA_DIR / "shareholding_holder_scan.csv"
SHAREHOLDING_QTR_CSV = DATA_DIR / "shareholding_qtr_export.csv"


def export_scanned_shareholding_data(
    *,
    holders_path: Path | None = None,
    scan_path: Path | None = None,
    qtr_path: Path | None = None,
) -> dict[str, int]:
    """
    Dump scanned SHP data from SQLite to CSV under ``data/``.

    Returns row counts written per file.
    """
    init_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    holders_out = holders_path or SHAREHOLDING_HOLDERS_CSV
    scan_out = scan_path or SHAREHOLDING_HOLDER_SCAN_CSV
    qtr_out = qtr_path or SHAREHOLDING_QTR_CSV
    counts: dict[str, int] = {"holders": 0, "scans": 0, "quarters": 0}

    with get_connection() as conn:
        # Checkpoint WAL so the on-disk DB file is fully caught up.
        try:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception:
            pass

        holders = conn.execute(
            """
            SELECT ticker, quarter_end, holder_name, holder_pct, category, fetched_at
            FROM shareholding_holders
            ORDER BY ticker, holder_pct DESC, holder_name COLLATE NOCASE
            """
        ).fetchall()
        scans = conn.execute(
            """
            SELECT ticker, quarter_end, fetched_at
            FROM shareholding_holder_scan
            ORDER BY ticker
            """
        ).fetchall()
        qtrs = conn.execute(
            """
            SELECT ticker, quarter_end, disclosure_date,
                   promoter_pct, fii_pct, dii_pct, public_pct, source, fetched_at
            FROM shareholding_qtr
            ORDER BY ticker, quarter_end DESC
            """
        ).fetchall()

    def _write(path: Path, rows: list, fields: list[str]) -> int:
        import csv

        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for row in rows:
                w.writerow({k: row[k] for k in fields})
        return len(rows)

    counts["holders"] = _write(
        holders_out,
        holders,
        ["ticker", "quarter_end", "holder_name", "holder_pct", "category", "fetched_at"],
    )
    counts["scans"] = _write(
        scan_out,
        scans,
        ["ticker", "quarter_end", "fetched_at"],
    )
    counts["quarters"] = _write(
        qtr_out,
        qtrs,
        [
            "ticker",
            "quarter_end",
            "disclosure_date",
            "promoter_pct",
            "fii_pct",
            "dii_pct",
            "public_pct",
            "source",
            "fetched_at",
        ],
    )
    return counts


def hydrate_public_holders_for_tickers(
    tickers: list[str],
    *,
    max_fetch: int = 20,
    min_pct: float = 1.0,
    force: bool = False,
) -> int:
    """
    Fetch NSE SHP XBRL for tickers not yet scanned for named public holders.

    Returns the number of tickers freshly scanned (0 holders still counts).
    Set ``force=True`` to re-parse even if already scanned.
    """
    keys = sorted({safe_str(t).upper() for t in tickers if safe_str(t)})
    if not keys or max_fetch <= 0:
        return 0
    if force:
        missing = keys[: int(max_fetch)]
    else:
        already = load_shareholding_holder_scan_tickers(keys)
        missing = [t for t in keys if t not in already][: int(max_fetch)]
    if not missing:
        return 0
    session = _nse_session()
    n = 0
    try:
        for ticker in missing:
            rows = fetch_nse_shareholding(
                ticker, session=session, max_quarters=1
            )
            if rows:
                save_shareholding_qtr(rows)
            # fetch_nse_shareholding saves holders when XBRL parses; if XBRL
            # failed, still mark scan so we don't hammer NSE every map load.
            scanned = load_shareholding_holder_scan_tickers([ticker])
            if ticker not in scanned:
                q = safe_str(rows[0].get("quarter_end")) if rows else ""
                save_shareholding_holders(ticker, q or "unknown", [])
            n += 1
    finally:
        session.close()
    # Touch min_pct so callers can pass it without unused-arg lint noise.
    _ = min_pct
    return n


__all__ = [
    "SHAREHOLDING_SEED_CSV",
    "ensure_shareholding_for_ticker",
    "fetch_nse_shareholding",
    "fetch_screener_shareholding",
    "export_scanned_shareholding_data",
    "hydrate_public_holders_for_tickers",
    "import_shareholding_seed_csv",
    "individual_holders_index",
    "institutional_entry_signal",
    "parse_xbrl_public_gt1_holders",
    "promoter_holdings_for_tickers",
    "public_holders_for_tickers",
    "shareholding_deltas",
    "SHAREHOLDING_HOLDERS_CSV",
    "SHAREHOLDING_HOLDER_SCAN_CSV",
    "SHAREHOLDING_QTR_CSV",
]
