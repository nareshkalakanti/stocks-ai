"""Governance scan — NSE DIN boards (primary) → optional Yahoo fallback."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from stocks.core.config import YFINANCE_REQUEST_DELAY, yfinance_worker_count
from stocks.core.text_utils import safe_str
from stocks.governance.service import (
    companies_with_boards,
    record_scan_attempt,
    save_company_board,
    scanned_ticker_set,
    ticker_has_din_board,
)
from stocks.market.nse_governance_board import fetch_board_from_nse_governance
from stocks.market.yfinance_limits import call_throttled

# Keep Yahoo as last-resort draft only (no DIN).
_ENABLE_YFINANCE_FALLBACK = False
_NSE_GOV_MARKETS = frozenset({"NSE", "NSE SME"})


def _is_nse_gov_market(market: str | None) -> bool:
    return safe_str(market).upper() in _NSE_GOV_MARKETS


def fetch_board_from_yfinance(ticker: str, market: str | None = "NSE") -> dict | None:
    """Yahoo ``companyOfficers`` — name-only, no DIN. Disabled by default."""
    if not _ENABLE_YFINANCE_FALLBACK:
        return None
    import yfinance as yf

    from stocks.market.price_service import to_yfinance_symbol
    from stocks.strategies.pead2.service import _safe_yf_info

    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        return None
    market_key = safe_str(market).upper() or "NSE"
    if not _is_nse_gov_market(market_key):
        return None
    symbol = to_yfinance_symbol(ticker_key, market_key)

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = _safe_yf_info(yt) or {}
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
        if not seats:
            return None
        name = (
            safe_str(info.get("longName"))
            or safe_str(info.get("shortName"))
            or ticker_key
        )
        return {
            "ticker": ticker_key,
            "name": name,
            "seats": seats,
            "market": market_key,
            "source": "yfinance",
        }

    return call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY)


def fetch_board_for_ticker(ticker: str, market: str | None = "NSE") -> dict | None:
    """DIN-first board fetch: NSE governance, then optional Yahoo."""
    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        return None
    market_key = safe_str(market).upper() or "NSE"
    if not _is_nse_gov_market(market_key):
        return None

    board = fetch_board_from_nse_governance(ticker_key, market=market_key)
    if board and board.get("seats"):
        # Universe market wins for SME so Map/Companies filters stay correct.
        if market_key == "NSE SME":
            board = {**board, "market": "NSE SME"}
        return board
    return fetch_board_from_yfinance(ticker_key, market_key)


def pending_governance_jobs(
    universe: pd.DataFrame,
    *,
    skip_scanned: bool = True,
) -> list[tuple[str, str, str]]:
    """Jobs as (ticker, name, market) needing a DIN board."""
    if universe is None or universe.empty:
        return []
    work = universe.copy()
    if "market" in work.columns:
        mk = work["market"].astype(str).str.upper()
        work = work[mk.isin(_NSE_GOV_MARKETS)]
    work = work.drop_duplicates(subset=["ticker"])

    din_done: set[str] = set()
    name_only: set[str] = set()
    scanned: set[str] = set()
    if skip_scanned:
        scanned = scanned_ticker_set()
        existing = companies_with_boards()
        if not existing.empty and "ticker" in existing.columns:
            for t in existing["ticker"].astype(str).str.upper().tolist():
                key = safe_str(t).upper()
                if not key:
                    continue
                if ticker_has_din_board(key):
                    din_done.add(key)
                else:
                    name_only.add(key)

    jobs: list[tuple[str, str, str]] = []
    for _, row in work.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        market = safe_str(row.get("market")).upper() or "NSE"
        if not _is_nse_gov_market(market):
            continue
        if skip_scanned and ticker in din_done:
            continue
        # Name-only Yahoo rows stay pending so NSE DIN can upgrade them.
        if skip_scanned and ticker not in name_only and ticker in scanned:
            continue
        name = safe_str(row.get("name")) or ticker
        jobs.append((ticker, name, market))
    # Prefer never-saved tickers before upgrading name-only rows.
    jobs.sort(key=lambda j: (0 if j[0] not in name_only else 1, j[0]))
    return jobs


def run_governance_scan(
    universe: pd.DataFrame,
    *,
    batch_size: int = 20,
    max_workers: int | None = None,
    skip_scanned: bool = True,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict:
    """
    Fetch one batch of pending tickers from NSE governance (DIN) and save boards.

    Call repeatedly until ``pending_after`` is 0.
    """
    empty = {
        "scanned": 0,
        "saved": 0,
        "skipped_empty": 0,
        "skipped_protected": 0,
        "failed": 0,
        "saved_tickers": [],
        "pending_before": 0,
        "pending_after": 0,
        "universe": 0,
        "batch_size": int(batch_size),
        "done": False,
        "source": "nse_governance",
    }
    if universe is None or universe.empty:
        return empty

    work = universe.copy()
    if "market" in work.columns:
        mk = work["market"].astype(str).str.upper()
        work = work[mk.isin(_NSE_GOV_MARKETS)]
    work = work.drop_duplicates(subset=["ticker"])
    universe_n = len(work)

    pending = pending_governance_jobs(work, skip_scanned=skip_scanned)
    pending_before = len(pending)
    # NSE filings are heavier than Yahoo — keep batches modest.
    batch = pending[: max(1, int(batch_size))]
    if not batch:
        empty.update(
            {
                "pending_before": 0,
                "pending_after": 0,
                "universe": universe_n,
                "done": True,
            }
        )
        return empty

    # Cap parallelism — NSE rate-limits aggressive clients.
    workers = max_workers or min(yfinance_worker_count(len(batch), 3), 3)
    saved = 0
    skipped_empty = 0
    skipped_protected = 0
    failed = 0
    saved_tickers: list[str] = []
    total = len(batch)
    done = 0

    with ThreadPoolExecutor(max_workers=max(1, min(workers, total))) as pool:
        futures = {
            pool.submit(fetch_board_for_ticker, ticker, market): (
                ticker,
                fallback_name,
                market,
            )
            for ticker, fallback_name, market in batch
        }
        for fut in as_completed(futures):
            done += 1
            ticker, fallback_name, market = futures[fut]
            if progress_callback:
                progress_callback(done, total, ticker)
            try:
                payload = fut.result()
            except Exception as exc:
                failed += 1
                record_scan_attempt(ticker, "failed", detail=str(exc)[:200])
                continue
            if not payload or not payload.get("seats"):
                skipped_empty += 1
                record_scan_attempt(
                    ticker,
                    "empty",
                    detail="No NSE governance board / DIN seats",
                )
                continue
            seats = list(payload["seats"])
            has_din = any(safe_str(s.get("din")) for s in seats)
            try:
                result = save_company_board(
                    ticker=ticker,
                    name=safe_str(payload.get("name")) or fallback_name,
                    market=safe_str(payload.get("market")) or market,
                    seats=seats,
                    notes=safe_str(payload.get("source")) or None,
                    replace_seats=True,
                    # DIN payload may upgrade Yahoo name-only; name-only never
                    # overwrites an existing DIN board.
                    protect_din_board=not has_din,
                )
            except ValueError as exc:
                failed += 1
                record_scan_attempt(ticker, "failed", detail=str(exc)[:200])
                continue
            if result.get("skipped"):
                skipped_protected += 1
                record_scan_attempt(
                    ticker, "protected", detail=str(result.get("reason") or "")
                )
                continue
            saved += 1
            saved_tickers.append(ticker)
            record_scan_attempt(
                ticker,
                "saved",
                detail=safe_str(payload.get("source")) or "nse_governance",
            )

    pending_after = max(0, pending_before - total)
    return {
        "scanned": total,
        "saved": saved,
        "skipped_empty": skipped_empty,
        "skipped_protected": skipped_protected,
        "failed": failed,
        "saved_tickers": saved_tickers,
        "pending_before": pending_before,
        "pending_after": pending_after,
        "universe": universe_n,
        "batch_size": int(batch_size),
        "done": pending_after == 0,
        "source": "nse_governance",
    }
