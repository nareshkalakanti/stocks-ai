"""Scan NSE sector / industry performance vs NIFTY 500."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone

import pandas as pd

from stocks.core.config import HEADWIND_TAILWIND_MCAP_MIN_CR, STRATEGY_MAX_WORKERS
from stocks.core.text_utils import resolve_company_name, safe_str
from stocks.market.indicators import get_nifty500_data
from stocks.strategies.sector_landscape.strategy import (
    equal_weight_index,
    group_key,
    series_to_points,
    total_return_pct,
)
from stocks.strategies.tq_bb.service import (
    _fetch_history,
    _listing_rows,
    _run_parallel_scan,
    is_skippable_symbol,
)
from stocks.shared.links import attach_research_links


def _fetch_stock_weekly(ticker: str, market: str | None) -> dict | None:
    if is_skippable_symbol(ticker):
        return None
    hist = _fetch_history(ticker, market, period="1y", interval="1wk")
    if hist is None or len(hist) < 8:
        return None
    close = hist["Close"].dropna()
    if len(close) < 8:
        return None
    ret = total_return_pct(close)
    if ret is None:
        return None
    price = round(float(close.iloc[-1]), 2)
    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "close": close,
        "return_pct": ret,
        "price": price,
    }


def _align_benchmark(benchmark: pd.DataFrame, weeks: int = 52) -> pd.Series:
    close = benchmark["Close"].dropna().astype(float)
    if len(close) > weeks:
        close = close.iloc[-weeks:]
    return close


def _build_groups(
    stock_rows: list[dict],
    meta: dict[str, dict],
    *,
    min_group_size: int,
) -> tuple[list[dict], list[dict]]:
    """Build sector and industry group payloads."""
    sector_members: dict[str, list[dict]] = defaultdict(list)
    industry_members: dict[str, list[dict]] = defaultdict(list)

    for row in stock_rows:
        ticker = row["ticker"]
        info = meta.get(ticker, {})
        sector = safe_str(info.get("sector"))
        industry = safe_str(info.get("industry"))
        sector_members[group_key(sector, industry, kind="sector")].append(row)
        industry_members[group_key(sector, industry, kind="industry")].append(row)

    sector_groups = _groups_from_members(sector_members, meta, kind="sector", min_group_size=min_group_size)
    industry_groups = _groups_from_members(
        industry_members, meta, kind="industry", min_group_size=min_group_size
    )
    return sector_groups, industry_groups


def _groups_from_members(
    members: dict[str, list[dict]],
    meta: dict[str, dict],
    *,
    kind: str,
    min_group_size: int,
) -> list[dict]:
    groups: list[dict] = []
    for label, rows in members.items():
        if len(rows) < min_group_size:
            continue
        series_map = {r["ticker"]: r["close"] for r in rows}
        index = equal_weight_index(series_map)
        if index.empty:
            continue
        ret = total_return_pct(index)
        if ret is None:
            continue

        sample = meta.get(rows[0]["ticker"], {})
        sector = safe_str(sample.get("sector"))
        industry = safe_str(sample.get("industry"))

        ranked = sorted(rows, key=lambda r: r["return_pct"], reverse=True)
        stocks_payload: list[dict] = []
        for i, r in enumerate(ranked[:24], start=1):
            info = meta.get(r["ticker"], {})
            stocks_payload.append(
                {
                    "rank": i,
                    "ticker": r["ticker"],
                    "name": resolve_company_name(info.get("name"), ticker=r["ticker"]),
                    "industry": safe_str(info.get("industry")) or None,
                    "return_pct": r["return_pct"],
                    "price": r["price"],
                    "spark": series_to_points(r["close"], max_points=32),
                }
            )

        up = sum(1 for r in rows if r["return_pct"] > 0)
        down = len(rows) - up
        groups.append(
            {
                "key": label,
                "kind": kind,
                "sector": sector or None,
                "industry": industry if kind == "industry" else None,
                "stock_count": len(rows),
                "return_pct": ret,
                "up_count": up,
                "down_count": down,
                "series": series_to_points(index, max_points=48),
                "stocks": stocks_payload,
            }
        )

    groups.sort(key=lambda g: g["return_pct"], reverse=True)
    return groups


def run_sector_landscape_scan(
    universe: pd.DataFrame,
    *,
    min_mcap_cr: float = HEADWIND_TAILWIND_MCAP_MIN_CR,
    min_group_size: int = 3,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    listings = _listing_rows(universe)
    if not listings:
        return {"error": "No listings in universe."}

    benchmark_df, benchmark_label = get_nifty500_data()
    if benchmark_df.empty:
        return {"error": "Could not load NIFTY 500 benchmark."}

    bench_close = _align_benchmark(benchmark_df)
    bench_return = total_return_pct(bench_close)
    bench_series = series_to_points(bench_close, max_points=48)

    meta: dict[str, dict] = {}
    for _, row in universe.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        meta[ticker] = {
            "name": safe_str(row.get("name")),
            "market": safe_str(row.get("market")) or None,
            "sector": safe_str(row.get("sector")),
            "industry": safe_str(row.get("industry")),
            "sub_sector": safe_str(row.get("sub_sector")),
            "market_cap_cr": row.get("market_cap_cr"),
        }

    workers = max_workers or STRATEGY_MAX_WORKERS

    def _analyze(ticker: str, market: str | None) -> dict | None:
        return _fetch_stock_weekly(ticker, market)

    raw = _run_parallel_scan(
        listings,
        _analyze,
        workers=workers,
        progress_callback=progress_callback,
    )
    stock_rows = [r for r in raw if r]
    if not stock_rows:
        return {"error": "No price histories returned. Try again later."}

    sector_groups, industry_groups = _build_groups(
        stock_rows,
        meta,
        min_group_size=min_group_size,
    )

    all_groups = sector_groups + industry_groups
    stock_df = pd.DataFrame(
        [
            {
                "ticker": s["ticker"],
                "name": s["name"],
                "sector": g["sector"],
                "industry": s.get("industry"),
                "screener_link": None,
                "tv_link": None,
            }
            for g in all_groups
            for s in g["stocks"]
        ]
    )
    if not stock_df.empty:
        stock_df = attach_research_links(stock_df.drop_duplicates("ticker"))
        link_map = {
            safe_str(r["ticker"]).upper(): {
                "sc": safe_str(r.get("screener_link")) or None,
                "tv": safe_str(r.get("tv_link")) or None,
            }
            for _, r in stock_df.iterrows()
        }
        for group in all_groups:
            for stock in group["stocks"]:
                links = link_map.get(stock["ticker"], {})
                stock["sc"] = links.get("sc")
                stock["tv"] = links.get("tv")

    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "market": "NSE",
        "min_mcap_cr": min_mcap_cr,
        "min_group_size": min_group_size,
        "benchmark": benchmark_label.split("(")[0].strip() or "NIFTY 500",
        "benchmark_return_pct": bench_return,
        "benchmark_series": bench_series,
        "as_of": as_of,
        "stocks_scanned": len(listings),
        "stocks_with_data": len(stock_rows),
        "sector_groups": sector_groups,
        "industry_groups": industry_groups,
    }
