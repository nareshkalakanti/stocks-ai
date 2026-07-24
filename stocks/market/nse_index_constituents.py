"""NSE index constituents — Nifty 50 / 100 / Midcap 150 / Smallcap 250 / 500.

Source: nsearchives CSV lists (Company Name, Industry, Symbol, Series, ISIN).
Cached in stocks_ai.db with optional force refresh.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from typing import Any

import pandas as pd
import requests

from stocks.core.config import DATA_DIR
from stocks.core.database import get_connection, init_db
from stocks.core.text_utils import safe_str

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_NSE_ARCHIVES = "https://nsearchives.nseindia.com/content/indices"
_TIMEOUT_SEC = 30
# Weekly refresh is enough — index reconstitutions are infrequent.
DEFAULT_CACHE_HOURS = 168

# Stable ids used in DB + playlist wiring.
NIFTY_INDEXES: dict[str, dict[str, str]] = {
    "NIFTY_50": {
        "label": "Nifty 50",
        "csv": "ind_nifty50list.csv",
    },
    "NIFTY_100": {
        "label": "Nifty 100",
        "csv": "ind_nifty100list.csv",
    },
    "NIFTY_MIDCAP_150": {
        "label": "Nifty Midcap 150",
        "csv": "ind_niftymidcap150list.csv",
    },
    "NIFTY_SMALLCAP_250": {
        "label": "Nifty Smallcap 250",
        "csv": "ind_niftysmallcap250list.csv",
    },
    "NIFTY_500": {
        "label": "Nifty 500",
        "csv": "ind_nifty500list.csv",
    },
}

LABEL_TO_INDEX_ID = {meta["label"]: index_id for index_id, meta in NIFTY_INDEXES.items()}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _USER_AGENT,
            "Accept": "text/csv,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        }
    )
    return session


def _parse_constituent_csv(text: str, *, index_id: str, fetched_at: str) -> list[dict[str, Any]]:
    if not text or not text.strip():
        return []
    try:
        df = pd.read_csv(StringIO(text))
    except Exception:
        return []
    if df.empty:
        return []
    cols = {str(c).strip().lower(): c for c in df.columns}
    sym_col = cols.get("symbol")
    if sym_col is None:
        return []
    name_col = cols.get("company name") or cols.get("company") or cols.get("name")
    industry_col = cols.get("industry")
    isin_col = cols.get("isin code") or cols.get("isin")
    series_col = cols.get("series")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        ticker = safe_str(row.get(sym_col)).upper()
        if not ticker or ticker in {"SYMBOL", "SCRIP"} or ticker in seen:
            continue
        seen.add(ticker)
        rows.append(
            {
                "index_id": index_id,
                "ticker": ticker,
                "name": safe_str(row.get(name_col)) if name_col else "",
                "industry": safe_str(row.get(industry_col)) if industry_col else "",
                "isin": safe_str(row.get(isin_col)) if isin_col else "",
                "series": safe_str(row.get(series_col)) if series_col else "",
                "fetched_at": fetched_at,
            }
        )
    return rows


def fetch_index_constituents_from_nse(
    index_id: str,
    *,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Live download of one index constituent CSV from NSE archives."""
    meta = NIFTY_INDEXES.get(index_id)
    if not meta:
        raise ValueError(f"Unknown index_id: {index_id}")
    url = f"{_NSE_ARCHIVES}/{meta['csv']}"
    sess = session or _session()
    resp = sess.get(url, timeout=_TIMEOUT_SEC)
    resp.raise_for_status()
    return _parse_constituent_csv(resp.text, index_id=index_id, fetched_at=_utc_now())


def _ensure_index_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS index_constituents (
            index_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            name TEXT,
            industry TEXT,
            isin TEXT,
            series TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (index_id, ticker)
        );
        CREATE INDEX IF NOT EXISTS idx_index_constituents_ticker
            ON index_constituents(ticker);
        CREATE INDEX IF NOT EXISTS idx_index_constituents_fetched
            ON index_constituents(fetched_at);
        """
    )


def replace_index_constituents(index_id: str, rows: list[dict[str, Any]]) -> int:
    """Replace all rows for one index_id. Returns row count saved."""
    init_db()
    with get_connection() as conn:
        _ensure_index_tables(conn)
        conn.execute("DELETE FROM index_constituents WHERE index_id = ?", (index_id,))
        for row in rows:
            conn.execute(
                """
                INSERT INTO index_constituents (
                    index_id, ticker, name, industry, isin, series, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    index_id,
                    row["ticker"],
                    row.get("name") or None,
                    row.get("industry") or None,
                    row.get("isin") or None,
                    row.get("series") or None,
                    row.get("fetched_at") or _utc_now(),
                ),
            )
        return len(rows)


