"""Governance scan — NSE sector universe → Yahoo officers → governance.db."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import YFINANCE_REQUEST_DELAY, yfinance_worker_count
from stocks.core.text_utils import safe_str
from stocks.governance.service import save_company_board
from stocks.market.price_service import to_yfinance_symbol
from stocks.market.yfinance_limits import call_throttled
from stocks.strategies.pead2.service import _safe_yf_info


def _officers_from_info(info: dict) -> list[dict]:
    raw = info.get("companyOfficers") or []
    seats: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = safe_str(item.get("name"))
        title = safe_str(item.get("title") or item.get("designation")) or "Director"
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        seats.append(
            {
                "name": name,
                "designation": title,
                "din": "",
                "source": "yfinance",
            }
        )
    return seats


def fetch_board_from_yfinance(ticker: str, market: str | None = "NSE") -> dict | None:
    """Return ``{ticker, name, seats}`` or None when Yahoo has no officers."""
    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        return None
    symbol = to_yfinance_symbol(ticker_key, market or "NSE")

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = _safe_yf_info(yt) or {}
        seats = _officers_from_info(info)
        if not seats:
            return None
        name = (
            safe_str(info.get("longName"))
            or safe_str(info.get("shortName"))
            or ticker_key
        )
        return {"ticker": ticker_key, "name": name, "seats": seats, "market": "NSE"}

    return call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY)


def run_governance_scan(
    universe: pd.DataFrame,
    *,
    max_tickers: int = 50,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """
    Scan NSE tickers for Yahoo ``companyOfficers`` and save boards to governance.db.

    Curated DIN boards are protected when Yahoo returns name-only officers.
    """
    if universe is None or universe.empty:
        return {
            "scanned": 0,
            "saved": 0,
            "skipped_empty": 0,
            "skipped_protected": 0,
            "failed": 0,
            "saved_tickers": [],
        }

    work = universe.copy()
    if "market" in work.columns:
        work = work[work["market"].astype(str).str.upper() == "NSE"]
    work = work.drop_duplicates(subset=["ticker"]).head(max(1, int(max_tickers)))
    jobs: list[tuple[str, str]] = []
    for _, row in work.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        name = safe_str(row.get("name")) or ticker
        jobs.append((ticker, name))

    workers = max_workers or yfinance_worker_count(len(jobs), 4)
    saved = 0
    skipped_empty = 0
    skipped_protected = 0
    failed = 0
    saved_tickers: list[str] = []
    total = len(jobs)
    done = 0

    with ThreadPoolExecutor(max_workers=max(1, min(workers, total or 1))) as pool:
        futures = {
            pool.submit(fetch_board_from_yfinance, ticker, "NSE"): (ticker, fallback_name)
            for ticker, fallback_name in jobs
        }
        for fut in as_completed(futures):
            done += 1
            if progress_callback:
                progress_callback(done, total)
            ticker, fallback_name = futures[fut]
            try:
                payload = fut.result()
            except Exception:
                failed += 1
                continue
            if not payload or not payload.get("seats"):
                skipped_empty += 1
                continue
            try:
                result = save_company_board(
                    ticker=ticker,
                    name=safe_str(payload.get("name")) or fallback_name,
                    seats=list(payload["seats"]),
                    replace_seats=True,
                    protect_din_board=True,
                )
            except ValueError:
                failed += 1
                continue
            if result.get("skipped"):
                skipped_protected += 1
                continue
            saved += 1
            saved_tickers.append(ticker)

    return {
        "scanned": total,
        "saved": saved,
        "skipped_empty": skipped_empty,
        "skipped_protected": skipped_protected,
        "failed": failed,
        "saved_tickers": saved_tickers,
    }
