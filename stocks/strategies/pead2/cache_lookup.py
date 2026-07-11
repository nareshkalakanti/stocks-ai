"""Compute PEAD scores from pead2_cache metrics for cross-strategy dashboards."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import PEAD2_CALC_VERSION
from stocks.core.database import load_pead2_cache, save_pead2_cache
from stocks.core.text_utils import safe_str
from stocks.strategies.pead2.service import _expand_lag_rows, _pead2_scorable_blob
from stocks.strategies.pead2.strategy import score_pead2_candidates


def _pead_blob_scorable(blob: dict | None) -> bool:
    """True when cache row has lag-0 metrics usable for scoring."""
    if not blob or not isinstance(blob, dict):
        return False
    if blob.get("unavailable") or blob.get("no_pead_data"):
        return False
    return _pead2_scorable_blob(blob) and bool((blob.get("lags") or {}).get("0"))


def _pead_unavailable_note(blob: dict) -> str:
    if blob.get("unavailable"):
        return safe_str(blob.get("unavailable_reason")) or "No PEAD data"
    if blob.get("no_pead_data"):
        return safe_str(blob.get("no_pead_data_reason")) or "No PEAD data"
    return "No PEAD data"


def pead_score_from_blob(blob: dict | None) -> float | None:
    """Read a pre-computed score when present on a cached PEAD2 payload."""
    if not blob or not isinstance(blob, dict):
        return None
    lags = blob.get("lags")
    if isinstance(lags, dict):
        lag0 = lags.get("0") or lags.get(0)
        if isinstance(lag0, dict):
            score = lag0.get("pead_score")
            if score is not None and not (isinstance(score, float) and pd.isna(score)):
                try:
                    return round(float(score), 1)
                except (TypeError, ValueError):
                    pass
    score = blob.get("pead_score")
    if score is not None and not (isinstance(score, float) and pd.isna(score)):
        try:
            return round(float(score), 1)
        except (TypeError, ValueError):
            pass
    return None


def pead_missing_reason(ticker: str, market: str | None) -> str:
    """User-facing reason when PEAD2 cannot be computed for a ticker."""
    from stocks.core.config import PEAD2_MIN_QUARTERS
    from stocks.market.price_service import to_yfinance_symbol
    from stocks.market.yfinance_limits import call_fast
    from stocks.strategies.earnings.quality import passes_earnings_quality
    from stocks.strategies.earnings.strategy import EBIDT_FIELDS, EPS_FIELDS, NET_INCOME_FIELDS
    from stocks.strategies.pead2.service import REVENUE_FIELDS, _series_from_income

    symbol = to_yfinance_symbol(ticker, market)

    def _probe() -> str:
        import yfinance as yf

        yt = yf.Ticker(symbol)
        income = yt.quarterly_income_stmt
        revenue = _series_from_income(income, REVENUE_FIELDS)
        if revenue is None or len(revenue) == 0:
            return "No quarterly earnings on Yahoo"
        if len(revenue) < PEAD2_MIN_QUARTERS:
            return f"Needs {PEAD2_MIN_QUARTERS}+ quarters (has {len(revenue)})"
        net_profit = _series_from_income(income, NET_INCOME_FIELDS)
        eps = _series_from_income(income, EPS_FIELDS)
        if net_profit is None or eps is None:
            return "Incomplete earnings data on Yahoo"
        ok, reason = passes_earnings_quality(net_profit, eps)
        if not ok:
            return reason or "Earnings quality check failed"
        return "Insufficient quarterly data"

    try:
        result = call_fast(_probe)
        return result or "Insufficient quarterly data"
    except Exception:
        return "Could not fetch earnings data"


def _pead_notes_from_cache(tickers: list[str], *, max_hours: int) -> dict[str, str]:
    keys = [safe_str(t).upper() for t in tickers if safe_str(t)]
    if not keys:
        return {}
    cached = load_pead2_cache(keys, max_hours=max_hours)
    notes: dict[str, str] = {}
    for key in keys:
        blob = cached.get(key)
        if blob is None:
            notes[key] = "Not scanned — run PEAD fetch"
            continue
        if not _pead_blob_scorable(blob):
            notes[key] = _pead_unavailable_note(blob)
    return notes


def count_pead_backfill_pending(tickers: list[str], *, max_hours: int) -> int:
    """How many tickers still need a PEAD fetch (missing or not scorable in cache)."""
    keys = [safe_str(t).upper() for t in tickers if safe_str(t)]
    if not keys:
        return 0
    cached = load_pead2_cache(keys, max_hours=max_hours)
    return sum(1 for key in keys if not _pead_blob_scorable(cached.get(key)))


def load_pead_scores_by_ticker(
    tickers: list[str],
    *,
    max_hours: int,
) -> dict[str, float]:
    """
    Map ticker → PEAD score from SQLite PEAD2 cache.

    Scores are recomputed from cached quarterly metrics (lag 0) using the same
    percentile/absolute logic as the PEAD scan — they are not stored per row.
    """
    keys = [safe_str(t).upper() for t in tickers if safe_str(t)]
    if not keys:
        return {}

    cached = load_pead2_cache(keys, max_hours=max_hours)
    if not cached:
        return {}

    blobs = [
        blob
        for blob in cached.values()
        if _pead_blob_scorable(blob)
    ]
    rows = _expand_lag_rows(blobs, quarter_lag=0)
    if not rows:
        return {}

    scored = score_pead2_candidates(pd.DataFrame(rows))
    if scored.empty or "pead_score" not in scored.columns:
        return {}

    out: dict[str, float] = {}
    for _, row in scored.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        score = row.get("pead_score")
        if not ticker or score is None or (isinstance(score, float) and pd.isna(score)):
            continue
        try:
            out[ticker] = round(float(score), 1)
        except (TypeError, ValueError):
            continue
    return out


def load_pead_pe_by_ticker(
    tickers: list[str],
    *,
    max_hours: int,
) -> dict[str, dict[str, float | None]]:
    """PE / Fwd PE from PEAD2 cache lag-0 rows (fallback when IV cache lacks PE)."""
    keys = [safe_str(t).upper() for t in tickers if safe_str(t)]
    if not keys:
        return {}

    cached = load_pead2_cache(keys, max_hours=max_hours)
    if not cached:
        return {}

    blobs = [
        blob
        for blob in cached.values()
        if _pead_blob_scorable(blob)
    ]
    rows = _expand_lag_rows(blobs, quarter_lag=0)
    out: dict[str, dict[str, float | None]] = {}
    for row in rows:
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        pe = row.get("pe_ratio")
        fpe = row.get("forward_pe")
        if pe is None and fpe is None:
            continue
        entry: dict[str, float | None] = {}
        if pe is not None and not (isinstance(pe, float) and pd.isna(pe)):
            try:
                entry["pe_ratio"] = round(float(pe), 1)
            except (TypeError, ValueError):
                pass
        if fpe is not None and not (isinstance(fpe, float) and pd.isna(fpe)):
            try:
                entry["forward_pe"] = round(float(fpe), 1)
            except (TypeError, ValueError):
                pass
        if entry:
            out[ticker] = entry
    return out


def attach_pead_scores(
    frame: pd.DataFrame,
    *,
    max_hours: int,
    column: str = "pead_score",
) -> pd.DataFrame:
    """Add ``pead_score`` from SQLite PEAD2 cache (null when not scanned)."""
    if frame is None or frame.empty or "ticker" not in frame.columns:
        return frame
    out = frame.copy()
    tickers = out["ticker"].astype(str).str.upper().tolist()
    scores = load_pead_scores_by_ticker(tickers, max_hours=max_hours)
    notes = _pead_notes_from_cache(tickers, max_hours=max_hours)
    out[column] = out["ticker"].astype(str).str.upper().map(scores)
    out["pead_note"] = out["ticker"].astype(str).str.upper().map(notes)
    out.loc[out[column].notna(), "pead_note"] = pd.NA
    return out


def backfill_pead_cache_for_tickers(
    tickers: list[str],
    markets: list[str | None] | None = None,
    *,
    max_fetch: int = 50,
    max_workers: int = 4,
) -> int:
    """
    Fetch and cache PEAD2 payloads for tickers missing or not scorable in SQLite.

    Returns the number of tickers fetched (including unavailable tombstones).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from stocks.strategies.pead2.service import analyze_pead2_ticker

    keys = [safe_str(t).upper() for t in tickers if safe_str(t)]
    if not keys:
        return 0

    existing = load_pead2_cache(keys, max_hours=999999)
    pending: list[tuple[str, str | None]] = []
    for i, key in enumerate(keys):
        if _pead_blob_scorable(existing.get(key)):
            continue
        market = None
        if markets is not None and i < len(markets):
            market = safe_str(markets[i]) or None
        pending.append((key, market))
    pending = pending[: max(0, max_fetch)]
    if not pending:
        return 0

    fresh: list[dict] = []
    workers = max(1, min(max_workers, len(pending)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(analyze_pead2_ticker, ticker, market): (ticker, market)
            for ticker, market in pending
        }
        for fut in as_completed(futures):
            ticker, market = futures[fut]
            try:
                row = fut.result()
            except Exception:
                row = None
            if row:
                fresh.append(row)
            else:
                reason = pead_missing_reason(ticker, market)
                fresh.append(
                    {
                        "ticker": ticker,
                        "market": market,
                        "calc_version": PEAD2_CALC_VERSION,
                        "no_pead_data": True,
                        "no_pead_data_reason": reason,
                        "unavailable": True,
                        "unavailable_reason": reason,
                        "lags": {},
                    }
                )

    if fresh:
        save_pead2_cache(fresh)
    return len(fresh)


def ensure_pead_scores(
    frame: pd.DataFrame,
    *,
    max_hours: int,
    backfill_max: int = 0,
    max_workers: int = 4,
) -> pd.DataFrame:
    """Attach PEAD scores, optionally fetching missing tickers from Yahoo."""
    out = attach_pead_scores(frame, max_hours=max_hours)
    if backfill_max <= 0 or out is None or out.empty or "pead_score" not in out.columns:
        return out

    missing = out[out["pead_score"].isna()]
    if missing.empty:
        return out

    tickers = missing["ticker"].astype(str).tolist()
    markets = (
        missing["market"].astype(str).tolist()
        if "market" in missing.columns
        else [None] * len(tickers)
    )
    backfill_pead_cache_for_tickers(
        tickers,
        markets,
        max_fetch=backfill_max,
        max_workers=max_workers,
    )
    return attach_pead_scores(out, max_hours=max_hours)