def load_index_constituents(index_id: str) -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        _ensure_index_tables(conn)
        return pd.read_sql_query(
            """
            SELECT index_id, ticker, name, industry, isin, series, fetched_at
            FROM index_constituents
            WHERE index_id = ?
            ORDER BY ticker
            """,
            conn,
            params=(index_id,),
        )


def index_constituents_fetched_at(index_id: str) -> str | None:
    init_db()
    with get_connection() as conn:
        _ensure_index_tables(conn)
        row = conn.execute(
            """
            SELECT MAX(fetched_at) AS fetched_at
            FROM index_constituents
            WHERE index_id = ?
            """,
            (index_id,),
        ).fetchone()
    if not row or not row["fetched_at"]:
        return None
    return str(row["fetched_at"])


def index_constituents_fresh(
    index_id: str,
    *,
    max_hours: int = DEFAULT_CACHE_HOURS,
) -> bool:
    from stocks.core.database import _is_fresh

    return _is_fresh(index_constituents_fetched_at(index_id), max_hours)


def ensure_index_constituents(
    index_id: str,
    *,
    force: bool = False,
    max_hours: int = DEFAULT_CACHE_HOURS,
) -> dict[str, Any]:
    """
    Return constituent rows for ``index_id``, refreshing from NSE when stale or forced.

    Returns ``{index_id, count, refreshed, fetched_at, error?}``.
    """
    if index_id not in NIFTY_INDEXES:
        raise ValueError(f"Unknown index_id: {index_id}")

    cached = load_index_constituents(index_id)
    if not force and not cached.empty and index_constituents_fresh(index_id, max_hours=max_hours):
        return {
            "index_id": index_id,
            "count": len(cached),
            "refreshed": False,
            "fetched_at": index_constituents_fetched_at(index_id),
        }

    try:
        rows = fetch_index_constituents_from_nse(index_id)
    except Exception as exc:
        if not cached.empty:
            return {
                "index_id": index_id,
                "count": len(cached),
                "refreshed": False,
                "fetched_at": index_constituents_fetched_at(index_id),
                "error": str(exc),
            }
        raise

    if not rows:
        if not cached.empty:
            return {
                "index_id": index_id,
                "count": len(cached),
                "refreshed": False,
                "fetched_at": index_constituents_fetched_at(index_id),
                "error": "NSE returned empty list",
            }
        return {
            "index_id": index_id,
            "count": 0,
            "refreshed": False,
            "fetched_at": None,
            "error": "NSE returned empty list",
        }

    n = replace_index_constituents(index_id, rows)
    return {
        "index_id": index_id,
        "count": n,
        "refreshed": True,
        "fetched_at": rows[0]["fetched_at"],
    }


def ensure_all_nifty_indexes(
    *,
    force: bool = False,
    max_hours: int = DEFAULT_CACHE_HOURS,
) -> list[dict[str, Any]]:
    """Refresh every configured Nifty index (skip when fresh unless ``force``)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    session = _session()
    for index_id in NIFTY_INDEXES:
        if not force and index_constituents_fresh(index_id, max_hours=max_hours):
            cached = load_index_constituents(index_id)
            results.append(
                {
                    "index_id": index_id,
                    "count": len(cached),
                    "refreshed": False,
                    "fetched_at": index_constituents_fetched_at(index_id),
                }
            )
            continue
        try:
            rows = fetch_index_constituents_from_nse(index_id, session=session)
            if rows:
                n = replace_index_constituents(index_id, rows)
                results.append(
                    {
                        "index_id": index_id,
                        "count": n,
                        "refreshed": True,
                        "fetched_at": rows[0]["fetched_at"],
                    }
                )
            else:
                results.append(ensure_index_constituents(index_id, force=False))
        except Exception as exc:
            cached = load_index_constituents(index_id)
            results.append(
                {
                    "index_id": index_id,
                    "count": len(cached),
                    "refreshed": False,
                    "fetched_at": index_constituents_fetched_at(index_id),
                    "error": str(exc),
                }
            )
    return results


def index_tickers(index_id: str, *, seed_if_empty: bool = True) -> set[str]:
    df = load_index_constituents(index_id)
    if df.empty and seed_if_empty:
        ensure_index_constituents(index_id, force=False)
        df = load_index_constituents(index_id)
    if df.empty:
        return set()
    return {safe_str(t).upper() for t in df["ticker"].tolist() if safe_str(t)}


__all__ = [
    "DEFAULT_CACHE_HOURS",
    "LABEL_TO_INDEX_ID",
    "NIFTY_INDEXES",
    "ensure_all_nifty_indexes",
    "ensure_index_constituents",
    "fetch_index_constituents_from_nse",
    "index_constituents_fetched_at",
    "index_constituents_fresh",
    "index_tickers",
    "load_index_constituents",
    "replace_index_constituents",
]
