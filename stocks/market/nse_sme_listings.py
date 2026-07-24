"""NSE Emerge / SME equity listings — internet CSV + SME.db sector/sub-sector.

Source: https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv
Market label stored in stocks_ai.db: ``NSE SME``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from stocks.core.config import DATA_DIR, STOCK_ANALYSIS_SQLITE_DIR
from stocks.core.text_utils import safe_str

NSE_SME_MARKET = "NSE SME"
_SME_CSV_URL = (
    "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv"
)
_CACHE_PATH = Path(DATA_DIR) / "nse_sme_equity.csv"
_CACHE_HOURS = 24
_TIMEOUT_SEC = 30
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# Equity series seen on Emerge (SM = SME, ST = trade-to-trade, SZ = special).
_SME_SERIES = frozenset({"SM", "ST", "SZ", "EQ", "BE"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _USER_AGENT,
            "Accept": "text/csv,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/market-data/securities-available-for-trading",
        }
    )
    return session


def _cache_fresh(path: Path = _CACHE_PATH, *, max_age_hours: float = _CACHE_HOURS) -> bool:
    if not path.is_file() or path.stat().st_size < 200:
        return False
    age_h = (datetime.now().timestamp() - path.stat().st_mtime) / 3600.0
    return age_h <= float(max_age_hours)


def _parse_sme_csv(text: str) -> pd.DataFrame:
    if not text or "SYMBOL" not in text.upper():
        return pd.DataFrame()
    try:
        df = pd.read_csv(StringIO(text))
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    cols = {str(c).strip().lower().replace(" ", "_"): c for c in df.columns}
    sym_col = cols.get("symbol")
    if sym_col is None:
        return pd.DataFrame()
    name_col = (
        cols.get("name_of_company")
        or cols.get("company_name")
        or cols.get("name")
    )
    series_col = cols.get("series") or cols.get("_series")

    rows: list[dict] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        ticker = safe_str(row.get(sym_col)).upper()
        if not ticker or ticker.startswith("*") or ticker == "SYMBOL" or ticker in seen:
            continue
        series = safe_str(row.get(series_col)).upper() if series_col else ""
        if series and series not in _SME_SERIES:
            continue
        name = safe_str(row.get(name_col)) if name_col else ticker
        seen.add(ticker)
        rows.append(
            {
                "ticker": ticker,
                "name": name or ticker,
                "market": NSE_SME_MARKET,
                "series": series,
                "sector": "",
                "industry": "",
                "sub_sector": "",
                "source_sector": "",
            }
        )
    return pd.DataFrame(rows)


def _fetch_sme_csv_text(*, force: bool = False) -> str:
    if not force and _cache_fresh():
        return _CACHE_PATH.read_text(encoding="utf-8", errors="replace")

    session = _session()
    try:
        session.get("https://www.nseindia.com", timeout=min(15, _TIMEOUT_SEC))
    except Exception:
        pass
    response = session.get(_SME_CSV_URL, timeout=_TIMEOUT_SEC)
    response.raise_for_status()
    text = response.text or ""
    if "SYMBOL" not in text.upper() or len(text) < 200:
        raise RuntimeError(f"NSE SME CSV empty/invalid ({len(text)} bytes)")
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(text, encoding="utf-8")
    return text


def _listings_from_sme_sqlite() -> pd.DataFrame:
    """Offline fallback from stock-analysis SME.db (nse_code + taxonomy)."""
    import sqlite3

    path = Path(STOCK_ANALYSIS_SQLITE_DIR) / "SME.db"
    if not path.is_file():
        return pd.DataFrame()
    query = """
        SELECT nse_code AS ticker, company_name AS name,
               sector, industry, subsector AS sub_sector
        FROM stocks
        WHERE nse_code IS NOT NULL AND TRIM(nse_code) != ''
    """
    with sqlite3.connect(path) as conn:
        df = pd.read_sql(query, conn)
    if df.empty:
        return pd.DataFrame()
    df["ticker"] = df["ticker"].map(lambda x: safe_str(x).upper())
    df["name"] = df["name"].fillna("").map(safe_str)
    df = df[df["ticker"] != ""].drop_duplicates("ticker")
    df["market"] = NSE_SME_MARKET
    df["series"] = ""
    for col in ("sector", "industry", "sub_sector"):
        df[col] = df[col].fillna("").map(safe_str)
    df["source_sector"] = df["sector"]
    # Prefer industry/sub_sector when sector blank (common in SME.db).
    blank_ind = df["industry"].eq("")
    df.loc[blank_ind, "industry"] = df.loc[blank_ind, "sub_sector"]
    blank_sub = df["sub_sector"].eq("")
    df.loc[blank_sub, "sub_sector"] = df.loc[blank_sub, "industry"]
    return df[
        [
            "ticker",
            "name",
            "market",
            "series",
            "sector",
            "industry",
            "sub_sector",
            "source_sector",
        ]
    ].reset_index(drop=True)


def fetch_nse_sme_listings(*, force: bool = False) -> pd.DataFrame:
    """Return NSE SME listings (internet CSV, else SME.db fallback)."""
    try:
        text = _fetch_sme_csv_text(force=force)
        df = _parse_sme_csv(text)
        if not df.empty:
            return df.reset_index(drop=True)
    except Exception:
        if _CACHE_PATH.is_file():
            df = _parse_sme_csv(
                _CACHE_PATH.read_text(encoding="utf-8", errors="replace")
            )
            if not df.empty:
                return df.reset_index(drop=True)
    return _listings_from_sme_sqlite()


def merge_nse_sme_into_stocks(
    stocks: pd.DataFrame,
    *,
    force_fetch: bool = False,
) -> pd.DataFrame:
    """
    Upsert ``NSE SME`` rows into the India stocks universe.

    Symbols on the NSE Emerge CSV are stored as market=``NSE SME`` (and removed
    from mainboard ``NSE`` when the HF dataset had them mis-tagged).
    Classification (sector / industry / sub_sector) is filled later by
    ``enrich_stocks_classification`` from SME.db when blank.
    """
    sme = fetch_nse_sme_listings(force=force_fetch)
    if sme.empty:
        return stocks if stocks is not None else pd.DataFrame()

    base = stocks.copy() if stocks is not None and not stocks.empty else pd.DataFrame()
    sme_tickers = set(sme["ticker"].astype(str).str.upper())

    # Drop prior NSE SME rows; re-add from the live/cached Emerge list.
    if not base.empty and "market" in base.columns:
        base = base[base["market"].astype(str) != NSE_SME_MARKET].copy()

    # HF india.csv often tags Emerge names as NSE — move them to NSE SME.
    relocated = pd.DataFrame()
    if not base.empty and "market" in base.columns and sme_tickers:
        is_nse = base["market"].astype(str).str.upper() == "NSE"
        is_sme = base["ticker"].astype(str).str.upper().isin(sme_tickers)
        relocated = base.loc[is_nse & is_sme].copy()
        base = base.loc[~(is_nse & is_sme)].copy()

    for col in (
        "ticker",
        "name",
        "market",
        "sector",
        "industry",
        "sub_sector",
        "source_sector",
    ):
        if col not in sme.columns:
            sme[col] = ""
        if not base.empty and col not in base.columns:
            base[col] = ""
        if not relocated.empty and col not in relocated.columns:
            relocated[col] = ""

    # Prefer richer name/sector labels from the relocated HF row when present.
    if not relocated.empty:
        look = relocated.drop_duplicates("ticker").set_index(
            relocated["ticker"].astype(str).str.upper()
        )
        for idx, row in sme.iterrows():
            ticker = safe_str(row.get("ticker")).upper()
            if ticker not in look.index:
                continue
            prev = look.loc[ticker]
            if isinstance(prev, pd.DataFrame):
                prev = prev.iloc[0]
            for col in ("name", "sector", "industry", "sub_sector", "source_sector"):
                cur = safe_str(sme.at[idx, col])
                alt = safe_str(prev.get(col))
                if col == "name":
                    if alt:
                        sme.at[idx, col] = alt
                elif not cur and alt:
                    sme.at[idx, col] = alt

    if sme.empty:
        return base.reset_index(drop=True) if not base.empty else sme

    cols = [c for c in base.columns] if not base.empty else list(sme.columns)
    for c in cols:
        if c not in sme.columns:
            sme[c] = ""
    sme = sme[cols] if cols else sme
    out = pd.concat([base, sme], ignore_index=True) if not base.empty else sme
    return out.drop_duplicates(subset=["ticker", "market"], keep="last").reset_index(
        drop=True
    )


def stocks_need_nse_sme(stocks: pd.DataFrame, *, min_count: int = 50) -> bool:
    """True when cached universe is missing a meaningful NSE SME slice."""
    if stocks is None or stocks.empty or "market" not in stocks.columns:
        return True
    n = int((stocks["market"].astype(str) == NSE_SME_MARKET).sum())
    return n < int(min_count)
