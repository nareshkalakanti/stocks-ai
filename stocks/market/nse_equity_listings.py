"""NSE mainboard equity listings — official EQUITY_L.csv.

Source: https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
Market label stored in stocks_ai.db: ``NSE``.
"""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from stocks.core.config import DATA_DIR
from stocks.core.text_utils import safe_str

NSE_MARKET = "NSE"
_EQUITY_CSV_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
_CACHE_PATH = Path(DATA_DIR) / "nse_equity_l.csv"
_CACHE_HOURS = 24
_TIMEOUT_SEC = 30
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# Mainboard equity series (EQ regular, BE trade-to-trade, BZ surveillance).
_EQUITY_SERIES = frozenset({"EQ", "BE", "BZ"})


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


def _parse_equity_csv(text: str) -> pd.DataFrame:
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
        if series and series not in _EQUITY_SERIES:
            continue
        name = safe_str(row.get(name_col)) if name_col else ticker
        seen.add(ticker)
        rows.append(
            {
                "ticker": ticker,
                "name": name or ticker,
                "market": NSE_MARKET,
                "series": series,
                "sector": "",
                "industry": "",
                "sub_sector": "",
                "source_sector": "",
            }
        )
    return pd.DataFrame(rows)


def _fetch_equity_csv_text(*, force: bool = False) -> str:
    if not force and _cache_fresh():
        return _CACHE_PATH.read_text(encoding="utf-8", errors="replace")

    session = _session()
    try:
        session.get("https://www.nseindia.com", timeout=min(15, _TIMEOUT_SEC))
    except Exception:
        pass
    response = session.get(_EQUITY_CSV_URL, timeout=_TIMEOUT_SEC)
    response.raise_for_status()
    text = response.text or ""
    if "SYMBOL" not in text.upper() or len(text) < 200:
        raise RuntimeError(f"NSE EQUITY_L CSV empty/invalid ({len(text)} bytes)")
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(text, encoding="utf-8")
    return text


def fetch_nse_equity_listings(*, force: bool = False) -> pd.DataFrame:
    """Return NSE mainboard listings from EQUITY_L (live or cache)."""
    try:
        text = _fetch_equity_csv_text(force=force)
        df = _parse_equity_csv(text)
        if not df.empty:
            return df.reset_index(drop=True)
    except Exception:
        if _CACHE_PATH.is_file():
            df = _parse_equity_csv(
                _CACHE_PATH.read_text(encoding="utf-8", errors="replace")
            )
            if not df.empty:
                return df.reset_index(drop=True)
    return pd.DataFrame()


def merge_nse_equity_into_stocks(
    stocks: pd.DataFrame,
    *,
    force_fetch: bool = False,
) -> pd.DataFrame:
    """
    Replace ``NSE`` mainboard rows from the official EQUITY_L list.

    Preserves other markets (BSE, NSE SME). Classification labels from prior
    NSE rows are carried forward when the ticker still exists.
    """
    nse = fetch_nse_equity_listings(force=force_fetch)
    if nse.empty:
        return stocks if stocks is not None else pd.DataFrame()

    base = stocks.copy() if stocks is not None and not stocks.empty else pd.DataFrame()
    prior = pd.DataFrame()
    if not base.empty and "market" in base.columns:
        is_nse = base["market"].astype(str).str.upper() == NSE_MARKET
        prior = base.loc[is_nse].copy()
        base = base.loc[~is_nse].copy()

    for col in (
        "ticker",
        "name",
        "market",
        "sector",
        "industry",
        "sub_sector",
        "source_sector",
    ):
        if col not in nse.columns:
            nse[col] = ""
        if not base.empty and col not in base.columns:
            base[col] = ""
        if not prior.empty and col not in prior.columns:
            prior[col] = ""

    if not prior.empty:
        look = prior.drop_duplicates("ticker").set_index(
            prior["ticker"].astype(str).str.upper()
        )
        for idx, row in nse.iterrows():
            ticker = safe_str(row.get("ticker")).upper()
            if ticker not in look.index:
                continue
            prev = look.loc[ticker]
            if isinstance(prev, pd.DataFrame):
                prev = prev.iloc[0]
            for col in ("name", "sector", "industry", "sub_sector", "source_sector"):
                cur = safe_str(nse.at[idx, col])
                alt = safe_str(prev.get(col))
                if col == "name":
                    # Prefer EQUITY_L name; fall back to prior if blank.
                    if not cur and alt:
                        nse.at[idx, col] = alt
                elif not cur and alt:
                    nse.at[idx, col] = alt

    if nse.empty:
        return base.reset_index(drop=True) if not base.empty else nse

    cols = [c for c in base.columns] if not base.empty else list(nse.columns)
    for c in cols:
        if c not in nse.columns:
            nse[c] = ""
    nse = nse[cols] if cols else nse
    out = pd.concat([base, nse], ignore_index=True) if not base.empty else nse
    return out.drop_duplicates(subset=["ticker", "market"], keep="last").reset_index(
        drop=True
    )


def stocks_need_nse_equity(stocks: pd.DataFrame, *, min_count: int = 2000) -> bool:
    """True when NSE mainboard is short, CSV stale, or drifts from EQUITY_L."""
    if stocks is None or stocks.empty or "market" not in stocks.columns:
        return True
    n = int((stocks["market"].astype(str).str.upper() == NSE_MARKET).sum())
    if n < int(min_count):
        return True
    if not _cache_fresh():
        return True
    try:
        official = len(
            _parse_equity_csv(
                _CACHE_PATH.read_text(encoding="utf-8", errors="replace")
            )
        )
        if official and abs(official - n) >= 5:
            return True
    except Exception:
        return True
    return False
