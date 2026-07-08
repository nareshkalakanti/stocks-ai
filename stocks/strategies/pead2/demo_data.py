"""PEAD demo rows from SQLite cache — scored with the live PEAD pipeline."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import PEAD2_CALC_VERSION
from stocks.core.database import get_connection, init_db, load_all_pead2_cache_payloads
from stocks.strategies.pead2.service import _expand_lag_rows, _score_pead_frame
from stocks.strategies.pead2.strategy import PEAD_HIGH_SCORE_MIN

# Past-result names for UI smoke tests (must exist in pead2_cache).
DEMO_TICKERS: tuple[str, ...] = (
    "SANDHAR",
    "INDOBORAX",
    "CENTENKA",
    "BODALCHEM",
    "JSWCEMENT",
)


def _empty_scan_result() -> dict:
    empty = pd.DataFrame()
    return {
        "candidates": empty,
        "candidates_previous": empty,
        "scanned": 0,
        "hits": 0,
        "hits_previous": 0,
        "cache_hits": 0,
        "demo_missing": list(DEMO_TICKERS),
    }


def _demo_meta(tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["ticker", "name", "market", "sector"])
    init_db()
    placeholders = ",".join("?" * len(tickers))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, name, market, sector
            FROM stocks
            WHERE ticker IN ({placeholders})
            """,
            tickers,
        ).fetchall()
    if not rows:
        return pd.DataFrame({"ticker": tickers})
    meta = pd.DataFrame([dict(r) for r in rows]).drop_duplicates("ticker")
    return meta


def _filter_demo(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "ticker" not in df.columns:
        return pd.DataFrame()
    demo_set = set(DEMO_TICKERS)
    out = df[df["ticker"].astype(str).str.upper().isin(demo_set)].copy()
    if out.empty:
        return out
    if "pead_score" in out.columns:
        out = out.sort_values("pead_score", ascending=False)
    out["valuation_pass"] = out["pead_score"] > PEAD_HIGH_SCORE_MIN
    return out.reset_index(drop=True)


def pead2_demo_candidates() -> pd.DataFrame:
    """Demo subset only (scored via ``pead2_demo_scan_result``)."""
    return pead2_demo_scan_result()["candidates"]


def pead2_demo_scan_result() -> dict:
    """
    Load demo tickers from pead2_cache, score against the full cached universe,
    and return current + previous (lag 1) quarter frames.
    """
    blobs = [
        blob
        for blob in load_all_pead2_cache_payloads(max_hours=999999)
        if isinstance(blob, dict)
        and blob.get("calc_version") == PEAD2_CALC_VERSION
        and not blob.get("unavailable")
    ]
    if not blobs:
        return _empty_scan_result()

    present = {
        str(b.get("ticker", "")).upper()
        for b in blobs
        if b.get("lags", {}).get("0")
    }
    missing = [t for t in DEMO_TICKERS if t not in present]
    meta = _demo_meta(list(DEMO_TICKERS))

    current_rows = _expand_lag_rows(blobs, quarter_lag=0)
    previous_rows = _expand_lag_rows(blobs, quarter_lag=1)
    if not current_rows:
        result = _empty_scan_result()
        result["demo_missing"] = missing or list(DEMO_TICKERS)
        return result

    df = _filter_demo(_score_pead_frame(current_rows, meta))
    df_prev = _filter_demo(_score_pead_frame(previous_rows, meta))

    return {
        "candidates": df,
        "candidates_previous": df_prev,
        "scanned": len(blobs),
        "hits": len(df),
        "hits_previous": len(df_prev),
        "cache_hits": len(blobs),
        "demo_missing": missing,
    }
